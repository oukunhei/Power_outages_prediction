"""Aggregate annual CMIP5 climate indicators to countries for one or more years."""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr

from outage_prediction.processing.spatial import (
    SpatialWeights,
    build_spatial_weights,
    nearest_grid_indices,
)


@dataclass(frozen=True, slots=True)
class ClimateIndicator:
    path: Path
    variable: str
    output_column: str
    expected_unit_tokens: tuple[str, ...]


@dataclass(slots=True)
class ClimateProcessingResult:
    features: pd.DataFrame
    report: dict[str, Any]


def _open_dataset(path: Path) -> xr.Dataset:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="variable .* has multiple fill values")
        return xr.open_dataset(path, engine="netcdf4")


def _validate_dataset(
    dataset: xr.Dataset,
    indicator: ClimateIndicator,
    expected_members: int,
    expected_start_year: int,
    expected_end_year: int,
) -> tuple[xr.DataArray, np.ndarray]:
    if indicator.variable not in dataset:
        raise ValueError(f"{indicator.path.name} does not contain {indicator.variable!r}")
    data = dataset[indicator.variable]
    required_dims = {"member", "time", "lat", "lon"}
    if not required_dims.issubset(data.dims):
        missing_dims = required_dims - set(data.dims)
        raise ValueError(f"{indicator.path.name} is missing dimensions {missing_dims}")
    if dataset.sizes["member"] != expected_members:
        raise ValueError(
            f"{indicator.path.name} has {dataset.sizes['member']} members; "
            f"expected {expected_members}"
        )
    years = dataset["time"].dt.year.values.astype(int)
    expected_years = np.arange(expected_start_year, expected_end_year + 1)
    if not np.array_equal(years, expected_years):
        raise ValueError(
            f"{indicator.path.name} must contain one annual record for every year "
            f"from {expected_start_year} through {expected_end_year}"
        )
    units = str(data.attrs.get("units", "")).lower()
    if not all(token.lower() in units for token in indicator.expected_unit_tokens):
        raise ValueError(
            f"Unexpected units for {indicator.variable}: {data.attrs.get('units')!r}"
        )
    return data, years


def _select_years(
    data: xr.DataArray,
    available_years: np.ndarray,
    years: list[int],
) -> xr.DataArray:
    positions: list[int] = []
    for year in years:
        matches = np.flatnonzero(available_years == year)
        if len(matches) != 1:
            raise ValueError(f"Climate data must contain exactly one record for {year}")
        positions.append(int(matches[0]))
    return data.isel(time=positions).transpose("time", "member", "lat", "lon").load()


def _validate_and_select(
    dataset: xr.Dataset,
    indicator: ClimateIndicator,
    year: int,
    expected_members: int,
    expected_start_year: int,
    expected_end_year: int,
) -> xr.DataArray:
    """Retain the single-year helper for callers and focused unit tests."""
    data, available_years = _validate_dataset(
        dataset,
        indicator,
        expected_members,
        expected_start_year,
        expected_end_year,
    )
    return _select_years(data, available_years, [year]).isel(time=0)


def _validate_provenance(indicator: ClimateIndicator) -> dict[str, str]:
    provenance_path = indicator.path.with_name("provenance.json")
    if not provenance_path.is_file():
        raise FileNotFoundError(f"Missing CDS provenance file: {provenance_path}")
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid CDS provenance JSON: {provenance_path}") from error
    labels = [
        str(entity.get("prov:label", ""))
        for entity in provenance.get("entity", {}).values()
        if isinstance(entity, dict)
    ]
    if indicator.path.name not in labels:
        raise ValueError(
            f"CDS provenance does not name its NetCDF file: {indicator.path.name}"
        )
    return {"path": provenance_path.name, "netcdf_label": indicator.path.name}


