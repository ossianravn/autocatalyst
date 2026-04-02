#!/usr/bin/env python3
"""Print the current AutoCatalyst convergence decision for a repository."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from convergence import convergence_status, load_session


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether AutoCatalyst should continue or stop")
    parser.add_argument("--root", default=".", help="repository root or working directory")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    config, rounds = load_session(root)
    print(json.dumps(convergence_status(config, rounds), indent=2))


if __name__ == "__main__":
    main()
