"""Country-code loading and normalization."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

MAPPING_SHEET = "Regions, area, and countries"
BOUNDARY_ISO_ALIASES = {"IMY": "IMN"}


def load_gem_country_mapping(workbook_path: Path) -> pd.DataFrame:
    columns = ["GEM Standard Country Name/Area", "ISO-alpha3 Code"]
    mapping = pd.read_excel(workbook_path, sheet_name=MAPPING_SHEET, usecols=columns)
    mapping = mapping.rename(
        columns={
            "GEM Standard Country Name/Area": "gem_country",
            "ISO-alpha3 Code": "iso3",
        }
    )
    mapping["gem_country"] = mapping["gem_country"].astype("string").str.strip()
    mapping["iso3"] = mapping["iso3"].astype("string").str.strip().str.upper()
    if mapping["gem_country"].duplicated().any():
        duplicates = mapping.loc[mapping["gem_country"].duplicated(), "gem_country"].tolist()
        raise ValueError(f"GIPT country mapping has duplicate names: {duplicates}")
    duplicate_iso = mapping["iso3"].dropna().duplicated()
    if duplicate_iso.any():
        raise ValueError("GIPT country mapping contains duplicate ISO3 codes")
    return mapping
