"""Project configuration loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(config_path: Path) -> dict[str, Any]:
    config_path = config_path.resolve()
    with config_path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError(f"Configuration must be a mapping: {config_path}")

    thresholds = config.get("thresholds", {})
    if float(thresholds.get("heating_degree_days", -1)) != 3000.0:
        raise ValueError("The confirmed HDD threshold must be 3000 degree-days.")
    return config


def resolve_project_path(project_root: Path, configured_path: str) -> Path:
    path = (project_root / configured_path).resolve()
    if not path.is_relative_to(project_root.resolve()):
        raise ValueError(f"Configured path escapes the project repository: {configured_path}")
    return path
