#!/usr/bin/env python3
"""Prepare truly blind judge packets plus parent-only mapping artifacts for a round."""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path


def read_required(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return path.read_text(encoding="utf-8")


def parse_candidate_specs(root: Path, specs: list[str]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    seen_labels: set[str] = set()
    for spec in specs:
        if "=" not in spec:
            raise ValueError(f"Candidate spec must be LABEL=PATH, got: {spec}")
        label, raw_path = spec.split("=", 1)
        label = label.strip()
        if not label:
            raise ValueError(f"Candidate label cannot be empty: {spec}")
        if label in seen_labels:
            raise ValueError(f"Duplicate candidate label: {label}")
        seen_labels.add(label)
        path = (root / raw_path).resolve()
        candidates.append(
            {
                "label": label,
                "path": str(path),
                "relativePath": str(path.relative_to(root)),
                "content": read_required(path),
            }
        )
    if len(candidates) < 2:
        raise ValueError("Provide at least two candidates with --candidate LABEL=PATH")
    return candidates


def packet_markdown(
    round_no: int,
    judge_index: int,
    anchor_path: str,
    anchor_text: str,
    rubric_path: str,
    rubric_text: str,
    aliases: list[dict[str, str]],
) -> str:
    lines = [
        f"# Blind Judge Packet: Round {round_no} / Judge {judge_index}",
        "",
        "Evaluate the candidates strictly against the anchor and rubric.",
        "Do not infer provenance, authorship, or whether any candidate is the incumbent, rewrite, or synthesis.",
        "Use the aliases exactly as written and rank them best to worst with no ties.",
        "",
        f"## Anchor (`{anchor_path}`)",
        "",
        anchor_text.rstrip(),
        "",
        f"## Rubric (`{rubric_path}`)",
        "",
        rubric_text.rstrip(),
        "",
        "## Candidates",
        "",
    ]
    for alias in aliases:
        lines.extend(
            [
                f"### {alias['alias']}",
                "",
                "```",
                alias["content"].rstrip(),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def tribunal_summary_markdown(
    round_no: int,
    map_path: str,
    packet_paths: list[str],
    summary_json_path: str,
) -> str:
    lines = [
        f"# Round {round_no} Tribunal Summary",
        "",
        "## Blind setup",
        "",
        f"- candidate map: `{map_path}`",
        f"- structured summary: `{summary_json_path}`",
        "- judge packet order is permuted separately for each judge",
        "",
        "## Judge packets",
        "",
    ]
    for packet_path in packet_paths:
        lines.append(f"- `{packet_path}`")
    lines.extend(
        [
            "",
            "## Verdict collection",
            "",
            "- judge 1: pending",
            "- judge 2: pending",
            "- judge 3: pending",
            "",
            "## Aggregation",
            "",
            "- pending",
            "",
        ]
    )
    return "\n".join(lines)


def tribunal_summary_payload(
    round_no: int,
    map_path: str,
    packet_paths: list[str],
) -> dict[str, object]:
    return {
        "schema": "autocatalyst.tribunal.v1",
        "round": round_no,
        "candidateMapArtifact": map_path,
        "judgePackets": packet_paths,
        "judgeVerdicts": [],
        "aggregationMethod": "",
        "result": "",
        "note": "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare blinded judge packets for an AutoCatalyst round")
    parser.add_argument("--root", default=".", help="repository root or working directory")
    parser.add_argument("--round", required=True, type=int, help="round number")
    parser.add_argument("--anchor", required=True, help="path to the anchor document")
    parser.add_argument("--rubric", required=True, help="path to the rubric file")
    parser.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="candidate specification as LABEL=PATH; repeat for each candidate",
    )
    parser.add_argument("--judge-count", type=int, default=3, help="number of judge packets to create")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    anchor_path = (root / args.anchor).resolve()
    rubric_path = (root / args.rubric).resolve()
    anchor_text = read_required(anchor_path)
    rubric_text = read_required(rubric_path)
    candidates = parse_candidate_specs(root, args.candidate)

    rounds_dir = root / "autocatalyst-artifacts" / "rounds"
    rounds_dir.mkdir(parents=True, exist_ok=True)

    packet_paths: list[str] = []
    map_payload: dict[str, object] = {
        "round": args.round,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "anchor": str(anchor_path.relative_to(root)),
        "rubric": str(rubric_path.relative_to(root)),
        "candidates": [
            {"label": item["label"], "path": item["relativePath"]}
            for item in candidates
        ],
        "perJudge": {},
    }

    rng = random.SystemRandom()
    generic_aliases = [f"Candidate {idx}" for idx in range(1, len(candidates) + 1)]

    for judge_index in range(1, args.judge_count + 1):
        shuffled = candidates[:]
        rng.shuffle(shuffled)
        blinded = []
        for alias, candidate in zip(generic_aliases, shuffled):
            blinded.append(
                {
                    "alias": alias,
                    "label": candidate["label"],
                    "path": candidate["relativePath"],
                    "content": candidate["content"],
                }
            )

        packet_name = f"round-{args.round:03d}-judge-{judge_index}-packet.md"
        packet_path = rounds_dir / packet_name
        packet_path.write_text(
            packet_markdown(
                round_no=args.round,
                judge_index=judge_index,
                anchor_path=str(anchor_path.relative_to(root)),
                anchor_text=anchor_text,
                rubric_path=str(rubric_path.relative_to(root)),
                rubric_text=rubric_text,
                aliases=blinded,
            ),
            encoding="utf-8",
        )
        packet_paths.append(str(packet_path.relative_to(root)))
        map_payload["perJudge"][f"judge{judge_index}"] = [
            {"alias": item["alias"], "label": item["label"], "path": item["path"]}
            for item in blinded
        ]

    map_name = f"round-{args.round:03d}-candidate-map.json"
    map_path = rounds_dir / map_name
    map_path.write_text(json.dumps(map_payload, indent=2), encoding="utf-8")

    summary_json_name = f"round-{args.round:03d}-tribunal-summary.json"
    summary_json_path = rounds_dir / summary_json_name
    summary_json_payload = tribunal_summary_payload(
        round_no=args.round,
        map_path=str(map_path.relative_to(root)),
        packet_paths=packet_paths,
    )
    summary_json_path.write_text(json.dumps(summary_json_payload, indent=2), encoding="utf-8")

    summary_name = f"round-{args.round:03d}-tribunal-summary.md"
    summary_path = rounds_dir / summary_name
    summary_path.write_text(
        tribunal_summary_markdown(
            round_no=args.round,
            map_path=str(map_path.relative_to(root)),
            packet_paths=packet_paths,
            summary_json_path=str(summary_json_path.relative_to(root)),
        ),
        encoding="utf-8",
    )

    result = {
        "candidate_map": str(map_path.relative_to(root)),
        "judge_packets": packet_paths,
        "tribunal_summary": str(summary_path.relative_to(root)),
        "tribunal_summary_json": str(summary_json_path.relative_to(root)),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
