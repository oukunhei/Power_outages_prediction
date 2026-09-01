from __future__ import annotations

from pathlib import Path

from outage_prediction.config import load_config

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_confirmed_hdd_threshold_is_3000() -> None:
    config = load_config(PROJECT_ROOT / "config" / "project.yaml")
    assert config["thresholds"]["heating_degree_days"] == 3000.0
