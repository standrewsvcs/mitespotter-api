"""
tools/check_coverage.py
Fail if any measured file is below the per-file coverage threshold.

Usage: uv run coverage json -o coverage.json && uv run python tools/check_coverage.py coverage.json [threshold]

Created: 2026-11-07
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

import json
import sys


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else "coverage.json"
    threshold = float(argv[2]) if len(argv) > 2 else 85.0
    with open(path, encoding="utf-8") as f:
        files = json.load(f)["files"]

    failing = {
        name: data["summary"]["percent_covered"]
        for name, data in files.items()
        if data["summary"]["num_statements"] and data["summary"]["percent_covered"] < threshold
    }
    for name, percent in sorted(failing.items()):
        print(f"{name}: {percent:.1f}% < {threshold:.0f}%")
    if not failing:
        print(f"All {len(files)} files at or above {threshold:.0f}%")
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
