#!/usr/bin/env python3
"""Append a structured AutoCatalyst round row and refresh derived artifacts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from convergence import convergence_status, split_rows
from render_dashboard import render_dashboard, write_artifacts
from validate_structured_output import load_and_validate

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


def resolve_repo_path(root: Path, path_str: str) -> Path:
    candidate = Path(path_str)
    if candidate.is_absolute():
        return candidate
    return (root / candidate).resolve()


def to_repo_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def parse_named_paths(specs: list[str], *, prefix: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for index, spec in enumerate(specs, start=1):
        raw = str(spec).strip()
        if not raw:
            continue
        if "=" in raw:
            name, path = raw.split("=", 1)
            judge = name.strip() or f"{prefix}{index}"
            artifact = path.strip()
        else:
            judge = f"{prefix}{index}"
            artifact = raw
        if artifact:
            items.append({"judge": judge, "artifact": artifact})
    return items


def parse_named_rankings(specs: list[str], *, prefix: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, spec in enumerate(specs, start=1):
        raw = str(spec).strip()
        if not raw:
            continue
        if "=" in raw:
            name, ranking_text = raw.split("=", 1)
            judge = name.strip() or f"{prefix}{index}"
        else:
            judge = f"{prefix}{index}"
            ranking_text = raw
        ranking = [part.strip() for part in ranking_text.split(">") if part.strip()]
        items.append({"judge": judge, "ranking": ranking})
    return items


def load_structured_output(root: Path, role: str, path_str: str) -> dict[str, Any]:
    path = resolve_repo_path(root, path_str)
    if not path.exists():
        raise FileNotFoundError(f"Missing {role} output artifact: {path_str}")
    return load_and_validate(role, path)


def judge_key_from_path(path_str: str, fallback_index: int) -> str:
    name = Path(path_str).name.lower()
    match = re.search(r"judge[-_]?(\d+)", name)
    if match:
        return f"judge{match.group(1)}"
    return f"judge{fallback_index}"


def infer_companion_artifacts(root: Path, artifact_paths: list[str]) -> list[str]:
    inferred: list[str] = []
    for path_str in artifact_paths:
        path = resolve_repo_path(root, path_str)
        if path.name.endswith("-tribunal-summary.md"):
            candidate = path.with_suffix(".json")
            if candidate.exists():
                inferred.append(to_repo_path(root, candidate))
        elif path.name.endswith("-tribunal-summary.json"):
            candidate = path.with_suffix(".md")
            if candidate.exists():
                inferred.append(to_repo_path(root, candidate))
    return list(dict.fromkeys(inferred))


def discover_structured_artifacts(root: Path, artifact_paths: list[str]) -> dict[str, Any]:
    discovered: dict[str, Any] = {
        "critic": None,
        "research": None,
        "candidateMapArtifact": "",
        "summaryArtifact": "",
        "summaryDataArtifact": "",
        "summaryData": None,
        "judgePackets": [],
        "judgeVerdicts": [],
    }

    for path_str in artifact_paths:
        lowered = Path(path_str).name.lower()

        if "candidate-map" in lowered and lowered.endswith(".json") and not discovered["candidateMapArtifact"]:
            discovered["candidateMapArtifact"] = path_str
            continue

        if "tribunal-summary" in lowered and lowered.endswith(".md") and not discovered["summaryArtifact"]:
            discovered["summaryArtifact"] = path_str
            continue

        if "tribunal-summary" in lowered and lowered.endswith(".json") and not discovered["summaryDataArtifact"]:
            try:
                discovered["summaryData"] = load_structured_output(root, "tribunal", path_str)
                discovered["summaryDataArtifact"] = path_str
            except Exception:
                pass
            continue

        if "judge-" in lowered and "packet" in lowered:
            discovered["judgePackets"].append(path_str)
            continue

        if "judge-" in lowered and "verdict" in lowered:
            try:
                payload = load_structured_output(root, "judge", path_str)
            except Exception:
                continue
            discovered["judgeVerdicts"].append(
                {
                    "judge": judge_key_from_path(path_str, len(discovered["judgeVerdicts"]) + 1),
                    "artifact": path_str,
                    "ranking": payload["ranking"],
                    "winner": payload["winner"],
                    "rationale": payload["rationale"],
                    "blockers": payload["blockers"],
                }
            )
            continue

        if "critic" in lowered and discovered["critic"] is None:
            try:
                payload = load_structured_output(root, "critic", path_str)
            except Exception:
                continue
            discovered["critic"] = {"artifact": path_str, "data": payload}
            continue

        if "research" in lowered and discovered["research"] is None:
            try:
                payload = load_structured_output(root, "researcher", path_str)
            except Exception:
                continue
            discovered["research"] = {"artifact": path_str, "data": payload}

    discovered["judgePackets"] = list(dict.fromkeys(discovered["judgePackets"]))
    discovered["judgeVerdicts"] = list(
        {item["judge"]: item for item in discovered["judgeVerdicts"]}.values()
    )
    return discovered


def write_tribunal_summary_companion(
    root: Path,
    *,
    path_str: str,
    round_no: int,
    candidate_map_artifact: str,
    judge_packets: list[str],
    judge_verdicts: list[dict[str, Any]],
    aggregation_method: str,
    result: str,
    note: str,
) -> None:
    payload = {
        "schema": "autocatalyst.tribunal.v1",
        "round": round_no,
        "candidateMapArtifact": candidate_map_artifact,
        "judgePackets": judge_packets,
        "judgeVerdicts": judge_verdicts,
        "aggregationMethod": aggregation_method,
        "result": result,
        "note": note,
    }
    resolve_repo_path(root, path_str).write_text(json.dumps(payload, indent=2), encoding="utf-8")


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
    parser.add_argument("--judge-verdict-artifact", action="append", default=[])
    parser.add_argument("--judge-panel-ranking", action="append", default=[])
    parser.add_argument("--candidate-map-artifact", default="")
    parser.add_argument("--tribunal-summary-artifact", default="")
    parser.add_argument("--aggregation-method", default="")
    parser.add_argument("--critic-output-artifact", default="")
    parser.add_argument("--researcher-output-artifact", default="")
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

    artifact_paths = [path for path in args.artifact if str(path).strip()]
    artifact_paths.extend(infer_companion_artifacts(root, artifact_paths))
    if args.critic_output_artifact.strip() and args.critic_output_artifact not in artifact_paths:
        artifact_paths.append(args.critic_output_artifact.strip())
    if args.researcher_output_artifact.strip() and args.researcher_output_artifact not in artifact_paths:
        artifact_paths.append(args.researcher_output_artifact.strip())
    discovered = discover_structured_artifacts(root, artifact_paths)
    if discovered["summaryDataArtifact"] and discovered["summaryDataArtifact"] not in artifact_paths:
        artifact_paths.append(discovered["summaryDataArtifact"])
    row["artifacts"] = artifact_paths
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

    critic_artifact = args.critic_output_artifact.strip() or (
        discovered["critic"]["artifact"] if isinstance(discovered.get("critic"), dict) else ""
    )
    if critic_artifact:
        critic_data = (
            load_structured_output(root, "critic", critic_artifact)
            if args.critic_output_artifact.strip()
            else discovered["critic"]["data"]
        )
        row["critic"] = {
            "artifact": critic_artifact,
            "rewriteWarranted": bool(critic_data["rewriteWarranted"]),
            "hardBlockers": critic_data["hardBlockers"],
            "softConcerns": critic_data["softConcerns"],
            "suggestedRubricItems": critic_data["suggestedRubricItems"],
        }

    researcher_artifact = args.researcher_output_artifact.strip() or (
        discovered["research"]["artifact"] if isinstance(discovered.get("research"), dict) else ""
    )
    if researcher_artifact:
        researcher_data = (
            load_structured_output(root, "researcher", researcher_artifact)
            if args.researcher_output_artifact.strip()
            else discovered["research"]["data"]
        )
        row["research"] = {
            "artifact": researcher_artifact,
            "confirmedFacts": researcher_data["confirmedFacts"],
            "unresolvedQuestions": researcher_data["unresolvedQuestions"],
            "implications": researcher_data["implications"],
            "conflicts": researcher_data["conflicts"],
        }

    judge_verdicts = parse_named_paths(args.judge_verdict_artifact, prefix="judge")
    judge_rankings = parse_named_rankings(args.judge_panel_ranking, prefix="judge")
    auto_verdicts = discovered["judgeVerdicts"]
    merged_verdicts: dict[str, dict[str, Any]] = {
        item["judge"]: dict(item) for item in auto_verdicts
    }
    for item in judge_verdicts:
        structured = load_structured_output(root, "judge", item["artifact"])
        merged_verdicts[item["judge"]] = {
            "judge": item["judge"],
            "artifact": item["artifact"],
            "ranking": structured["ranking"],
            "winner": structured["winner"],
            "rationale": structured["rationale"],
            "blockers": structured["blockers"],
        }
    if any(
        [
            args.candidate_map_artifact.strip(),
            args.tribunal_summary_artifact.strip(),
            args.aggregation_method.strip(),
            merged_verdicts,
            judge_rankings,
            discovered["candidateMapArtifact"],
            discovered["summaryArtifact"],
            discovered["summaryDataArtifact"],
            discovered["judgePackets"],
        ]
    ):
        for item in judge_rankings:
            bucket = merged_verdicts.setdefault(
                item["judge"],
                {"judge": item["judge"], "artifact": "", "ranking": [], "winner": "", "rationale": "", "blockers": []},
            )
            bucket["ranking"] = item["ranking"]

        tribunal_data = discovered["summaryData"] if isinstance(discovered.get("summaryData"), dict) else {}
        candidate_map_artifact = args.candidate_map_artifact.strip() or discovered["candidateMapArtifact"] or str(tribunal_data.get("candidateMapArtifact", "")).strip()
        summary_artifact = args.tribunal_summary_artifact.strip() or discovered["summaryArtifact"]
        summary_data_artifact = discovered["summaryDataArtifact"]
        if not summary_data_artifact and summary_artifact:
            summary_candidate = resolve_repo_path(root, summary_artifact).with_suffix(".json")
            summary_data_artifact = to_repo_path(root, summary_candidate)
            if summary_data_artifact not in artifact_paths:
                artifact_paths.append(summary_data_artifact)
        judge_packets = discovered["judgePackets"] or list(tribunal_data.get("judgePackets", []))
        aggregation_method = args.aggregation_method.strip() or str(tribunal_data.get("aggregationMethod", "")).strip()
        tribunal_result = str(tribunal_data.get("result", "")).strip() or args.winner
        tribunal_note = str(tribunal_data.get("note", "")).strip() or args.winner_reason

        if summary_data_artifact:
            write_tribunal_summary_companion(
                root,
                path_str=summary_data_artifact,
                round_no=args.round,
                candidate_map_artifact=candidate_map_artifact,
                judge_packets=judge_packets,
                judge_verdicts=list(merged_verdicts.values()),
                aggregation_method=aggregation_method,
                result=tribunal_result,
                note=tribunal_note,
            )

        row["tribunal"] = {
            "candidateMapArtifact": candidate_map_artifact,
            "summaryArtifact": summary_artifact,
            "summaryDataArtifact": summary_data_artifact,
            "judgePackets": judge_packets,
            "aggregationMethod": aggregation_method,
            "result": tribunal_result,
            "note": tribunal_note,
            "judgeVerdicts": list(merged_verdicts.values()),
        }

    row["artifacts"] = list(dict.fromkeys(artifact_paths))

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
