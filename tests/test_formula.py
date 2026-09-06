from __future__ import annotations

import math

import pandas as pd

from outage_prediction.scoring.formula import FormulaRiskModel


def test_formula_known_country_inputs() -> None:
    features = pd.DataFrame(
        {
            "drought": [1],
            "heat": [1],
            "cold": [1],
            "pv_share": [0.8036842105263158],
            "wind_share": [0.0],
            "hydro_share": [0.1581578947368421],
        }
    )
    result = FormulaRiskModel().predict(features).iloc[0]
    assert math.isclose(result["risk_score"], 0.6183841842105262, abs_tol=1e-12)
    assert math.isclose(
        result["risk_score"],
        result["climate_contribution"] + result["renewable_interaction_contribution"],
        abs_tol=1e-12,
    )
    term_columns = [column for column in result.index if column.startswith("term_")]
    assert len(term_columns) == 12
    assert math.isclose(result["risk_score"], result[term_columns].sum(), abs_tol=1e-12)


def test_zero_contributions_have_zero_shares() -> None:
    features = pd.DataFrame(
        {
            "drought": [0],
            "heat": [0],
            "cold": [0],
            "pv_share": [0.5],
            "wind_share": [0.25],
            "hydro_share": [0.25],
        }
    )
    result = FormulaRiskModel().predict(features).iloc[0]
    assert result["risk_score"] == 0
    assert result["climate_share_abs"] == 0
    assert result["renewable_share_abs"] == 0
