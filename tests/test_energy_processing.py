from __future__ import annotations

import pandas as pd

from outage_prediction.processing.energy import _allocate_country_capacity


def test_binational_hydropower_is_split_without_double_counting() -> None:
    rows = pd.DataFrame(
        {
            "Type": ["wind", "hydropower"],
            "Country/area": ["Alpha", "Alpha/Beta"],
            "Capacity (MW)": [50.0, 100.0],
            "Country/area 1 (hydropower only)": [None, "Alpha"],
            "Country/area 2 (hydropower only)": [None, "Beta"],
            "Country/area 1 Capacity (MW) (hydropower only)": [None, 60.0],
            "Country/area 2 Capacity (MW) (hydropower only)": [None, 40.0],
        }
    )

    allocated, split_rows = _allocate_country_capacity(rows)

    assert split_rows == 1
    assert allocated["capacity_mw"].sum() == 150.0
    hydro = allocated.loc[allocated["technology_type"].eq("hydropower")]
    assert dict(zip(hydro["gem_country"], hydro["capacity_mw"], strict=True)) == {
        "Alpha": 60.0,
        "Beta": 40.0,
    }

