from __future__ import annotations

from pathlib import Path

from outage_prediction.pipeline import reproduce_legacy_results
from outage_prediction.scoring.formula import FormulaRiskModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_all_legacy_excel_results_are_reproduced() -> None:
    _, report = reproduce_legacy_results(
        PROJECT_ROOT / "data" / "legacy" / "parameters.xlsx",
        FormulaRiskModel(),
    )
    assert report["status"] == "PASS"
    assert report["rows"] == 199
    assert report["matched_rows"] == 199
    assert report["maximum_absolute_error"] <= 1e-12
