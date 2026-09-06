"""Command-line entry points for reproducible builds."""

from __future__ import annotations

import argparse
from pathlib import Path

from outage_prediction.pipeline import build_legacy_release, build_release


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the power-outage risk frontend release.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    full_build = subparsers.add_parser(
        "build",
        help="Build production outputs from raw GIPT and CMIP5 snapshots.",
    )
    full_build.add_argument("--config", type=Path, default=Path("config/project.yaml"))
    legacy_build = subparsers.add_parser(
        "build-legacy",
        help="Reproduce the old workbook and publish results with confirmed thresholds.",
    )
    legacy_build.add_argument("--config", type=Path, default=Path("config/project.yaml"))
    args = parser.parse_args()

    project_root = _project_root()
    config_path = args.config
    if not config_path.is_absolute():
        config_path = project_root / config_path
    if args.command == "build":
        output = build_release(config_path, project_root)
        print(f"Published frontend data: {output}")
    elif args.command == "build-legacy":
        output = build_legacy_release(config_path, project_root)
        print(f"Published frontend data: {output}")


if __name__ == "__main__":
    main()
