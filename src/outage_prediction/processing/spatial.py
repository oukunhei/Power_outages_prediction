"""World-boundary preparation and gridded country aggregation utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import regionmask

from outage_prediction.processing.country_codes import BOUNDARY_ISO_ALIASES


@dataclass(slots=True)
class SpatialWeights:
    matrix: np.ndarray
    grid_cell_counts: np.ndarray
    latitudes: np.ndarray
    longitudes: np.ndarray


def load_world_boundaries(boundary_path: Path) -> gpd.GeoDataFrame:
    boundaries = gpd.read_file(boundary_path).to_crs("EPSG:4326")
    required = {"iso3", "name", "geometry"}
    if not required.issubset(boundaries.columns):
        raise ValueError(f"World boundaries must contain {sorted(required)}")
    boundaries = boundaries.loc[
        boundaries["iso3"].notna(), ["iso3", "name", "geometry"]
    ].copy()
    boundaries["iso3"] = boundaries["iso3"].replace(BOUNDARY_ISO_ALIASES)
    boundaries["geometry"] = boundaries.geometry.make_valid()
    boundaries = boundaries.dissolve(by="iso3", aggfunc="first").reset_index()
    boundaries = boundaries.rename(columns={"name": "boundary_name"})
    boundaries = boundaries.sort_values("iso3").reset_index(drop=True)
    boundaries["region_id"] = np.arange(len(boundaries), dtype=int)
    if boundaries["iso3"].duplicated().any() or boundaries.geometry.is_empty.any():
        raise ValueError("World boundaries contain duplicate ISO3 codes or empty geometry")
    return boundaries


def build_spatial_weights(
    boundaries: gpd.GeoDataFrame,
    longitudes: np.ndarray,
    latitudes: np.ndarray,
) -> SpatialWeights:
    regions = regionmask.from_geopandas(
        boundaries,
        numbers="region_id",
        names="boundary_name",
        abbrevs="iso3",
        overlap=False,
    )
    mask = regions.mask_3D(
        longitudes,
        latitudes,
        drop=False,
        wrap_lon=180,
    ).values
    latitude_weights = np.cos(np.deg2rad(latitudes))
    cell_weights = np.broadcast_to(latitude_weights[:, None], (len(latitudes), len(longitudes)))
    matrix = mask.reshape(len(boundaries), -1).astype(float)
    grid_cell_counts = matrix.sum(axis=1).astype(int)
    matrix *= cell_weights.reshape(1, -1)
    return SpatialWeights(
        matrix=matrix,
        grid_cell_counts=grid_cell_counts,
        latitudes=np.asarray(latitudes),
        longitudes=np.asarray(longitudes),
    )


def nearest_grid_indices(
    longitude: float,
    latitude: float,
    longitudes: np.ndarray,
    latitudes: np.ndarray,
) -> tuple[int, int]:
    longitude_distance = np.abs(((longitudes - longitude + 180) % 360) - 180)
    return int(np.argmin(np.abs(latitudes - latitude))), int(np.argmin(longitude_distance))
