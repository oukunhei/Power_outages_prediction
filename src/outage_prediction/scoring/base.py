"""Common contract for formula and future machine-learning risk models."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class RiskModel(Protocol):
    """A model that converts versioned country features into relative risk scores."""

    name: str
    version: str

    def predict(self, features: pd.DataFrame) -> pd.DataFrame:
        """Return one prediction row for every input feature row."""

    def explain(
        self,
        features: pd.DataFrame,
        predictions: pd.DataFrame,
    ) -> pd.DataFrame | None:
        """Return optional grouped model contributions."""
