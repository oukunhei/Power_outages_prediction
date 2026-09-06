"""Risk-model factory used by the pipeline."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from outage_prediction.scoring.base import RiskModel
from outage_prediction.scoring.formula import FormulaRiskModel


def create_risk_model(config: Mapping[str, object]) -> RiskModel:
    model_type = str(config.get("type", "formula"))
    version = str(config.get("version", "fixed-formula-v2-hdd3000"))
    if model_type == "formula":
        return FormulaRiskModel(version=version)
    if model_type == "machine_learning":
        artifact = config.get("artifact_path")
        if not artifact or not Path(str(artifact)).is_file():
            raise ValueError("The configured machine-learning model artifact does not exist.")
        raise NotImplementedError(
            "MachineLearningRiskModel is an extension point; inference is not implemented yet."
        )
    raise ValueError(f"Unsupported risk model type: {model_type}")
