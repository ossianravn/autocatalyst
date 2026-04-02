#!/usr/bin/env python3
"""Compute AutoCatalyst convergence status from session logs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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


def split_rows(rows: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    config = None
    rounds: list[dict[str, Any]] = []
    for row in rows:
        if row.get("type") == "config":
            config = row
            rounds = []
        elif row.get("type") == "round":
            rounds.append(row)
    return config, rounds


def load_session(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = load_rows(root / "autocatalyst.jsonl")
    config, rounds = split_rows(rows)
    if config is None:
        raise ValueError("autocatalyst.jsonl must start with a config row")
    return config, rounds


def round_streak_effect(round_row: dict[str, Any]) -> str:
    winner = str(round_row.get("winner", "")).upper()
    status = str(round_row.get("status", "")).lower()

    if winner == "A" and status == "keep":
        return "increment"
    if winner in {"B", "AB"} and status == "promote":
        return "reset"
    return "noop"


def current_survival_streak(rounds: list[dict[str, Any]]) -> int:
    streak = 0
    for round_row in rounds:
        effect = round_streak_effect(round_row)
        if effect == "increment":
            streak += 1
        elif effect == "reset":
            streak = 0
    return streak


def convergence_status(config: dict[str, Any], rounds: list[dict[str, Any]]) -> dict[str, Any]:
    survival_target = int(config.get("survivalTarget", 2) or 2)
    streak = current_survival_streak(rounds)
    latest = rounds[-1] if rounds else None
    should_stop = bool(rounds) and survival_target > 0 and streak >= survival_target

    if not rounds:
        reason = "No rounds logged yet."
    elif should_stop:
        reason = (
            f"Stop: incumbent survival streak reached the target "
            f"({streak}/{survival_target})."
        )
    else:
        reason = (
            f"Continue: incumbent survival streak is below the target "
            f"({streak}/{survival_target})."
        )

    return {
        "survivalTarget": survival_target,
        "currentSurvivalStreak": streak,
        "roundCount": len(rounds),
        "latestRound": int(latest.get("round", 0)) if latest else 0,
        "latestWinner": str(latest.get("winner", "")) if latest else "",
        "shouldStop": should_stop,
        "decision": "stop" if should_stop else "continue",
        "reason": reason,
    }
