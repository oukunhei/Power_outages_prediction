"""Generate the high-resolution static risk map."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm


def render_static_map(
    world: gpd.GeoDataFrame,
    output_path: Path,
    scenario: str,
    year: int,
    hdd_threshold: float,
    color_limit: float | None = None,
) -> None:
    scored = world["risk_score"].dropna()
    if scored.empty:
        raise ValueError("No valid risk scores are available for the static map")
    if color_limit is None:
        color_limit = max(float(scored.abs().max()), 1e-9)
    if color_limit <= 0:
        raise ValueError("Static-map color limit must be positive")
    norm = TwoSlopeNorm(vmin=-color_limit, vcenter=0.0, vmax=color_limit)
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
    axis.set_title(f"Global Relative Power Outage Risk · {year}", fontsize=20, pad=14)
    axis.text(
        0.0,
        -0.02,
        f"{scenario} · prediction year {year} · HDD threshold: {hdd_threshold:g} degree-days\n"
        "Sources: Global Energy Monitor; Copernicus Climate Data Store",
        transform=axis.transAxes,
        fontsize=9,
        color="#485568",
    )
    scalar = plt.cm.ScalarMappable(norm=norm, cmap="RdYlBu_r")
    colorbar = figure.colorbar(
        scalar,
        ax=axis,
        orientation="horizontal",
        shrink=0.48,
        pad=0.025,
    )
    colorbar.set_label("Relative risk score (not probability)")
    figure.savefig(output_path, dpi=300, facecolor="white")
    plt.close(figure)
