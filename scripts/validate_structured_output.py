#!/usr/bin/env python3
"""Extract and validate structured JSON blocks from AutoCatalyst role outputs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


FENCED_JSON_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)

SCHEMAS: dict[str, dict[str, Any]] = {
    "judge": {
        "schema": "autocatalyst.judge.v1",
        "required": {
            "ranking": list,
            "winner": str,
            "rationale": str,
            "blockers": list,
        },
    },
    "critic": {
        "schema": "autocatalyst.critic.v1",
        "required": {
            "rewriteWarranted": bool,
            "hardBlockers": list,
            "softConcerns": list,
            "suggestedRubricItems": list,
        },
    },
    "researcher": {
        "schema": "autocatalyst.researcher.v1",
        "required": {
            "confirmedFacts": list,
            "unresolvedQuestions": list,
            "implications": list,
            "conflicts": list,
        },
    },
    "tribunal": {
        "schema": "autocatalyst.tribunal.v1",
        "required": {
            "round": int,
            "candidateMapArtifact": str,
            "judgePackets": list,
            "judgeVerdicts": list,
            "aggregationMethod": str,
            "result": str,
            "note": str,
        },
    },
}


def extract_json_block(text: str) -> dict[str, Any]:
    matches = list(FENCED_JSON_RE.finditer(text))
    if not matches:
        raise ValueError("No fenced JSON block found.")
    payload = matches[-1].group(1)
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Structured output must be a JSON object.")
    return data


def extract_json_payload(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Structured output must be a JSON object.")
        return data
    return extract_json_block(path.read_text(encoding="utf-8"))


def require_string_list(value: Any, *, field: str) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field} must be a non-empty-string array.")


def require_optional_string_list(value: Any, *, field: str) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field} must contain only non-empty strings.")


def validate_judge(data: dict[str, Any]) -> None:
    require_string_list(data["ranking"], field="ranking")
    winner = data["winner"]
    if winner not in data["ranking"]:
        raise ValueError("winner must appear in ranking.")
    blockers = data["blockers"]
    if not isinstance(blockers, list):
        raise ValueError("blockers must be an array.")
    for item in blockers:
        if not isinstance(item, dict):
            raise ValueError("each blocker must be an object.")
        if not isinstance(item.get("candidate"), str) or not item["candidate"].strip():
            raise ValueError("each blocker must include candidate.")
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise ValueError("each blocker must include reason.")


def validate_critic(data: dict[str, Any]) -> None:
    for field in ("hardBlockers", "softConcerns", "suggestedRubricItems"):
        value = data[field]
        if not isinstance(value, list):
            raise ValueError(f"{field} must be an array.")
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise ValueError(f"{field} must contain only non-empty strings.")


def validate_researcher(data: dict[str, Any]) -> None:
    confirmed = data["confirmedFacts"]
    if not isinstance(confirmed, list):
        raise ValueError("confirmedFacts must be an array.")
    for item in confirmed:
        if not isinstance(item, dict):
            raise ValueError("each confirmed fact must be an object.")
        if not isinstance(item.get("claim"), str) or not item["claim"].strip():
            raise ValueError("each confirmed fact must include claim.")
        if not isinstance(item.get("citation"), str) or not item["citation"].strip():
            raise ValueError("each confirmed fact must include citation.")
    for field in ("unresolvedQuestions", "implications", "conflicts"):
        value = data[field]
        if not isinstance(value, list):
            raise ValueError(f"{field} must be an array.")
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise ValueError(f"{field} must contain only non-empty strings.")


def validate_tribunal(data: dict[str, Any]) -> None:
    require_optional_string_list(data["judgePackets"], field="judgePackets")
    verdicts = data["judgeVerdicts"]
    if not isinstance(verdicts, list):
        raise ValueError("judgeVerdicts must be an array.")
    for item in verdicts:
        if not isinstance(item, dict):
            raise ValueError("each judgeVerdicts item must be an object.")
        for field in ("judge", "artifact", "winner", "rationale"):
            if not isinstance(item.get(field), str):
                raise ValueError(f"each judge verdict must include {field}.")
        ranking = item.get("ranking", [])
        if ranking:
            require_string_list(ranking, field="ranking")
        blockers = item.get("blockers", [])
        if not isinstance(blockers, list):
            raise ValueError("judge verdict blockers must be an array.")
        for blocker in blockers:
            if not isinstance(blocker, dict):
                raise ValueError("each blocker must be an object.")
            if not isinstance(blocker.get("candidate"), str) or not isinstance(blocker.get("reason"), str):
                raise ValueError("each blocker must include candidate and reason strings.")


def validate_payload(role: str, data: dict[str, Any]) -> None:
    spec = SCHEMAS[role]
    expected_schema = spec["schema"]
    if data.get("schema") != expected_schema:
        raise ValueError(f"schema must be {expected_schema!r}.")

    for field, expected_type in spec["required"].items():
        if field not in data:
            raise ValueError(f"missing required field: {field}")
        if not isinstance(data[field], expected_type):
            raise ValueError(f"{field} must be of type {expected_type.__name__}.")

    if role == "judge":
        validate_judge(data)
    elif role == "critic":
        validate_critic(data)
    elif role == "researcher":
        validate_researcher(data)
    elif role == "tribunal":
        validate_tribunal(data)


def load_and_validate(role: str, path: Path) -> dict[str, Any]:
    data = extract_json_payload(path)
    validate_payload(role, data)
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate structured JSON blocks from AutoCatalyst role outputs")
    parser.add_argument("--role", required=True, choices=sorted(SCHEMAS))
    parser.add_argument("--file", required=True, help="path to the saved agent output")
    args = parser.parse_args()

    path = Path(args.file).resolve()
    data = load_and_validate(args.role, path)
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
