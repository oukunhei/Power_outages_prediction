from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from shapely.geometry import box

from outage_prediction.processing.climate import ClimateIndicator, build_climate_features


def _write_indicator(
    root: Path,
    filename: str,
    variable: str,
    units: str,
    values_2007: tuple[float, float],
) -> Path:
    directory = root / variable
    directory.mkdir()
    path = directory / filename
    values = np.zeros((2, 2, 2, 2), dtype=float)
    values[0, 1, :, :] = values_2007[0]
    values[1, 1, :, :] = values_2007[1]
    dataset = xr.Dataset(
        {
            variable: (
                ("member", "time", "lat", "lon"),
                values,
                {"units": units},
            )
        },
        coords={
            "member": ["m1", "m2"],
            "time": pd.to_datetime(["2006-01-01", "2007-01-01"]),
            "lat": [-5.0, 5.0],
            "lon": [0.0, 10.0],
        },
    )
    dataset.to_netcdf(path, engine="netcdf4")
    (directory / "provenance.json").write_text(
        json.dumps({"entity": {"output": {"prov:label": filename}}}),
        encoding="utf-8",
    )
    return path


def test_country_aggregation_and_strict_thresholds(tmp_path: Path) -> None:
    boundaries = gpd.GeoDataFrame(
        {
            "iso3": ["AAA"],
            "boundary_name": ["Alpha"],
            "region_id": [0],
        },
        geometry=[box(-20, -20, 20, 20)],
        crs="EPSG:4326",
    )
    dry = _write_indicator(tmp_path, "dry.nc", "dry_var", "days", (20.0, 40.0))
    cdd = _write_indicator(tmp_path, "cdd.nc", "cdd_var", "degC day", (301.0, 301.0))
    hdd = _write_indicator(tmp_path, "hdd.nc", "hdd_var", "degC day", (3000.0, 3000.0))

    result = build_climate_features(
        indicators=[
            ClimateIndicator(dry, "dry_var", "dry", ("day",)),
            ClimateIndicator(cdd, "cdd_var", "cdd", ("degc", "day")),
            ClimateIndicator(hdd, "hdd_var", "hdd", ("degc", "day")),
        ],
        boundaries=boundaries,
        year=2007,
        expected_members=2,
        expected_start_year=2006,
        expected_end_year=2007,
        thresholds={
            "drought_days": 30.0,
            "cooling_degree_days": 300.0,
            "heating_degree_days": 3000.0,
        },
    )

    row = result.features.iloc[0]
    assert row["dry"] == 30.0
    assert row["drought"] == 0.0
    assert row["heat"] == 1.0
    assert row["cold"] == 0.0
    assert result.report["period"] == [2006, 2007]

