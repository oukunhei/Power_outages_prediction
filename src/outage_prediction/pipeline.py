"""Build multi-year country risk releases from frozen energy and climate snapshots."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from outage_prediction.config import load_config, resolve_project_path
from outage_prediction.processing.climate import (
    ClimateIndicator,
    build_climate_features_for_years,
)
from outage_prediction.processing.energy import EnergyProcessingResult, build_energy_features
from outage_prediction.processing.spatial import load_world_boundaries
from outage_prediction.scoring.registry import create_risk_model
from outage_prediction.visualization.static_map import render_static_map


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _map_frame(boundaries: pd.DataFrame, results: pd.DataFrame) -> Any:
    display_columns = [
        "iso3",
        "country_name",
        "risk_score",
        "climate_contribution",
        "renewable_interaction_contribution",
        "climate_share_abs",
        "renewable_share_abs",
        "data_quality",
        "climate_year",
    ]
    merged = boundaries[["iso3", "boundary_name", "geometry"]].merge(
        results[display_columns], on="iso3", how="left", validate="one_to_one"
    )
    merged["country_name"] = merged["country_name"].fillna(merged["boundary_name"])
    merged["data_quality"] = merged["data_quality"].fillna("unavailable")
    merged["geometry"] = merged.geometry.simplify(0.04, preserve_topology=True)
    return merged


def _publish(staging: Path, output_root: Path) -> Path:
    latest = output_root / "latest"
    archive = output_root / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    archived: Path | None = None
    if latest.exists():
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        archived = archive / timestamp
        shutil.move(str(latest), str(archived))
    try:
        shutil.move(str(staging), str(latest))
    except Exception:
        if archived is not None and archived.exists() and not latest.exists():
            shutil.move(str(archived), str(latest))
        raise
    return latest


def _input_record(project_root: Path, configured_path: str) -> dict[str, str | int]:
    path = resolve_project_path(project_root, configured_path)
    return {
        "path": str(path.relative_to(project_root)),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _prediction_years(project: dict[str, Any]) -> list[int]:
    return list(
        range(
            int(project["prediction_year_start"]),
            int(project["prediction_year_end"]) + 1,
        )
    )


def _build_results(
    boundaries: pd.DataFrame,
    energy: EnergyProcessingResult,
    climate_features: pd.DataFrame,
    model: Any,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    results = climate_features.merge(
        boundaries[["iso3", "boundary_name"]],
        on="iso3",
        how="left",
        validate="many_to_one",
    )
    results = results.merge(
        energy.features,
        on="iso3",
        how="left",
        validate="many_to_one",
    )
    results["country_name"] = results["gem_country"].fillna(results["boundary_name"])

    energy_columns = ["pv_share", "wind_share", "hydro_share"]
    climate_columns = ["dry", "cdd", "hdd", "drought", "heat", "cold"]
    has_energy = results[energy_columns].notna().all(axis=1)
    has_climate = results[climate_columns].notna().all(axis=1)
    results["data_quality"] = np.select(
        [has_energy & has_climate, ~has_energy & has_climate, has_energy & ~has_climate],
        ["complete", "missing_energy", "missing_climate"],
        default="unavailable",
    )
    predictions = model.predict(results)
    results = pd.concat([results, predictions], axis=1)
    results["energy_release"] = config["energy"]["release"]
    results["energy_status_scope"] = ", ".join(config["energy"]["included_statuses"])
    results["energy_year_assumption"] = "fixed snapshot for every prediction year"
    results["climate_scenario"] = config["project"]["climate_scenario"]
    results["hdd_threshold"] = float(config["thresholds"]["heating_degree_days"])
    results["dry_days"] = results["dry"]
    results["cooling_degree_days"] = results["cdd"]
    results["heating_degree_days"] = results["hdd"]
    results = results.sort_values(["climate_year", "iso3"]).reset_index(drop=True)
    return results, has_energy, has_climate


def build_release(config_path: Path, project_root: Path) -> Path:
    """Build selectable annual results and featured maps from raw local snapshots."""
    config = load_config(config_path)
    paths = config["paths"]
    project = config["project"]
    thresholds = config["thresholds"]
    years = _prediction_years(project)
    featured_years = [int(year) for year in project["featured_prediction_years"]]
    default_year = int(project["default_prediction_year"])
    model = create_risk_model(config["risk_model"])

    boundary_path = resolve_project_path(project_root, paths["world_boundaries"])
    boundaries = load_world_boundaries(boundary_path)
    energy = build_energy_features(
        resolve_project_path(project_root, paths["gem_snapshot"]),
        list(config["energy"]["included_statuses"]),
    )
    indicators = [
        ClimateIndicator(
            path=resolve_project_path(project_root, paths["climate_drought"]),
            variable="cdd",
            output_column="dry",
            expected_unit_tokens=("day",),
        ),
        ClimateIndicator(
            path=resolve_project_path(project_root, paths["climate_cooling"]),
            variable="cd",
            output_column="cdd",
            expected_unit_tokens=("degc", "day"),
        ),
        ClimateIndicator(
            path=resolve_project_path(project_root, paths["climate_heating"]),
            variable="hd",
            output_column="hdd",
            expected_unit_tokens=("degc", "day"),
        ),
    ]
    climate = build_climate_features_for_years(
        indicators=indicators,
        boundaries=boundaries,
        years=years,
        expected_members=int(config["climate"]["expected_members"]),
        expected_start_year=int(config["climate"]["expected_start_year"]),
        expected_end_year=int(config["climate"]["expected_end_year"]),
        thresholds=thresholds,
    )
    results, has_energy, has_climate = _build_results(
        boundaries,
        energy,
        climate.features,
        model,
        config,
    )

    complete = results["data_quality"].eq("complete")
    if not complete.any():
        raise RuntimeError("The full pipeline produced no complete country risk rows")
    decomposition_error = (
        results.loc[complete, "risk_score"]
        - results.loc[complete, "climate_contribution"]
        - results.loc[complete, "renewable_interaction_contribution"]
    ).abs()
    if bool((decomposition_error > 1e-12).any()):
        raise RuntimeError("Risk decomposition validation failed")

    featured_results = results.loc[results["climate_year"].isin(featured_years)]
    color_limit = max(float(featured_results["risk_score"].abs().max()), 1e-9)
    default_results = results.loc[results["climate_year"].eq(default_year)]
    world_default = _map_frame(boundaries, default_results)

    output_root = resolve_project_path(project_root, paths["output_root"])
    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build-", dir=output_root) as temporary:
        staging = Path(temporary) / "release"
        staging.mkdir()
        results.to_csv(staging / "country_risk.csv", index=False)
        results.to_parquet(staging / "country_risk.parquet", index=False)
        energy.features.to_parquet(staging / "energy_features.parquet", index=False)
        climate.features.to_parquet(staging / "climate_features.parquet", index=False)
        world_default.to_file(staging / "country_risk.geojson", driver="GeoJSON")

        static_maps: dict[str, str] = {}
        for year in featured_years:
            year_results = results.loc[results["climate_year"].eq(year)]
            world_year = _map_frame(boundaries, year_results)
            filename = f"power_outage_risk_{year}.png"
            render_static_map(
                world_year,
                staging / filename,
                scenario=str(project["climate_scenario"]),
                year=year,
                hdd_threshold=float(thresholds["heating_degree_days"]),
                color_limit=color_limit,
            )
            static_maps[str(year)] = filename

        inputs = {
            key: _input_record(project_root, paths[key])
            for key in [
                "gem_snapshot",
                "climate_drought",
                "climate_cooling",
                "climate_heating",
                "world_boundaries",
            ]
        }
        energy_not_mapped = sorted(set(energy.features["iso3"]) - set(boundaries["iso3"]))
        year_summaries = {
            str(year): {
                "complete_rows": int(
                    results.loc[results["climate_year"].eq(year), "data_quality"]
                    .eq("complete")
                    .sum()
                ),
                "risk_min": float(
                    results.loc[results["climate_year"].eq(year), "risk_score"].min()
                ),
                "risk_max": float(
                    results.loc[results["climate_year"].eq(year), "risk_score"].max()
                ),
            }
            for year in years
        }
        manifest = {
            "pipeline": "multi_year_raw_snapshots_v2",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "project": project,
            "available_prediction_years": years,
            "featured_prediction_years": featured_years,
            "default_prediction_year": default_year,
            "static_maps": static_maps,
            "risk_color_limit": color_limit,
            "thresholds": thresholds,
            "risk_model": {"name": model.name, "version": model.version},
            "energy_processing": energy.report,
            "climate_processing": climate.report,
            "energy_projection_assumption": (
                "The GIPT operating-capacity snapshot is held fixed for all years; "
                "year-to-year changes therefore reflect climate inputs only."
            ),
            "published_rows": int(len(results)),
            "complete_rows": int(complete.sum()),
            "missing_energy_rows": int((~has_energy).sum()),
            "missing_climate_rows": int((~has_climate).sum()),
            "energy_iso3_without_boundary": energy_not_mapped,
            "maximum_decomposition_error": float(decomposition_error.max()),
            "year_summaries": year_summaries,
            "inputs": inputs,
            "sources": config["sources"],
        }
        (staging / "energy_quality_report.json").write_text(
            json.dumps(energy.report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (staging / "climate_quality_report.json").write_text(
            json.dumps(climate.report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (staging / "run_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        published = _publish(staging, output_root)
    return published
