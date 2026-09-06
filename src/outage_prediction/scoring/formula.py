"""The fixed regression formula used by the original project."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

REQUIRED_FEATURES = (
    "drought",
    "heat",
    "cold",
    "pv_share",
    "wind_share",
    "hydro_share",
)


@dataclass(frozen=True, slots=True)
class FormulaRiskModel:
    """Deterministic implementation of the original Excel regression formula."""

    version: str = "legacy-formula-v1"
    name: str = "fixed_regression_formula"

    def predict(self, features: pd.DataFrame) -> pd.DataFrame:
        missing = sorted(set(REQUIRED_FEATURES) - set(features.columns))
        if missing:
            raise ValueError(f"Risk features are missing required columns: {missing}")

        values = (
            features.loc[:, REQUIRED_FEATURES]
            .apply(pd.to_numeric, errors="coerce")
            .astype(float)
        )
        d = values["drought"]
        h = values["heat"]
        c = values["cold"]
        pv = values["pv_share"]
        wind = values["wind_share"]
        hydro = values["hydro_share"]

        terms = {
            "term_drought": -0.0019 * d,
            "term_heat": -0.0057 * h,
            "term_cold": 0.0063 * c,
            "term_drought_hydro": 0.0413 * d * hydro,
            "term_heat_hydro": -0.0030 * h * hydro,
            "term_cold_hydro": -0.0116 * c * hydro,
            "term_drought_wind": -0.0196 * d * wind,
            "term_heat_wind": 0.01801 * h * wind,
            "term_cold_wind": 0.0398 * c * wind,
            "term_drought_pv": 0.2084 * d * pv,
            "term_heat_pv": 0.0764 * h * pv,
            "term_cold_pv": 0.4810 * c * pv,
        }
        climate = terms["term_drought"] + terms["term_heat"] + terms["term_cold"]
        climate_terms = {"term_drought", "term_heat", "term_cold"}
        renewable = sum(
            value for name, value in terms.items() if name not in climate_terms
        )
        risk = climate + renewable
        denominator = climate.abs() + renewable.abs()
        climate_share = np.where(denominator > 0, climate.abs() / denominator, 0.0)
        renewable_share = np.where(denominator > 0, renewable.abs() / denominator, 0.0)

        return pd.DataFrame(
            {
                **terms,
                "risk_score": risk,
                "climate_contribution": climate,
                "renewable_interaction_contribution": renewable,
                "climate_share_abs": climate_share,
                "renewable_share_abs": renewable_share,
                "model_name": self.name,
                "model_version": self.version,
            },
            index=features.index,
        )

    def explain(
        self,
        features: pd.DataFrame,
        predictions: pd.DataFrame,
    ) -> pd.DataFrame:
        columns = [
            "climate_contribution",
            "renewable_interaction_contribution",
            "climate_share_abs",
            "renewable_share_abs",
        ]
        return predictions.loc[:, columns].copy()
