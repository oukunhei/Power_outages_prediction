from __future__ import annotations

import pandas as pd

from outage_prediction.visualization.interactive_map import build_interactive_map


def test_interactive_map_contains_local_country_polygons_and_colorbar() -> None:
    data = pd.DataFrame(
        {
            "iso3": ["AAA"],
            "risk_score": [0.2],
            "climate_share_abs": [0.25],
            "renewable_share_abs": [0.75],
        }
    )
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"iso3": "AAA", "country_name": "Alpha"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                },
            }
        ],
    }

    figure = build_interactive_map(data, geojson)

    assert len(figure.data) == 2
    assert figure.data[0].fill == "toself"
    assert "相对风险：0.2000" in figure.data[0].hovertemplate
    assert figure.data[1].marker.showscale is True

