"""Convert the raw GIPT facility workbook into country-level energy shares."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from outage_prediction.processing.country_codes import load_gem_country_mapping

FACILITY_SHEET = "Power facilities"
FACILITY_COLUMNS = [
    "Type",
    "Country/area",
    "Capacity (MW)",
    "Status",
    "Country/area 1 (hydropower only)",
    "Country/area 2 (hydropower only)",
    "Country/area 1 Capacity (MW) (hydropower only)",
    "Country/area 2 Capacity (MW) (hydropower only)",
    "GEM unit/phase ID",
]
RENEWABLE_TYPES = {
    "utility-scale solar": "pv_capacity_mw",
    "wind": "wind_capacity_mw",
    "hydropower": "hydro_capacity_mw",
}


@dataclass(slots=True)
class EnergyProcessingResult:
    features: pd.DataFrame
    report: dict[str, Any]


def _allocate_country_capacity(facilities: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    country_1 = "Country/area 1 (hydropower only)"
    country_2 = "Country/area 2 (hydropower only)"
    capacity_1 = "Country/area 1 Capacity (MW) (hydropower only)"
    capacity_2 = "Country/area 2 Capacity (MW) (hydropower only)"
    is_binational = facilities["Type"].eq("hydropower") & facilities[country_2].notna()

    ordinary = facilities.loc[~is_binational, ["Type", "Country/area", "Capacity (MW)"]].copy()
    ordinary.columns = ["technology_type", "gem_country", "capacity_mw"]

    shared = facilities.loc[is_binational]
    if shared[[country_1, country_2, capacity_1, capacity_2]].isna().any().any():
        raise ValueError("A binational hydropower row is missing country allocation data")
    difference = (shared[capacity_1] + shared[capacity_2] - shared["Capacity (MW)"]).abs()
    if bool((difference > 0.1).any()):
        raise ValueError("Binational hydropower allocations do not sum to total capacity")

    first = shared[["Type", country_1, capacity_1]].copy()
    first.columns = ["technology_type", "gem_country", "capacity_mw"]
    second = shared[["Type", country_2, capacity_2]].copy()
    second.columns = ["technology_type", "gem_country", "capacity_mw"]
    allocated = pd.concat([ordinary, first, second], ignore_index=True)
    return allocated, int(is_binational.sum())


def build_energy_features(
    workbook_path: Path,
    included_statuses: list[str],
) -> EnergyProcessingResult:
    facilities = pd.read_excel(
        workbook_path,
        sheet_name=FACILITY_SHEET,
        usecols=FACILITY_COLUMNS,
    )
    facilities["Type"] = facilities["Type"].astype("string").str.strip().str.lower()
    facilities["Status"] = facilities["Status"].astype("string").str.strip().str.lower()
    facilities["Capacity (MW)"] = pd.to_numeric(facilities["Capacity (MW)"], errors="coerce")
    raw_rows = len(facilities)

    statuses = {status.strip().lower() for status in included_statuses}
    filtered = facilities.loc[facilities["Status"].isin(statuses)].copy()
    invalid_capacity = filtered["Capacity (MW)"].isna() | filtered["Capacity (MW)"].le(0)
    invalid_capacity_rows = int(invalid_capacity.sum())
    filtered = filtered.loc[~invalid_capacity]
    if filtered.empty:
        raise ValueError("No GIPT facility rows remain after status and capacity validation")

    allocated, binational_rows = _allocate_country_capacity(filtered)
    mapping = load_gem_country_mapping(workbook_path)
    allocated["gem_country"] = allocated["gem_country"].astype("string").str.strip()
    allocated = allocated.merge(mapping, on="gem_country", how="left", validate="many_to_one")
    unmapped = sorted(allocated.loc[allocated["iso3"].isna(), "gem_country"].dropna().unique())
    if unmapped:
        raise ValueError(f"Operating GIPT facilities have no ISO3 mapping: {unmapped}")

    grouped = (
        allocated.groupby(["iso3", "gem_country", "technology_type"], as_index=False)[
            "capacity_mw"
        ]
        .sum()
        .sort_values(["iso3", "technology_type"])
    )
    total = grouped.groupby(["iso3", "gem_country"], as_index=False)["capacity_mw"].sum()
    total = total.rename(columns={"capacity_mw": "total_tracked_capacity_mw"})
    renewable = grouped.loc[grouped["technology_type"].isin(RENEWABLE_TYPES)].copy()
    renewable["capacity_column"] = renewable["technology_type"].map(RENEWABLE_TYPES)
    renewable = renewable.pivot_table(
        index=["iso3", "gem_country"],
        columns="capacity_column",
        values="capacity_mw",
        aggfunc="sum",
        fill_value=0.0,
    ).reset_index()

    features = total.merge(renewable, on=["iso3", "gem_country"], how="left")
    capacity_columns = list(RENEWABLE_TYPES.values())
    for column in capacity_columns:
        if column not in features:
            features[column] = 0.0
        features[column] = features[column].fillna(0.0)
    features["pv_share"] = features["pv_capacity_mw"] / features["total_tracked_capacity_mw"]
    features["wind_share"] = (
        features["wind_capacity_mw"] / features["total_tracked_capacity_mw"]
    )
    features["hydro_share"] = (
        features["hydro_capacity_mw"] / features["total_tracked_capacity_mw"]
    )
    share_columns = ["pv_share", "wind_share", "hydro_share"]
    if not features[share_columns].apply(lambda column: column.between(0, 1)).all().all():
        raise ValueError("One or more country energy shares fall outside [0, 1]")

    report = {
        "source_rows": int(raw_rows),
        "included_statuses": sorted(statuses),
        "filtered_facility_rows": int(len(filtered)),
        "invalid_capacity_rows_dropped": invalid_capacity_rows,
        "binational_hydropower_rows_split": binational_rows,
        "allocated_rows": int(len(allocated)),
        "country_count": int(len(features)),
        "total_tracked_capacity_mw": float(features["total_tracked_capacity_mw"].sum()),
        "share_denominator": "all tracked facilities with included statuses",
    }
    return EnergyProcessingResult(features=features, report=report)