def _aggregate_indicator_years(
    data: xr.DataArray,
    boundaries: gpd.GeoDataFrame,
    weights: SpatialWeights,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Aggregate all selected years without repeating the expensive spatial mask work."""
    values = np.asarray(data.values, dtype=float).reshape(
        data.sizes["time"], data.sizes["member"], -1
    )
    country_by_member = np.full(
        (data.sizes["time"], data.sizes["member"], len(boundaries)),
        np.nan,
        dtype=float,
    )

    # Every grid cell belongs to at most one region. Iterating only over a country's
    # non-zero cells avoids a dense year/member-by-country matrix multiplication.
    for region_index in range(len(boundaries)):
        cell_indices = np.flatnonzero(weights.matrix[region_index] > 0)
        if len(cell_indices) == 0:
            continue
        cell_weights = weights.matrix[region_index, cell_indices]
        region_values = values[:, :, cell_indices]
        finite = np.isfinite(region_values)
        numerator = np.nan_to_num(region_values, nan=0.0) @ cell_weights
        denominator = finite.astype(float) @ cell_weights
        with np.errstate(divide="ignore", invalid="ignore"):
            country_by_member[:, :, region_index] = np.divide(
                numerator,
                denominator,
                out=np.full_like(numerator, np.nan),
                where=denominator > 0,
            )

    fallback = np.broadcast_to(
        weights.grid_cell_counts == 0,
        (data.sizes["time"], len(boundaries)),
    ).copy()
    fallback |= ~np.isfinite(country_by_member).any(axis=1)
    representative_points = boundaries.geometry.representative_point()
    for region_index in np.flatnonzero(fallback.any(axis=0)):
        point = representative_points.iloc[int(region_index)]
        lat_index, lon_index = nearest_grid_indices(
            point.x,
            point.y,
            weights.longitudes,
            weights.latitudes,
        )
        fallback_years = np.flatnonzero(fallback[:, region_index])
        country_by_member[fallback_years, :, region_index] = values[
            fallback_years,
            :,
            lat_index * len(weights.longitudes) + lon_index,
        ]

    valid_members = np.isfinite(country_by_member).sum(axis=1)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN slice encountered")
        median = np.nanmedian(country_by_member, axis=1)
        percentile_10 = np.nanpercentile(country_by_member, 10, axis=1)
        percentile_90 = np.nanpercentile(country_by_member, 90, axis=1)
    return median, percentile_10, percentile_90, valid_members, fallback


def _aggregate_indicator(
    data: xr.DataArray,
    boundaries: gpd.GeoDataFrame,
    weights: SpatialWeights,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Compatibility wrapper for a single annual data array."""
    expanded = data.expand_dims(time=[0]).transpose("time", "member", "lat", "lon")
    outputs = _aggregate_indicator_years(expanded, boundaries, weights)
    return tuple(output[0] for output in outputs)  # type: ignore[return-value]


def build_climate_features_for_years(
    indicators: list[ClimateIndicator],
    boundaries: gpd.GeoDataFrame,
    years: list[int],
    expected_members: int,
    expected_start_year: int,
    expected_end_year: int,
    thresholds: dict[str, float],
) -> ClimateProcessingResult:
    if not indicators:
        raise ValueError("At least one climate indicator is required")
    normalized_years = sorted({int(year) for year in years})
    if not normalized_years:
        raise ValueError("At least one climate year is required")
    if normalized_years[0] < expected_start_year or normalized_years[-1] > expected_end_year:
        raise ValueError(
            f"Climate years must be within {expected_start_year}-{expected_end_year}"
        )

    country_count = len(boundaries)
    features = pd.DataFrame(
        {
            "climate_year": np.repeat(normalized_years, country_count),
            "iso3": np.tile(boundaries["iso3"].to_numpy(), len(normalized_years)),
        }
    )
    spatial_weights: SpatialWeights | None = None
    reference_lon: np.ndarray | None = None
    reference_lat: np.ndarray | None = None
    variable_reports: dict[str, Any] = {}
    combined_fallback: np.ndarray | None = None

    for indicator in indicators:
        provenance = _validate_provenance(indicator)
        with _open_dataset(indicator.path) as dataset:
            data, available_years = _validate_dataset(
                dataset,
                indicator,
                expected_members,
                expected_start_year,
                expected_end_year,
            )
            selected = _select_years(data, available_years, normalized_years)
            longitudes = np.asarray(dataset["lon"].values, dtype=float)
            latitudes = np.asarray(dataset["lat"].values, dtype=float)
            if spatial_weights is None:
                spatial_weights = build_spatial_weights(boundaries, longitudes, latitudes)
                reference_lon = longitudes
                reference_lat = latitudes
            elif not (
                np.array_equal(reference_lon, longitudes)
                and np.array_equal(reference_lat, latitudes)
            ):
                raise ValueError("Climate indicator files do not share the same grid")

            median, p10, p90, valid_members, fallback = _aggregate_indicator_years(
                selected,
                boundaries,
                spatial_weights,
            )
            column = indicator.output_column
            features[column] = median.reshape(-1)
            features[f"{column}_p10"] = p10.reshape(-1)
            features[f"{column}_p90"] = p90.reshape(-1)
            features[f"{column}_member_count"] = valid_members.reshape(-1)
            combined_fallback = (
                fallback if combined_fallback is None else combined_fallback | fallback
            )
            valid_by_year = np.isfinite(median).sum(axis=1)
            variable_reports[column] = {
                "file": indicator.path.name,
                "variable": indicator.variable,
                "units": selected.attrs.get("units"),
                "member_count": int(selected.sizes["member"]),
                "valid_country_count_by_year": {
                    str(year): int(count)
                    for year, count in zip(normalized_years, valid_by_year, strict=True)
                },
                "fallback_country_year_count": int(fallback.sum()),
                "provenance": provenance,
            }

    if spatial_weights is None or combined_fallback is None:
        raise RuntimeError("Climate spatial weights were not initialized")
    features["climate_grid_cell_count"] = np.tile(
        spatial_weights.grid_cell_counts, len(normalized_years)
    )
    features["climate_spatial_fallback"] = combined_fallback.reshape(-1)

    indicator_thresholds = {
        "drought": ("dry", float(thresholds["drought_days"])),
        "heat": ("cdd", float(thresholds["cooling_degree_days"])),
        "cold": ("hdd", float(thresholds["heating_degree_days"])),
    }
    for output, (continuous, threshold) in indicator_thresholds.items():
        features[output] = (features[continuous] > threshold).astype(float)
        features.loc[features[continuous].isna(), output] = np.nan

    report = {
        "years": normalized_years,
        "period": [int(expected_start_year), int(expected_end_year)],
        "aggregation": "country area-weighted mean per member, then ensemble median",
        "grid": {
            "latitude_count": int(len(spatial_weights.latitudes)),
            "longitude_count": int(len(spatial_weights.longitudes)),
        },
        "country_count": int(country_count),
        "year_country_rows": int(len(features)),
        "fallback_country_year_count": int(combined_fallback.sum()),
        "variables": variable_reports,
    }
    return ClimateProcessingResult(features=features, report=report)


def build_climate_features(
    indicators: list[ClimateIndicator],
    boundaries: gpd.GeoDataFrame,
    year: int,
    expected_members: int,
    expected_start_year: int,
    expected_end_year: int,
    thresholds: dict[str, float],
) -> ClimateProcessingResult:
    """Build one year with the same recovered aggregation used by multi-year releases."""
    result = build_climate_features_for_years(
        indicators=indicators,
        boundaries=boundaries,
        years=[year],
        expected_members=expected_members,
        expected_start_year=expected_start_year,
        expected_end_year=expected_end_year,
        thresholds=thresholds,
    )
    result.features = result.features.drop(columns="climate_year")
    result.report["year"] = int(year)
    result.report["fallback_country_count"] = result.report["fallback_country_year_count"]
    return result
