"""Browser-compatible interactive map without remote tiles or WebGL."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.colors import sample_colorscale

MAP_COLORSCALE = [
    [0.0, "#2878B5"],
    [0.45, "#F5F7F6"],
    [0.68, "#F9C66B"],
    [1.0, "#C83E3A"],
]


def _geometry_coordinates(
    geometry: dict[str, Any],
) -> tuple[list[float | None], list[float | None]]:
    polygons = (
        [geometry["coordinates"]]
        if geometry["type"] == "Polygon"
        else geometry["coordinates"]
    )
    longitudes: list[float | None] = []
    latitudes: list[float | None] = []
    for polygon in polygons:
        exterior = polygon[0]
        longitudes.extend(point[0] for point in exterior)
        latitudes.extend(point[1] for point in exterior)
        longitudes.append(None)
        latitudes.append(None)
    return longitudes, latitudes


def build_interactive_map(data: pd.DataFrame, geojson: dict[str, Any]) -> go.Figure:
    risk_by_iso = data.set_index("iso3", drop=False)
    scored = data["risk_score"].dropna()
    color_limit = max(float(scored.abs().max()), 1e-9)
    figure = go.Figure()

    for feature in geojson["features"]:
        properties = feature.get("properties", {})
        iso3 = str(properties["iso3"])
        country_name = properties.get("country_name") or properties.get("name") or "未知地区"
        longitudes, latitudes = _geometry_coordinates(feature["geometry"])
        row = risk_by_iso.loc[iso3] if iso3 in risk_by_iso.index else None
        has_score = row is not None and pd.notna(row["risk_score"])

        if has_score:
            normalized = (float(row["risk_score"]) / color_limit + 1.0) / 2.0
            fill_color = sample_colorscale(MAP_COLORSCALE, [min(max(normalized, 0.0), 1.0)])[0]
            hover = (
                f"<b>{country_name}</b><br>"
                f"相对风险：{row['risk_score']:.4f}<br>"
                f"气候直接贡献占比：{row['climate_share_abs']:.1%}<br>"
                f"新能源交互贡献占比：{row['renewable_share_abs']:.1%}"
                "<extra></extra>"
            )
        else:
            fill_color = "#D9DEE5"
            hover = f"<b>{country_name}</b><br>数据不足<extra></extra>"

        figure.add_trace(
            go.Scatter(
                x=longitudes,
                y=latitudes,
                mode="lines",
                fill="toself",
                fillcolor=fill_color,
                line={"color": "white", "width": 0.45},
                customdata=[[iso3] for _ in longitudes],
                hoveron="fills",
                hovertemplate=hover,
                name=country_name,
                showlegend=False,
            )
        )

    figure.add_trace(
        go.Scatter(
            x=[None, None],
            y=[None, None],
            mode="markers",
            marker={
                "color": [-color_limit, color_limit],
                "cmin": -color_limit,
                "cmax": color_limit,
                "colorscale": MAP_COLORSCALE,
                "showscale": True,
                "colorbar": {
                    "title": {"text": "相对风险得分", "side": "right"},
                    "thickness": 13,
                    "len": 0.58,
                    "outlinewidth": 0,
                },
            },
            hoverinfo="skip",
            showlegend=False,
        )
    )
    figure.update_layout(
        height=590,
        margin={"l": 0, "r": 0, "t": 8, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        clickmode="event+select",
        dragmode="pan",
        showlegend=False,
        xaxis={"range": [-180, 180], "visible": False, "showgrid": False, "zeroline": False},
        yaxis={
            "range": [-60, 90],
            "visible": False,
            "showgrid": False,
            "zeroline": False,
            "scaleanchor": "x",
            "scaleratio": 1,
        },
    )
    return figure
