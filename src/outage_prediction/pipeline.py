"""Orchestrate full raw-data builds and legacy regression checks."""

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
from outage_prediction.processing.climate import ClimateIndicator, build_climate_features
from outage_prediction.processing.energy import build_energy_features
from outage_prediction.processing.spatial import load_world_boundaries
from outage_prediction.scoring.registry import create_risk_model
from outage_prediction.visualization.static_map import render_static_map


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_metric(path: Path, value_column: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame = frame.drop(columns=[column for column in frame if column.startswith("Unnamed")])
    required = {"iso", value_column}
    if not required.issubset(frame.columns):
        raise ValueError(f"{path} must contain columns {sorted(required)}")
    if frame["iso"].duplicated().any():
        raise ValueError(f"{path} contains duplicate ISO3 codes")
    return frame.loc[:, ["iso", value_column]]


def reproduce_legacy_results(
    parameters_path: Path,
    model: Any,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    legacy = pd.read_excel(parameters_path)
    legacy = legacy.rename(
        columns={
            "iso": "legacy_iso3",
            "Country": "country_name",
            "photovoltaic": "pv_share",
            "wind": "wind_share",
            "hydropower": "hydro_share",
            "Risk": "legacy_risk_score",
        }
    )
    predictions = model.predict(legacy)
    difference = (predictions["risk_score"] - legacy["legacy_risk_score"]).abs()
    tolerance = 1e-12
    report = {
        "rows": int(len(legacy)),
        "matched_rows": int((difference <= tolerance).sum()),
        "maximum_absolute_error": float(difference.max()),
        "tolerance": tolerance,
        "status": "PASS" if bool((difference <= tolerance).all()) else "FAIL",
    }
    if report["status"] != "PASS":
        raise RuntimeError(f"Python formula did not reproduce the legacy workbook: {report}")
    legacy["python_reproduced_risk"] = predictions["risk_score"]
    legacy["absolute_error"] = difference
    return legacy, report


def _build_corrected_features(
    legacy: pd.DataFrame,
    config: dict[str, Any],
    project_root: Path,
) -> pd.DataFrame:
    paths = config["paths"]
    frame = legacy[
        [
            "legacy_iso3",
            "country_name",
            "pv_share",
            "wind_share",
            "hydro_share",
            "drought",
            "heat",
            "cold",
            "legacy_risk_score",
        ]
    ].rename(
        columns={
            "drought": "legacy_drought",
            "heat": "legacy_heat",
            "cold": "legacy_cold",
        }
    )
    frame = frame.merge(
        _read_metric(resolve_project_path(project_root, paths["legacy_cooling"]), "cdd"),
        left_on="legacy_iso3",
        right_on="iso",
        how="left",
    ).drop(columns="iso")
    frame = frame.merge(
        _read_metric(resolve_project_path(project_root, paths["legacy_heating"]), "hdd"),
        left_on="legacy_iso3",
        right_on="iso",
        how="left",
    ).drop(columns="iso")
    frame = frame.merge(
        _read_metric(resolve_project_path(project_root, paths["legacy_drought"]), "dry"),
        left_on="legacy_iso3",
        right_on="iso",
        how="left",
    ).drop(columns="iso")

    thresholds = config["thresholds"]
    frame["drought"] = (frame["dry"] > float(thresholds["drought_days"])).astype("Float64")
    frame["heat"] = (frame["cdd"] > float(thresholds["cooling_degree_days"])).astype(
        "Float64"
    )
    frame["cold"] = (frame["hdd"] > float(thresholds["heating_degree_days"])).astype(
        "Float64"
    )
    for metric, indicator in (("dry", "drought"), ("cdd", "heat"), ("hdd", "cold")):
        frame.loc[frame[metric].isna(), indicator] = pd.NA

    required = ["pv_share", "wind_share", "hydro_share", "dry", "cdd", "hdd"]
    frame["data_quality"] = np.where(frame[required].notna().all(axis=1), "complete", "unavailable")
    # Keep the non-standard legacy ZAR row explicit. The workbook already has COG and COD,
    # so silently remapping ZAR would merge distinct rows without evidence.
    frame["iso3"] = frame["legacy_iso3"]
    if frame["iso3"].duplicated().any():
        duplicates = frame.loc[frame["iso3"].duplicated(keep=False), "iso3"].tolist()
        raise ValueError(f"ISO normalization created duplicates: {duplicates}")
    return frame


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


def build_release(config_path: Path, project_root: Path) -> Path:
    """Build production outputs directly from the raw GIPT and CMIP5 snapshots."""
    config = load_config(config_path)
    paths = config["paths"]
    project = config["project"]
    thresholds = config["thresholds"]
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
    climate = build_climate_features(
        indicators=indicators,
        boundaries=boundaries,
        year=int(project["climate_year"]),
        expected_members=int(config["climate"]["expected_members"]),
        expected_start_year=int(config["climate"]["expected_start_year"]),
        expected_end_year=int(config["climate"]["expected_end_year"]),
        thresholds=thresholds,
    )

    results = boundaries[["iso3", "boundary_name"]].copy()
    results = results.merge(energy.features, on="iso3", how="left", validate="one_to_one")
    results = results.merge(climate.features, on="iso3", how="left", validate="one_to_one")
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
    results["energy_release"] = "GIPT August 2026 v3"
    results["energy_status_scope"] = ", ".join(config["energy"]["included_statuses"])
    results["climate_scenario"] = project["climate_scenario"]
    results["climate_year"] = int(project["climate_year"])
    results["hdd_threshold"] = float(thresholds["heating_degree_days"])
    results["dry_days"] = results["dry"]
    results["cooling_degree_days"] = results["cdd"]
    results["heating_degree_days"] = results["hdd"]

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

    world = _map_frame(boundaries, results)
    output_root = resolve_project_path(project_root, paths["output_root"])
    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build-", dir=output_root) as temporary:
        staging = Path(temporary) / "release"
        staging.mkdir()
        results.to_csv(staging / "country_risk.csv", index=False)
        results.to_parquet(staging / "country_risk.parquet", index=False)
        energy.features.to_parquet(staging / "energy_features.parquet", index=False)
        climate.features.to_parquet(staging / "climate_features.parquet", index=False)
        world.to_file(staging / "country_risk.geojson", driver="GeoJSON")
        render_static_map(
            world,
            staging / "power_outage_risk.png",
            scenario=str(project["climate_scenario"]),
            year=int(project["climate_year"]),
            hdd_threshold=float(thresholds["heating_degree_days"]),
        )

        legacy_report: dict[str, Any] | None = None
        legacy_path = resolve_project_path(project_root, paths["legacy_parameters"])
        if legacy_path.is_file():
            legacy, legacy_report = reproduce_legacy_results(legacy_path, model)
            legacy.to_csv(staging / "legacy_formula_reproduction.csv", index=False)

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
        manifest = {
            "pipeline": "full_raw_snapshots_v1",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "project": project,
            "thresholds": thresholds,
            "risk_model": {"name": model.name, "version": model.version},
            "energy_processing": energy.report,
            "climate_processing": climate.report,
            "legacy_formula_reproduction": legacy_report,
            "published_rows": int(len(results)),
            "complete_rows": int(complete.sum()),
            "missing_energy_rows": int((~has_energy).sum()),
            "missing_climate_rows": int((~has_climate).sum()),
            "energy_iso3_without_boundary": energy_not_mapped,
            "maximum_decomposition_error": float(decomposition_error.max()),
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


def build_legacy_release(config_path: Path, project_root: Path) -> Path:
    config = load_config(config_path)
    model = create_risk_model(config["risk_model"])
    paths = config["paths"]
    parameters_path = resolve_project_path(project_root, paths["legacy_parameters"])
    legacy, reproduction = reproduce_legacy_results(parameters_path, model)
    features = _build_corrected_features(legacy, config, project_root)
    predictions = model.predict(features)
    results = pd.concat([features, predictions], axis=1)
    results["climate_scenario"] = config["project"]["climate_scenario"]
    results["climate_year"] = int(config["project"]["climate_year"])
    results["hdd_threshold"] = float(config["thresholds"]["heating_degree_days"])

    boundary_path = resolve_project_path(project_root, paths["world_boundaries"])
    boundaries = load_world_boundaries(boundary_path)
    world = _map_frame(boundaries, results)
    output_root = resolve_project_path(project_root, paths["output_root"])
    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build-", dir=output_root) as temporary:
        staging = Path(temporary) / "release"
        staging.mkdir()
        results.to_csv(staging / "country_risk.csv", index=False)
        results.to_parquet(staging / "country_risk.parquet", index=False)
        legacy.to_csv(staging / "legacy_formula_reproduction.csv", index=False)
        world.to_file(staging / "country_risk.geojson", driver="GeoJSON")
        render_static_map(
            world,
            staging / "power_outage_risk.png",
            scenario=str(config["project"]["climate_scenario"]),
            year=int(config["project"]["climate_year"]),
            hdd_threshold=float(config["thresholds"]["heating_degree_days"]),
        )

        complete = results["data_quality"].eq("complete")
        changed = (
            results.loc[complete, "risk_score"]
            .sub(results.loc[complete, "legacy_risk_score"])
            .abs()
            .gt(1e-12)
        )
        inputs = {
            key: {
                "path": str(resolve_project_path(project_root, value).relative_to(project_root)),
                "sha256": _sha256(resolve_project_path(project_root, value)),
            }
            for key, value in paths.items()
            if key.startswith("legacy_") or key == "world_boundaries"
        }
        manifest = {
            "created_at_utc": datetime.now(UTC).isoformat(),
            "project": config["project"],
            "thresholds": config["thresholds"],
            "risk_model": {"name": model.name, "version": model.version},
            "legacy_formula_reproduction": reproduction,
            "published_rows": int(len(results)),
            "complete_rows": int(complete.sum()),
            "unavailable_rows": int((~complete).sum()),
            "rows_changed_by_corrected_thresholds": int(changed.sum()),
            "inputs": inputs,
            "sources": config["sources"],
        }
        (staging / "run_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        published = _publish(staging, output_root)
    return published
