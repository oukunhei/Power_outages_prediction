"""Command-line entry points for reproducible builds."""

from __future__ import annotations

import argparse
from pathlib import Path

from outage_prediction.pipeline import build_legacy_release


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the power-outage risk frontend release.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser(
        "build-legacy",
        help="Reproduce the old workbook and publish results with confirmed thresholds.",
    )
    build.add_argument("--config", type=Path, default=Path("config/project.yaml"))
    args = parser.parse_args()

    if args.command == "build-legacy":
        project_root = _project_root()
        config_path = args.config
        if not config_path.is_absolute():
            config_path = project_root / config_path
        output = build_legacy_release(config_path, project_root)
        print(f"Published frontend data: {output}")


if __name__ == "__main__":
    main()
