"""Build a reproducible frontend release from the original project aggregates."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm

from outage_prediction.config import load_config, resolve_project_path
from outage_prediction.scoring.registry import create_risk_model

BOUNDARY_ISO_ALIASES = {"IMY": "IMN"}


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


def _prepare_boundaries(boundary_path: Path, results: pd.DataFrame) -> gpd.GeoDataFrame:
    boundaries = gpd.read_file(boundary_path).to_crs("EPSG:4326")
    boundaries = boundaries.loc[boundaries["iso3"].notna(), ["iso3", "name", "geometry"]].copy()
    boundaries["iso3"] = boundaries["iso3"].replace(BOUNDARY_ISO_ALIASES)
    boundaries["geometry"] = boundaries.geometry.make_valid()
    boundaries = boundaries.dissolve(by="iso3", aggfunc="first").reset_index()
    boundaries["geometry"] = boundaries.geometry.simplify(0.04, preserve_topology=True)
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
    merged = boundaries.merge(results[display_columns], on="iso3", how="left")
    merged["country_name"] = merged["country_name"].fillna(merged["name"])
    merged["data_quality"] = merged["data_quality"].fillna("unavailable")
    return merged


def _render_static_map(world: gpd.GeoDataFrame, output_path: Path) -> None:
    scored = world["risk_score"].dropna()
    if scored.empty:
        raise ValueError("No valid risk scores are available for the static map")
    lower = float(scored.min())
    upper = float(scored.max())
    norm = TwoSlopeNorm(vmin=min(lower, -1e-9), vcenter=0.0, vmax=max(upper, 1e-9))
    figure, axis = plt.subplots(figsize=(15, 8.5), constrained_layout=True)
    world.plot(
        column="risk_score",
        ax=axis,
        cmap="RdYlBu_r",
        norm=norm,
        linewidth=0.18,
        edgecolor="white",
        missing_kwds={"color": "#D9DEE5", "label": "Data unavailable"},
    )
    axis.set_axis_off()
    axis.set_title("Global Relative Power Outage Risk", fontsize=20, pad=14)
    axis.text(
        0.0,
        -0.02,
        "CMIP5 / RCP4.5 · fixed year 2100 · HDD threshold: 3000 degree-days\n"
        "Sources: Global Energy Monitor; Copernicus Climate Data Store",
        transform=axis.transAxes,
        fontsize=9,
        color="#485568",
    )
    scalar = plt.cm.ScalarMappable(norm=norm, cmap="RdYlBu_r")
    colorbar = figure.colorbar(scalar, ax=axis, orientation="horizontal", shrink=0.48, pad=0.025)
    colorbar.set_label("Relative risk score (not probability)")
    figure.savefig(output_path, dpi=300, facecolor="white")
    plt.close(figure)


def _publish(staging: Path, output_root: Path) -> Path:
    latest = output_root / "latest"
    archive = output_root / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    if latest.exists():
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        shutil.move(str(latest), str(archive / timestamp))
    shutil.move(str(staging), str(latest))
    return latest


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
    world = _prepare_boundaries(boundary_path, results)
    output_root = resolve_project_path(project_root, paths["output_root"])
    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build-", dir=output_root) as temporary:
        staging = Path(temporary) / "release"
        staging.mkdir()
        results.to_csv(staging / "country_risk.csv", index=False)
        results.to_parquet(staging / "country_risk.parquet", index=False)
        legacy.to_csv(staging / "legacy_formula_reproduction.csv", index=False)
        world.to_file(staging / "country_risk.geojson", driver="GeoJSON")
        _render_static_map(world, staging / "power_outage_risk.png")

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
