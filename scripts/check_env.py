"""Fail fast when the project environment is missing or internally incompatible."""

from __future__ import annotations

import importlib
import importlib.metadata
import math
import sys
from pathlib import Path

EXPECTED_IMPORTS = {
    "dask": "dask",
    "geopandas": "geopandas",
    "matplotlib": "matplotlib",
    "netCDF4": "netCDF4",
    "openpyxl": "openpyxl",
    "pandas": "pandas",
    "plotly": "plotly",
    "pyarrow": "pyarrow",
    "pydantic-settings": "pydantic_settings",
    "PyYAML": "yaml",
    "regionmask": "regionmask",
    "rioxarray": "rioxarray",
    "streamlit": "streamlit",
    "xarray": "xarray",
}


def require_isolated_environment() -> Path:
    prefix = Path(sys.prefix).resolve()
    base_prefix = Path(sys.base_prefix).resolve()
    if prefix == base_prefix:
        raise RuntimeError(
            "The check is running outside a virtual environment. "
            "Use 'uv run python scripts/check_env.py'."
        )
    if prefix.name != ".venv":
        raise RuntimeError(f"Expected the project .venv, but Python is using: {prefix}")
    return prefix


def import_and_report() -> None:
    failures: list[str] = []
    for distribution, module_name in EXPECTED_IMPORTS.items():
        try:
            importlib.import_module(module_name)
            version = importlib.metadata.version(distribution)
            print(f"  {distribution:<18} {version}")
        except Exception as exc:  # noqa: BLE001 - report every binary/import failure together
            failures.append(f"{distribution}: {type(exc).__name__}: {exc}")

    if failures:
        details = "\n".join(f"  - {failure}" for failure in failures)
        raise RuntimeError(f"Dependency verification failed:\n{details}")


def run_compatibility_smoke_test() -> None:
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import xarray as xr
    from shapely.geometry import Point

    frame = pd.DataFrame({"risk": np.array([0.1, 0.2], dtype=float)})
    array = xr.DataArray(frame["risk"].to_numpy(), dims=("country",))
    geo = gpd.GeoDataFrame(frame, geometry=[Point(0, 0), Point(1, 1)], crs="EPSG:4326")

    if not math.isclose(float(array.sum()), 0.3, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError(
            "NumPy/pandas/xarray numerical smoke test returned an unexpected result."
        )
    if geo.crs is None or geo.crs.to_epsg() != 4326:
        raise RuntimeError("GeoPandas/Shapely CRS smoke test failed.")


def main() -> None:
    environment = require_isolated_environment()
    print(f"Python: {sys.version.split()[0]}")
    print(f"Environment: {environment}")
    print("Dependencies:")
    import_and_report()
    run_compatibility_smoke_test()
    print("Compatibility smoke test: PASS")


if __name__ == "__main__":
    main()
