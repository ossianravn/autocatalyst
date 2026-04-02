#!/usr/bin/env python3
"""Append a structured AutoCatalyst round row and refresh derived artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from convergence import convergence_status, split_rows
from render_dashboard import render_dashboard, write_artifacts

VALID_STATUS = {"promote", "keep", "mixed", "blocked", "rejected"}
VALID_WINNERS = {"A", "B", "AB"}
VALID_HARD_CHECKS = {"pass", "fail", "mixed", "na"}
VALID_EVIDENCE = {"judge-first", "benchmark-first", "hybrid"}


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def append_round(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Append an AutoCatalyst round log row")
    parser.add_argument("--root", default=".", help="repository root or working directory")
    parser.add_argument("--round", required=True, type=int)
    parser.add_argument("--winner", required=True, choices=sorted(VALID_WINNERS))
    parser.add_argument("--status", required=True, choices=sorted(VALID_STATUS))
    parser.add_argument("--winner-reason", default="")
    parser.add_argument("--evidence-mode", choices=sorted(VALID_EVIDENCE))
    parser.add_argument("--hard-checks", default="na", choices=sorted(VALID_HARD_CHECKS))
    parser.add_argument("--judge-ranking", nargs="*", default=[])
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--promotion", action="append", default=[])
    parser.add_argument("--agent-name", action="append", default=[])
    parser.add_argument("--incumbent-before", default="")
    parser.add_argument("--incumbent-after", default="")
    parser.add_argument("--benchmark-summary", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--degraded-mode", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    jsonl_path = root / "autocatalyst.jsonl"
    rows = load_rows(jsonl_path)
    if not rows or rows[0].get("type") != "config":
        raise SystemExit("autocatalyst.jsonl must exist and start with a config row. Run init_session.py first.")

    row: dict[str, Any] = {
        "type": "round",
        "round": args.round,
        "winner": args.winner,
        "status": args.status,
        "winnerReason": args.winner_reason,
        "hardChecks": args.hard_checks,
        "judgeRanking": args.judge_ranking,
        "artifacts": args.artifact,
        "promotions": args.promotion,
        "agentNames": args.agent_name,
        "degradedMode": args.degraded_mode,
    }
    if args.evidence_mode:
        row["evidenceMode"] = args.evidence_mode
    if args.incumbent_before:
        row["incumbentBefore"] = args.incumbent_before
    if args.incumbent_after:
        row["incumbentAfter"] = args.incumbent_after
    if args.benchmark_summary:
        row["benchmarkSummary"] = args.benchmark_summary
    if args.notes:
        row["notes"] = args.notes

    append_round(jsonl_path, row)
    dashboard = render_dashboard(root)
    (root / "autocatalyst-dashboard.md").write_text(dashboard, encoding="utf-8")
    write_artifacts(root)
    _, updated_rounds = split_rows(load_rows(jsonl_path))
    convergence = convergence_status(rows[0], updated_rounds)
    print(
        f"logged round {args.round} in {jsonl_path} — "
        f"{convergence['decision']}: {convergence['reason']}"
    )


if __name__ == "__main__":
    main()
