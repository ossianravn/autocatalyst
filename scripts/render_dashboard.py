#!/usr/bin/env python3
"""Render AutoCatalyst markdown dashboards, Mermaid artifacts, and browser reports."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from convergence import convergence_status, load_session


MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            row["__sourceSpan"] = {
                "file": path.name,
                "heading": str(row.get("type", "row")),
                "startLine": line_no,
                "endLine": line_no,
            }
        rows.append(row)
    return rows


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str):
        if not value.strip():
            return []
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(value)]


def sanitize(text: Any) -> str:
    value = str(text)
    replacements = [
        ("\n", " "),
        ("\r", " "),
        ('"', "'"),
        ("[", "("),
        ("]", ")"),
        ("{", "("),
        ("}", ")"),
        ("|", "/"),
        ("`", "'"),
    ]
    for old, new in replacements:
        value = value.replace(old, new)
    return " ".join(value.split())


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


def jsonl_span(row: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not row:
        return []
    span = row.get("__sourceSpan")
    if isinstance(span, dict):
        return [span]
    return []


def parse_markdown_sections(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}

    sections: dict[str, dict[str, Any]] = {}
    current_heading: str | None = None
    current_heading_line = 0
    current_lines: list[tuple[int, str]] = []

    def flush_section() -> None:
        if current_heading is None:
            return

        items: list[dict[str, Any]] = []
        paragraphs: list[dict[str, Any]] = []
        keyed_items: dict[str, dict[str, Any]] = {}
        paragraph_lines: list[tuple[int, str]] = []

        def flush_paragraph() -> None:
            if not paragraph_lines:
                return
            text = " ".join(part.strip() for _, part in paragraph_lines if part.strip())
            paragraphs.append(
                {
                    "text": text,
                    "startLine": paragraph_lines[0][0],
                    "endLine": paragraph_lines[-1][0],
                }
            )
            paragraph_lines.clear()

        for line_no, raw_line in current_lines:
            stripped = raw_line.strip()
            if not stripped:
                flush_paragraph()
                continue
            if stripped.startswith("- "):
                flush_paragraph()
                item_text = stripped[2:].strip()
                item = {
                    "text": item_text,
                    "startLine": line_no,
                    "endLine": line_no,
                }
                items.append(item)
                if ":" in item_text:
                    key, value = item_text.split(":", 1)
                    keyed_items[key.strip().lower()] = {
                        "text": value.strip(),
                        "startLine": line_no,
                        "endLine": line_no,
                    }
                continue
            paragraph_lines.append((line_no, stripped))

        flush_paragraph()
        section_text = "\n".join(line for _, line in current_lines).strip()
        section_end_line = current_lines[-1][0] if current_lines else current_heading_line
        sections[current_heading] = {
            "text": section_text,
            "items": items,
            "paragraphs": paragraphs,
            "keyedItems": keyed_items,
            "headingLine": current_heading_line,
            "startLine": current_heading_line,
            "endLine": section_end_line,
            "file": path.name,
        }

    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.rstrip()
        if line.startswith("## "):
            flush_section()
            current_heading = line[3:].strip()
            current_heading_line = line_no
            current_lines = []
            continue
        if current_heading is not None:
            current_lines.append((line_no, line))

    flush_section()
    return sections


def make_extracted_text(
    value: str | None,
    *,
    file: str,
    heading: str,
    start_line: int | None,
    end_line: int | None,
) -> dict[str, Any] | None:
    if not value:
        return None
    return {
        "value": value,
        "file": file,
        "heading": heading,
        "startLine": start_line,
        "endLine": end_line,
    }


def make_extracted_list(items: list[dict[str, Any]], *, file: str, heading: str) -> dict[str, Any] | None:
    texts = [str(item.get("text", "")).strip() for item in items if str(item.get("text", "")).strip()]
    if not texts:
        return None
    return {
        "items": texts,
        "file": file,
        "heading": heading,
        "startLine": items[0].get("startLine"),
        "endLine": items[-1].get("endLine"),
    }


def first_paragraph(section: dict[str, Any]) -> dict[str, Any] | None:
    paragraphs = section.get("paragraphs", [])
    if not paragraphs:
        return None
    paragraph = paragraphs[0]
    return make_extracted_text(
        paragraph.get("text"),
        file=section.get("file", ""),
        heading=section.get("heading", ""),
        start_line=paragraph.get("startLine"),
        end_line=paragraph.get("endLine"),
    )


def keyed_bullet(section: dict[str, Any], key: str) -> dict[str, Any] | None:
    item = section.get("keyedItems", {}).get(key.lower())
    if not item:
        return None
    return make_extracted_text(
        item.get("text"),
        file=section.get("file", ""),
        heading=section.get("heading", ""),
        start_line=item.get("startLine"),
        end_line=item.get("endLine"),
    )


def extract_session_brief(root: Path) -> dict[str, Any]:
    session_sections = parse_markdown_sections(root / "autocatalyst.md")
    rubric_sections = parse_markdown_sections(root / "autocatalyst-rubric.md")

    for heading, section in session_sections.items():
        section["heading"] = heading
    for heading, section in rubric_sections.items():
        section["heading"] = heading

    audience_section = session_sections.get("Audience and Deliverables", {})
    current_incumbent_section = session_sections.get("Current Incumbent", {})
    current_incumbent_items = current_incumbent_section.get("items", [])
    current_incumbent = (
        make_extracted_text(
            current_incumbent_items[0].get("text"),
            file=current_incumbent_section.get("file", "autocatalyst.md"),
            heading="Current Incumbent",
            start_line=current_incumbent_items[0].get("startLine"),
            end_line=current_incumbent_items[0].get("endLine"),
        )
        if current_incumbent_items
        else first_paragraph(current_incumbent_section)
    )

    return {
        "objective": first_paragraph(session_sections.get("Objective", {})),
        "audience": keyed_bullet(audience_section, "audience"),
        "deliverables": keyed_bullet(audience_section, "deliverables"),
        "constraints": make_extracted_list(
            session_sections.get("Constraints", {}).get("items", []),
            file=session_sections.get("Constraints", {}).get("file", "autocatalyst.md"),
            heading="Constraints",
        ),
        "off_limits": make_extracted_list(
            session_sections.get("Off Limits", {}).get("items", []),
            file=session_sections.get("Off Limits", {}).get("file", "autocatalyst.md"),
            heading="Off Limits",
        ),
        "current_incumbent": current_incumbent,
        "rubric_snapshot": make_extracted_list(
            session_sections.get("Rubric Snapshot", {}).get("items", []),
            file=session_sections.get("Rubric Snapshot", {}).get("file", "autocatalyst.md"),
            heading="Rubric Snapshot",
        ),
        "learned": make_extracted_list(
            session_sections.get("What Has Been Learned", {}).get("items", []),
            file=session_sections.get("What Has Been Learned", {}).get("file", "autocatalyst.md"),
            heading="What Has Been Learned",
        ),
        "rubric_core": make_extracted_list(
            rubric_sections.get("Core criteria", {}).get("items", []),
            file=rubric_sections.get("Core criteria", {}).get("file", "autocatalyst-rubric.md"),
            heading="Core criteria",
        ),
        "rubric_promoted": make_extracted_list(
            rubric_sections.get("Promoted criteria", {}).get("items", []),
            file=rubric_sections.get("Promoted criteria", {}).get("file", "autocatalyst-rubric.md"),
            heading="Promoted criteria",
        ),
    }


def process_overview_mermaid() -> str:
    return """flowchart TD
    A[Anchor / task / constraints] --> P[Planner or evidence-mode vote]
    P --> I[Incumbent A]
    I --> R[Researcher optional]
    I --> C[Critic]
    C --> B[Rewriter -> candidate B]
    I --> S[Synthesizer]
    B --> S
    S --> AB[Candidate AB]
    I --> T[Tribunal]
    B --> T
    AB --> T
    R --> T
    T --> W{Winner}
    W -->|A| K[Keep incumbent / streak++]
    W -->|B or AB| N[Promote new incumbent / streak=0]
    K --> L[Log round + dashboard + report]
    N --> L"""


def session_history_mermaid(config: dict[str, Any], rounds: list[dict[str, Any]]) -> str:
    lines: list[str] = ["flowchart TD"]
    title = sanitize(config.get("name", "session"))
    lines.append(f"    START[Session start: {title}] --> I0[Initial incumbent]")
    if not rounds:
        lines.append("    I0 --> NEXT[No rounds logged yet]")
        return "\n".join(lines)

    previous = "I0"
    for round_row in rounds:
        rid = int(round_row.get("round", len(lines)))
        round_node = f"R{rid}"
        verdict_node = f"W{rid}"
        incumbent_node = f"I{rid}"
        winner = sanitize(round_row.get("winner", "A"))
        status = sanitize(round_row.get("status", "keep"))
        lines.append(f"    {previous} --> {round_node}[Round {rid}]")
        lines.append(f"    {round_node} --> {verdict_node}{{Winner {winner}}}")
        lines.append(f"    {verdict_node} --> {incumbent_node}[Incumbent after round {rid} / {status}]")
        previous = incumbent_node
    return "\n".join(lines)


def round_flow_mermaid(round_row: dict[str, Any]) -> str:
    hard_checks = sanitize(round_row.get("hardChecks", "na"))
    winner = sanitize(round_row.get("winner", "A"))
    status = sanitize(round_row.get("status", "keep"))
    degraded = "degraded mode" if bool(round_row.get("degradedMode")) else "full mode"
    return "\n".join(
        [
            "flowchart TD",
            "    ANCHOR[Anchor] --> A[Incumbent A]",
            "    A --> C[Critic]",
            "    C --> B[Candidate B]",
            "    A --> S[Synthesizer]",
            "    B --> S",
            "    S --> AB[Candidate AB]",
            f"    B --> HC[Hard checks: {hard_checks}]",
            "    AB --> HC",
            "    A --> T[Tribunal]",
            "    HC --> T",
            "    T --> W{Winner}",
            f"    W --> O[Winner {winner} / {status} / {degraded}]",
        ]
    )


def mermaid_markdown(title: str, mermaid: str) -> str:
    return f"# {title}\n\n```mermaid\n{mermaid}\n```\n"


def collect_summary(config: dict[str, Any], rounds: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(r.get("status", "unknown") for r in rounds)
    winner_counts = Counter(r.get("winner", "?") for r in rounds)
    promotions: list[str] = []
    artifact_paths: list[str] = []
    agent_names: list[str] = []
    degraded_count = 0
    latest = rounds[-1] if rounds else None

    for round_row in rounds:
        promotions.extend(as_list(round_row.get("promotions")))
        artifact_paths.extend(as_list(round_row.get("artifacts")))
        artifact_paths.extend(tribunal_artifact_paths(round_row))
        agent_names.extend(as_list(round_row.get("agentNames")))
        if bool(round_row.get("degradedMode")):
            degraded_count += 1

    return {
        "counts": counts,
        "winner_counts": winner_counts,
        "promotions": list(dict.fromkeys(promotions)),
        "artifact_paths": list(dict.fromkeys(artifact_paths)),
        "agent_names": list(dict.fromkeys(agent_names)),
        "degraded_count": degraded_count,
        "latest": latest,
        "task_class": config.get("taskClass", "unknown"),
        "evidence_mode": config.get("evidenceMode", "unknown"),
        "survival_target": config.get("survivalTarget", 2),
        "name": config.get("name", "session"),
        "round_count": len(rounds),
    }


def render_dashboard(root: Path) -> str:
    try:
        config, rounds = load_session(root)
    except ValueError:
        rows = load_jsonl(root / "autocatalyst.jsonl")
        if not rows:
            return "# AutoCatalyst Dashboard\n\nNo session found.\n"
        raise
    if not rounds and not config:
        return "# AutoCatalyst Dashboard\n\nNo session found.\n"

    summary = collect_summary(config, rounds)
    convergence = convergence_status(config, rounds)
    counts = summary["counts"]
    winner_counts = summary["winner_counts"]
    latest = summary["latest"]

    lines: list[str] = []
    lines.append(f"# AutoCatalyst Dashboard: {summary['name']}")
    lines.append("")
    lines.append(f"**Task class:** {summary['task_class']}  ")
    lines.append(f"**Evidence mode:** {summary['evidence_mode']}  ")
    lines.append(f"**Survival target:** {summary['survival_target']}  ")
    lines.append(f"**Current survival streak:** {convergence['currentSurvivalStreak']}  ")
    lines.append(f"**Convergence decision:** {convergence['decision']}  ")
    lines.append(f"**Rounds logged:** {summary['round_count']}  ")
    lines.append(f"**Degraded rounds:** {summary['degraded_count']}  ")
    lines.append("**Browser report:** `autocatalyst-report.html`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    if rounds:
        lines.append(
            f"- Status counts: promote={counts.get('promote', 0)}, keep={counts.get('keep', 0)}, mixed={counts.get('mixed', 0)}, blocked={counts.get('blocked', 0)}, rejected={counts.get('rejected', 0)}"
        )
        lines.append(
            f"- Winner counts: A={winner_counts.get('A', 0)}, B={winner_counts.get('B', 0)}, AB={winner_counts.get('AB', 0)}"
        )
        if latest:
            lines.append(
                f"- Latest round: #{latest.get('round')} winner={latest.get('winner')} status={latest.get('status')} — {sanitize(latest.get('winnerReason', ''))}"
            )
            latest_tribunal = normalize_tribunal(latest)
            latest_verdicts = latest_tribunal.get("judgeVerdicts", [])
            latest_aggregation = latest_tribunal.get("aggregationMethod", "")
            if latest_verdicts or latest_aggregation:
                tribunal_bits = []
                if latest_verdicts:
                    tribunal_bits.append(f"{len(latest_verdicts)} judge verdicts")
                if latest_aggregation:
                    tribunal_bits.append(f"aggregation={latest_aggregation}")
                lines.append(f"- Latest tribunal: {', '.join(tribunal_bits)}")
        lines.append(f"- Convergence: {convergence['reason']}")
    else:
        lines.append("- No rounds logged yet.")
    lines.append("")

    lines.append("## Agents that actually ran")
    lines.append("")
    if summary["agent_names"]:
        for name in summary["agent_names"]:
            lines.append(f"- {name}")
    else:
        lines.append("- none logged yet")
    lines.append("")

    lines.append("## Promoted criteria")
    lines.append("")
    if summary["promotions"]:
        for item in summary["promotions"]:
            lines.append(f"- {item}")
    else:
        lines.append("- none yet")
    lines.append("")

    lines.append("## Artifact files")
    lines.append("")
    if summary["artifact_paths"]:
        for path in summary["artifact_paths"]:
            lines.append(f"- {path}")
    else:
        lines.append("- none logged yet")
    lines.append("")

    lines.append("## Latest tribunal")
    lines.append("")
    if latest:
        latest_tribunal = normalize_tribunal(latest)
        latest_grouped = tribunal_round_artifacts(latest)
        if latest_tribunal.get("candidateMapArtifact"):
            lines.append(f"- candidate map: {latest_tribunal['candidateMapArtifact']}")
        if latest_tribunal.get("summaryDataArtifact"):
            lines.append(f"- structured summary: {latest_tribunal['summaryDataArtifact']}")
        for packet in latest_tribunal.get("judgePackets", []):
            lines.append(f"- judge packet: {packet}")
        for packet in latest_grouped["judge_packet"]:
            if packet not in latest_tribunal.get("judgePackets", []):
                lines.append(f"- judge packet: {packet}")
        for verdict in latest_tribunal.get("judgeVerdicts", []):
            judge_name = display_judge_name(str(verdict.get("judge", "judge")))
            ranking = " > ".join(as_list(verdict.get("ranking")))
            suffix = f" ({ranking})" if ranking else ""
            if verdict.get("artifact"):
                lines.append(f"- {judge_name}: {verdict['artifact']}{suffix}")
        if latest_tribunal.get("summaryArtifact"):
            lines.append(f"- tribunal summary: {latest_tribunal['summaryArtifact']}")
        if latest_tribunal.get("aggregationMethod"):
            lines.append(f"- aggregation method: {latest_tribunal['aggregationMethod']}")
        if latest_tribunal.get("result"):
            lines.append(f"- result: {latest_tribunal['result']}")
        if latest_tribunal.get("note"):
            lines.append(f"- note: {latest_tribunal['note']}")
        if not any(
            [
                latest_tribunal.get("candidateMapArtifact"),
                latest_tribunal.get("summaryDataArtifact"),
                latest_grouped["judge_packet"],
                latest_tribunal.get("judgePackets", []),
                latest_tribunal.get("judgeVerdicts", []),
                latest_tribunal.get("summaryArtifact"),
                latest_tribunal.get("aggregationMethod"),
            ]
        ):
            lines.append("- none logged for the latest round")
    else:
        lines.append("- none logged yet")
    lines.append("")

    lines.append("## Latest critic")
    lines.append("")
    if latest and isinstance(latest.get("critic"), dict):
        critic = latest["critic"]
        if critic.get("artifact"):
            lines.append(f"- artifact: {critic['artifact']}")
        lines.append(f"- rewrite warranted: {'yes' if bool(critic.get('rewriteWarranted')) else 'no'}")
        for field, label in (
            ("hardBlockers", "hard blockers"),
            ("softConcerns", "soft concerns"),
            ("suggestedRubricItems", "suggested rubric items"),
        ):
            values = as_list(critic.get(field))
            if values:
                lines.append(f"- {label}: {'; '.join(values)}")
    else:
        lines.append("- none logged for the latest round")
    lines.append("")

    lines.append("## Latest research")
    lines.append("")
    if latest and isinstance(latest.get("research"), dict):
        research = latest["research"]
        if research.get("artifact"):
            lines.append(f"- artifact: {research['artifact']}")
        confirmed = research.get("confirmedFacts", [])
        if isinstance(confirmed, list) and confirmed:
            fact_bits = []
            for item in confirmed[:3]:
                if isinstance(item, dict):
                    claim = str(item.get("claim", "")).strip()
                    citation = str(item.get("citation", "")).strip()
                    if claim and citation:
                        fact_bits.append(f"{claim} [{citation}]")
            if fact_bits:
                lines.append(f"- confirmed facts: {'; '.join(fact_bits)}")
        for field, label in (
            ("unresolvedQuestions", "open questions"),
            ("implications", "implications"),
            ("conflicts", "conflicts"),
        ):
            values = as_list(research.get(field))
            if values:
                lines.append(f"- {label}: {'; '.join(values)}")
    else:
        lines.append("- none logged for the latest round")
    lines.append("")

    lines.append("## Rounds")
    lines.append("")
    lines.append("| # | winner | status | hard checks | judge ranking | degraded | reason |")
    lines.append("|---|--------|--------|-------------|---------------|----------|--------|")
    for round_row in rounds:
        ranking = ", ".join(as_list(round_row.get("judgeRanking")))
        reason = sanitize(round_row.get("winnerReason", ""))
        degraded = "yes" if bool(round_row.get("degradedMode")) else "no"
        lines.append(
            f"| {round_row.get('round', '')} | {round_row.get('winner', '')} | {round_row.get('status', '')} | {sanitize(round_row.get('hardChecks', 'na'))} | {ranking} | {degraded} | {reason} |"
        )
    lines.append("")
    lines.append("## Generated visualizations")
    lines.append("")
    lines.append("- autocatalyst-artifacts/process-overview.md")
    lines.append("- autocatalyst-artifacts/session-history.md")
    lines.append("- autocatalyst-artifacts/rounds/round-<n>-flow.md")
    lines.append("- autocatalyst-report.html")
    lines.append("")
    return "\n".join(lines) + "\n"


def render_session_history(config: dict[str, Any], rounds: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append(f"# Session History: {sanitize(config.get('name', 'session'))}")
    lines.append("")
    lines.append("```mermaid")
    lines.append(session_history_mermaid(config, rounds))
    lines.append("```")
    lines.append("")
    if rounds:
        lines.append("## Round outcomes")
        lines.append("")
        for round_row in rounds:
            lines.append(
                f"- Round {round_row.get('round')}: winner={round_row.get('winner')} status={round_row.get('status')} — {sanitize(round_row.get('winnerReason', ''))}"
            )
    else:
        lines.append("No rounds logged yet.")
    lines.append("")
    return "\n".join(lines)


def render_round_flow(round_row: dict[str, Any]) -> str:
    rid = int(round_row.get("round", 0))
    hard_checks = sanitize(round_row.get("hardChecks", "na"))
    winner = sanitize(round_row.get("winner", "A"))
    status = sanitize(round_row.get("status", "keep"))
    reason = sanitize(round_row.get("winnerReason", ""))
    ranking = ", ".join(as_list(round_row.get("judgeRanking"))) or "not logged"
    agents = ", ".join(as_list(round_row.get("agentNames"))) or "not logged"
    degraded = "yes" if bool(round_row.get("degradedMode")) else "no"

    lines: list[str] = []
    lines.append(f"# Round {rid} Flow")
    lines.append("")
    lines.append("```mermaid")
    lines.append(round_flow_mermaid(round_row))
    lines.append("```")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(f"- winner: {winner}")
    lines.append(f"- status: {status}")
    lines.append(f"- hard checks: {hard_checks}")
    lines.append(f"- judge ranking: {ranking}")
    lines.append(f"- degraded mode: {degraded}")
    lines.append(f"- agents logged: {agents}")
    if reason:
        lines.append(f"- reason: {reason}")
    artifacts = as_list(round_row.get("artifacts"))
    if artifacts:
        lines.append("- artifacts:")
        for path in artifacts:
            lines.append(f"  - {path}")
    promotions = as_list(round_row.get("promotions"))
    if promotions:
        lines.append("- promoted criteria:")
        for item in promotions:
            lines.append(f"  - {item}")
    lines.append("")
    return "\n".join(lines)


def rel_href(path: str) -> str:
    return quote(path.replace("\\", "/"), safe="/-_.~")


def html_list(items: list[str], empty: str = "none") -> str:
    if not items:
        return f"<p class=\"empty-state\">{escape(empty)}</p>"
    lines = ["<ul class=\"plain-list\">"]
    for item in items:
        lines.append(f"  <li>{escape(item)}</li>")
    lines.append("</ul>")
    return "\n".join(lines)


def html_link_list(items: list[str], empty: str = "none") -> str:
    if not items:
        return f"<p class=\"empty-state\">{escape(empty)}</p>"
    lines = ["<ul class=\"plain-list\">"]
    for item in items:
        href = rel_href(item)
        lines.append(f'  <li><a href="{href}">{escape(item)}</a></li>')
    lines.append("</ul>")
    return "\n".join(lines)


def render_tribunal_snapshot(root: Path, latest_story: dict[str, Any] | None) -> str:
    if not latest_story:
        return '<p class="empty-state">No latest round is available yet.</p>'

    tribunal = latest_story.get("tribunal", {})
    grouped = tribunal_round_artifacts({"artifacts": latest_story.get("artifacts", []), "tribunal": tribunal})
    judge_verdicts = tribunal.get("judgeVerdicts", []) if isinstance(tribunal, dict) else []
    aggregation = tribunal.get("aggregationMethod", "") if isinstance(tribunal, dict) else ""
    candidate_map = str(tribunal.get("candidateMapArtifact", "")).strip() if isinstance(tribunal, dict) else ""
    summary_artifact = str(tribunal.get("summaryArtifact", "")).strip() if isinstance(tribunal, dict) else ""
    summary_data_artifact = str(tribunal.get("summaryDataArtifact", "")).strip() if isinstance(tribunal, dict) else ""
    summary_note_text = str(tribunal.get("note", "")).strip() if isinstance(tribunal, dict) else ""
    tribunal_result = str(tribunal.get("result", "")).strip() if isinstance(tribunal, dict) else ""

    if not any(
        [
            candidate_map,
            summary_artifact,
            summary_data_artifact,
            judge_verdicts,
            grouped["judge_packet"],
            grouped["judge_verdict"],
            grouped["candidate_map"],
            grouped["tribunal_summary"],
        ]
    ):
        return '<p class="empty-state">No tribunal artifacts were logged for the latest round.</p>'

    lines = ['<ul class="plain-list">']
    if candidate_map:
        lines.append(
            f'  <li><strong>Candidate map.</strong> <a href="{rel_href(candidate_map)}">{escape(candidate_map)}</a> keeps the unblinding information on the parent side only.</li>'
        )

    judge_packets = grouped["judge_packet"]
    if judge_packets:
        lines.append(
            f"  <li><strong>Blind packets.</strong> {len(judge_packets)} packet(s) were prepared so each judge saw the same contenders under permuted aliases.</li>"
        )

    if summary_artifact:
        summary_excerpt = read_markdown_summary(root / summary_artifact)
        summary_note = f" {escape(summary_excerpt)}" if summary_excerpt else ""
        lines.append(
            f'  <li><strong>Tribunal summary.</strong> <a href="{rel_href(summary_artifact)}">{escape(summary_artifact)}</a>{summary_note}</li>'
        )
    if summary_data_artifact:
        lines.append(
            f'  <li><strong>Structured summary.</strong> <a href="{rel_href(summary_data_artifact)}">{escape(summary_data_artifact)}</a></li>'
        )

    if judge_verdicts:
        for item in judge_verdicts:
            judge_name = display_judge_name(str(item.get("judge", "judge")))
            artifact = str(item.get("artifact", "")).strip()
            ranking = " > ".join(as_list(item.get("ranking")))
            rationale = str(item.get("rationale", "")).strip()
            winner = str(item.get("winner", "")).strip()
            blockers = item.get("blockers", []) if isinstance(item.get("blockers", []), list) else []
            if artifact:
                link = f'<a href="{rel_href(artifact)}">{escape(artifact)}</a>'
            else:
                link = "verdict path not logged"
            ranking_note = f" Ranking: {escape(ranking)}." if ranking else ""
            winner_note = f" Winner: {escape(winner)}." if winner else ""
            rationale_note = f" {escape(rationale)}" if rationale else ""
            blocker_note = ""
            if blockers:
                blocker_bits = []
                for blocker in blockers:
                    if isinstance(blocker, dict):
                        candidate = str(blocker.get("candidate", "")).strip()
                        reason = str(blocker.get("reason", "")).strip()
                        if candidate and reason:
                            blocker_bits.append(f"{candidate}: {reason}")
                if blocker_bits:
                    blocker_note = " Blockers: " + "; ".join(escape(bit) for bit in blocker_bits) + "."
            lines.append(
                f"  <li><strong>{escape(judge_name)}.</strong> {link}.{ranking_note}{winner_note}{rationale_note}{blocker_note}</li>"
            )
    elif grouped["judge_verdict"]:
        for artifact in grouped["judge_verdict"]:
            lines.append(
                f'  <li><strong>Judge verdict.</strong> <a href="{rel_href(artifact)}">{escape(artifact)}</a></li>'
            )

    if aggregation:
        lines.append(f"  <li><strong>Aggregation method.</strong> {escape(aggregation)}</li>")
    if tribunal_result:
        lines.append(f"  <li><strong>Panel result.</strong> {escape(tribunal_result)}</li>")
    if summary_note_text:
        lines.append(f"  <li><strong>Panel note.</strong> {escape(summary_note_text)}</li>")

    lines.append("</ul>")
    return "\n".join(lines)


def render_role_output_snapshot(round_row: dict[str, Any], role_key: str) -> str:
    payload = round_row.get(role_key)
    if not isinstance(payload, dict):
        if role_key == "critic":
            return '<p class="empty-state">No structured critic output was logged for the latest round.</p>'
        if role_key == "research":
            return '<p class="empty-state">No structured researcher output was logged for the latest round.</p>'
        return '<p class="empty-state">No structured role output was logged.</p>'

    artifact = str(payload.get("artifact", "")).strip()
    lines = ['<ul class="plain-list">']
    if artifact:
        lines.append(f'  <li><strong>Artifact.</strong> <a href="{rel_href(artifact)}">{escape(artifact)}</a></li>')

    if role_key == "critic":
        rewrite_warranted = "yes" if bool(payload.get("rewriteWarranted")) else "no"
        lines.append(f"  <li><strong>Rewrite warranted.</strong> {rewrite_warranted}</li>")
        hard_blockers = as_list(payload.get("hardBlockers"))
        soft_concerns = as_list(payload.get("softConcerns"))
        rubric_items = as_list(payload.get("suggestedRubricItems"))
        if hard_blockers:
            lines.append(f"  <li><strong>Hard blockers.</strong> {escape('; '.join(hard_blockers))}</li>")
        if soft_concerns:
            lines.append(f"  <li><strong>Soft concerns.</strong> {escape('; '.join(soft_concerns))}</li>")
        if rubric_items:
            lines.append(f"  <li><strong>Suggested rubric items.</strong> {escape('; '.join(rubric_items))}</li>")
    elif role_key == "research":
        confirmed = payload.get("confirmedFacts", [])
        unresolved = as_list(payload.get("unresolvedQuestions"))
        implications = as_list(payload.get("implications"))
        conflicts = as_list(payload.get("conflicts"))
        if isinstance(confirmed, list) and confirmed:
            fact_bits = []
            for item in confirmed[:3]:
                if isinstance(item, dict):
                    claim = str(item.get("claim", "")).strip()
                    citation = str(item.get("citation", "")).strip()
                    if claim and citation:
                        fact_bits.append(f"{claim} [{citation}]")
            if fact_bits:
                lines.append(f"  <li><strong>Confirmed facts.</strong> {escape('; '.join(fact_bits))}</li>")
        if unresolved:
            lines.append(f"  <li><strong>Open questions.</strong> {escape('; '.join(unresolved))}</li>")
        if implications:
            lines.append(f"  <li><strong>Implications.</strong> {escape('; '.join(implications))}</li>")
        if conflicts:
            lines.append(f"  <li><strong>Conflicts.</strong> {escape('; '.join(conflicts))}</li>")

    lines.append("</ul>")
    return "\n".join(lines)


def source_code(*parts: str) -> str:
    return "<code>" + escape(".".join(part for part in parts if part)) + "</code>"


def make_claim(
    label: str,
    value: Any,
    claim_class: str,
    *,
    source_fields: list[str] | None = None,
    source_artifacts: list[str] | None = None,
    source_spans: list[dict[str, Any]] | None = None,
    unknown_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "label": label,
        "value": value,
        "claimClass": claim_class,
        "sourceFields": source_fields or [],
        "sourceArtifacts": source_artifacts or [],
        "sourceSpans": source_spans or [],
        "unknownReason": unknown_reason,
    }


def format_source_span(span: dict[str, Any]) -> str:
    file_name = str(span.get("file", ""))
    start_line = span.get("startLine")
    end_line = span.get("endLine")
    heading = str(span.get("heading", "")).strip()
    if start_line and end_line and start_line != end_line:
        location = f"{file_name}:{start_line}-{end_line}"
    elif start_line:
        location = f"{file_name}:{start_line}"
    else:
        location = file_name
    suffix = f" ({heading})" if heading else ""
    return f"<code>{escape(location)}</code>{escape(suffix)}"


def describe_claim(claim: dict[str, Any]) -> str:
    claim_class = claim.get("claimClass", "logged")
    parts: list[str] = []
    if claim_class == "logged":
        parts.append("Logged fact")
    elif claim_class == "derived":
        parts.append("Derived fact")
    elif claim_class == "explanatory":
        parts.append("Reporter explanation")
    else:
        parts.append("Unknown or unavailable")

    source_fields = claim.get("sourceFields", [])
    source_artifacts = claim.get("sourceArtifacts", [])
    source_spans = claim.get("sourceSpans", [])
    unknown_reason = claim.get("unknownReason")

    if source_spans:
        spans = ", ".join(format_source_span(span) for span in source_spans)
        parts.append(f"Spans: {spans}")
    if source_fields:
        fields = ", ".join(source_code(*field.split(".")) for field in source_fields)
        parts.append(f"Fields: {fields}")
    if source_artifacts:
        artifacts = ", ".join(f"<code>{escape(path)}</code>" for path in source_artifacts)
        parts.append(f"Files: {artifacts}")
    if unknown_reason:
        parts.append(escape(unknown_reason))
    return " ".join(parts)


def render_claim_table(claims: list[dict[str, Any]], empty: str) -> str:
    if not claims:
        return f"<p class=\"empty-state\">{escape(empty)}</p>"

    lines = [
        "<table class=\"facts-table\">",
        "  <thead>",
        "    <tr><th>Item</th><th>Value</th><th>Provenance</th></tr>",
        "  </thead>",
        "  <tbody>",
    ]
    for claim in claims:
        value = claim.get("value")
        if value is None or not str(value).strip():
            rendered_value = '<span class="unknown">Not logged</span>'
        else:
            rendered_value = escape(str(value))
        lines.append(
            "    <tr>"
            f"<th scope=\"row\">{escape(str(claim.get('label', '')))}</th>"
            f"<td>{rendered_value}</td>"
            f"<td>{describe_claim(claim)}</td>"
            "</tr>"
        )
    lines.extend(["  </tbody>", "</table>"])
    return "\n".join(lines)


def render_note(title: str, body: str) -> str:
    return f"<div class=\"note\"><p><strong>{escape(title)}</strong> {body}</p></div>"


def render_text_block(
    heading: str,
    field: Any,
    *,
    source_field: str,
    source_artifact: str = "",
    source_span: dict[str, Any] | None = None,
    claim_class: str = "logged",
    empty: str = "Not logged.",
    caution: str | None = None,
) -> str:
    extracted_field = field if isinstance(field, dict) else None
    scalar_value = extracted_field.get("value") if extracted_field else field

    if scalar_value is None or not str(scalar_value).strip():
        body = f"<p class=\"empty-state\">{escape(empty)}</p>"
        provenance = describe_claim(
            make_claim(
                heading,
                None,
                "unknown",
                source_spans=[source_span] if source_span else [],
                source_fields=[source_field],
                source_artifacts=[source_artifact],
                unknown_reason=empty,
            )
        )
    else:
        body = f"<p>{escape(str(scalar_value))}</p>"
        provenance = describe_claim(
            make_claim(
                heading,
                scalar_value,
                claim_class,
                source_spans=[extracted_field] if extracted_field else ([source_span] if source_span else []),
                source_fields=[source_field] if not extracted_field else [],
                source_artifacts=[source_artifact] if not extracted_field and source_artifact else [],
                unknown_reason=caution if claim_class == "unknown" else None,
            )
        )
    caution_html = f"<p class=\"caution\">{escape(caution)}</p>" if caution else ""
    return (
        "<div class=\"text-block\">"
        f"<h4>{escape(heading)}</h4>"
        f"{body}"
        f"{caution_html}"
        f"<p class=\"provenance\">{provenance}</p>"
        "</div>"
    )


def render_list_block(
    heading: str,
    field: dict[str, Any] | None,
    *,
    source_artifact: str,
    source_heading: str,
    empty: str,
    caution: str | None = None,
) -> str:
    items = field.get("items", []) if field else []
    provenance = describe_claim(
        make_claim(
            heading,
            ", ".join(items) if items else None,
            "logged" if items else "unknown",
            source_spans=[field] if field else [],
            source_artifacts=[source_artifact] if not field else [],
            source_fields=[source_heading] if not field else [],
            unknown_reason=empty if not items else None,
        )
    )
    caution_html = f"<p class=\"caution\">{escape(caution)}</p>" if caution else ""
    return (
        "<div class=\"text-block\">"
        f"<h4>{escape(heading)}</h4>"
        f"{html_list(items, empty=empty)}"
        f"{caution_html}"
        f"<p class=\"provenance\">{provenance}</p>"
        "</div>"
    )


def render_round_section(round_row: dict[str, Any]) -> str:
    rid = int(round_row.get("round", 0))
    degraded = "Yes" if bool(round_row.get("degradedMode")) else "No"
    ranking = ", ".join(as_list(round_row.get("judgeRanking"))) or None
    agents = as_list(round_row.get("agentNames"))
    promotions = as_list(round_row.get("promotions"))
    artifacts = as_list(round_row.get("artifacts"))
    row_span = round_row.get("__sourceSpan")

    claims = [
        make_claim("Winner", round_row.get("winner"), "logged", source_spans=jsonl_span(round_row), source_fields=["round.winner"]),
        make_claim("Status", round_row.get("status"), "logged", source_spans=jsonl_span(round_row), source_fields=["round.status"]),
        make_claim("Hard checks", round_row.get("hardChecks", "na"), "logged", source_spans=jsonl_span(round_row), source_fields=["round.hardChecks"]),
        make_claim("Degraded mode", degraded, "derived", source_spans=jsonl_span(round_row), source_fields=["round.degradedMode"]),
        make_claim("Judge ranking", ranking, "logged", source_spans=jsonl_span(round_row), source_fields=["round.judgeRanking"]),
        make_claim("Incumbent before", round_row.get("incumbentBefore"), "logged", source_spans=jsonl_span(round_row), source_fields=["round.incumbentBefore"]),
        make_claim("Incumbent after", round_row.get("incumbentAfter"), "logged", source_spans=jsonl_span(round_row), source_fields=["round.incumbentAfter"]),
    ]

    blocks = [
        render_text_block(
            "Why this winner was logged",
            round_row.get("winnerReason"),
            source_field="round.winnerReason",
            source_span=row_span,
            empty="No winner reason was logged for this round.",
        ),
        render_text_block(
            "Benchmark summary",
            round_row.get("benchmarkSummary"),
            source_field="round.benchmarkSummary",
            source_span=row_span,
            empty="No benchmark summary was logged for this round.",
            caution="This is logged session text, not an independently verified evaluation.",
        ),
        render_text_block(
            "Operator notes",
            round_row.get("notes"),
            source_field="round.notes",
            source_span=row_span,
            empty="No operator notes were logged for this round.",
            caution="This is explanatory session text and may summarize work that requires opening the linked artifacts to inspect directly.",
        ),
    ]

    return f"""
<article class="round-section">
  <h3>Round {rid}</h3>
  {render_note('What this section is', 'This is the logged record for one round. The facts table below comes from the round row in <code>autocatalyst.jsonl</code>. The diagram is explanatory and should not be treated as additional evidence.')}
  {render_claim_table(claims, empty='No round facts logged.')}
  {''.join(blocks)}
  <div class="support-grid">
    <div>
      <h4>Agents logged</h4>
      {html_list(agents, empty='No agent names were logged for this round.')}
      <p class="provenance">{describe_claim(make_claim('Agents logged', ', '.join(agents) if agents else None, 'logged' if agents else 'unknown', source_spans=jsonl_span(round_row), source_fields=['round.agentNames'], unknown_reason='No agent names were logged for this round.' if not agents else None))}</p>
    </div>
    <div>
      <h4>Promoted criteria</h4>
      {html_list(promotions, empty='No promoted criteria were logged for this round.')}
      <p class="provenance">{describe_claim(make_claim('Promoted criteria', ', '.join(promotions) if promotions else None, 'logged' if promotions else 'unknown', source_spans=jsonl_span(round_row), source_fields=['round.promotions'], unknown_reason='No promoted criteria were logged for this round.' if not promotions else None))}</p>
    </div>
  </div>
  <div>
    <h4>Artifacts linked from this round</h4>
    {html_link_list(artifacts, empty='No artifacts were linked from this round.')}
    <p class="provenance">{describe_claim(make_claim('Artifacts linked from this round', ', '.join(artifacts) if artifacts else None, 'logged' if artifacts else 'unknown', source_spans=jsonl_span(round_row), source_fields=['round.artifacts'], unknown_reason='No artifacts were linked from this round.' if not artifacts else None))}</p>
  </div>
  <figure class="diagram-block">
    <figcaption>Explanatory flow for round {rid}. This diagram shows the standard AutoCatalyst round shape, annotated with the logged outcome for this round.</figcaption>
    <div class="diagram mermaid">{escape(round_flow_mermaid(round_row))}</div>
  </figure>
</article>
"""


def collect_unknowns(config: dict[str, Any], rounds: list[dict[str, Any]], brief: dict[str, Any]) -> list[dict[str, Any]]:
    unknowns: list[dict[str, Any]] = []

    if not brief.get("objective"):
        unknowns.append(
            make_claim(
                "Objective",
                None,
                "unknown",
                source_artifacts=["autocatalyst.md"],
                source_fields=["Objective"],
                unknown_reason="The report looks for an exact '## Objective' section in autocatalyst.md. It was missing or empty.",
            )
        )
    if not brief.get("audience"):
        unknowns.append(
            make_claim(
                "Audience",
                None,
                "unknown",
                source_artifacts=["autocatalyst.md"],
                source_fields=["Audience and Deliverables"],
                unknown_reason="The report looks for a bullet starting with 'Audience:' inside '## Audience and Deliverables'.",
            )
        )
    if not brief.get("deliverables"):
        unknowns.append(
            make_claim(
                "Deliverables",
                None,
                "unknown",
                source_artifacts=["autocatalyst.md"],
                source_fields=["Audience and Deliverables"],
                unknown_reason="The report looks for a bullet starting with 'Deliverables:' inside '## Audience and Deliverables'.",
            )
        )
    if not brief.get("constraints"):
        unknowns.append(
            make_claim(
                "Constraints",
                None,
                "unknown",
                source_artifacts=["autocatalyst.md"],
                source_fields=["Constraints"],
                unknown_reason="The report only extracts bullet items under '## Constraints'.",
            )
        )
    if not brief.get("off_limits"):
        unknowns.append(
            make_claim(
                "Off limits",
                None,
                "unknown",
                source_artifacts=["autocatalyst.md"],
                source_fields=["Off Limits"],
                unknown_reason="The report only extracts bullet items under '## Off Limits'.",
            )
        )
    if not brief.get("rubric_snapshot"):
        unknowns.append(
            make_claim(
                "Rubric snapshot",
                None,
                "unknown",
                source_artifacts=["autocatalyst.md"],
                source_fields=["Rubric Snapshot"],
                unknown_reason="The report only extracts bullet items under '## Rubric Snapshot'.",
            )
        )
    if not brief.get("learned"):
        unknowns.append(
            make_claim(
                "What has been learned",
                None,
                "unknown",
                source_artifacts=["autocatalyst.md"],
                source_fields=["What Has Been Learned"],
                unknown_reason="The report only extracts bullet items under '## What Has Been Learned'.",
            )
        )
    if not brief.get("rubric_core") and not brief.get("rubric_promoted"):
        unknowns.append(
            make_claim(
                "Detailed rubric file",
                None,
                "unknown",
                source_artifacts=["autocatalyst-rubric.md"],
                unknown_reason="No rubric bullets were extracted from autocatalyst-rubric.md.",
            )
        )

    unknowns.append(
        make_claim(
            "Exact change diff for the winning candidate",
            None,
            "unknown",
            source_fields=["round.artifacts", "round.incumbentAfter"],
            unknown_reason="This report links artifacts, but it does not open or summarize file diffs on its own.",
        )
    )
    unknowns.append(
        make_claim(
            "Full critique text and full tribunal deliberation",
            None,
            "unknown",
            source_fields=["round.winnerReason", "round.judgeRanking", "round.notes"],
            unknown_reason="The report includes the logged outcome summary, not the complete subagent conversations.",
        )
    )
    unknowns.append(
        make_claim(
            "Blind-judging method details",
            None,
            "unknown",
            source_fields=["round.judgeRanking"],
            unknown_reason="The current report inputs do not include a separate field describing the judging protocol used in a round.",
        )
    )

    missing_reasons = sum(1 for row in rounds if not str(row.get("winnerReason", "")).strip())
    missing_rankings = sum(1 for row in rounds if not as_list(row.get("judgeRanking")))
    missing_benchmarks = sum(1 for row in rounds if not str(row.get("benchmarkSummary", "")).strip())
    missing_notes = sum(1 for row in rounds if not str(row.get("notes", "")).strip())

    unknowns.extend(
        [
            make_claim(
                "Rounds missing a winner reason",
                missing_reasons,
                "derived",
                source_fields=["round.winnerReason"],
            ),
            make_claim(
                "Rounds missing a judge ranking",
                missing_rankings,
                "derived",
                source_fields=["round.judgeRanking"],
            ),
            make_claim(
                "Rounds missing a benchmark summary",
                missing_benchmarks,
                "derived",
                source_fields=["round.benchmarkSummary"],
            ),
            make_claim(
                "Rounds missing operator notes",
                missing_notes,
                "derived",
                source_fields=["round.notes"],
            ),
        ]
    )
    return unknowns


def field_value(field: dict[str, Any] | None) -> str | None:
    if not field:
        return None
    value = field.get("value")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def field_items(field: dict[str, Any] | None) -> list[str]:
    if not field:
        return []
    return [str(item).strip() for item in field.get("items", []) if str(item).strip()]


def shorten(text: str | None, limit: int = 120) -> str:
    if not text:
        return ""
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def read_markdown_summary(path: Path) -> str | None:
    if not path.exists() or path.suffix.lower() != ".md":
        return None

    lines = path.read_text(encoding="utf-8").splitlines()
    current_heading = ""
    buffer: list[str] = []
    first_paragraph: list[str] = []

    def flush_paragraph(parts: list[str]) -> str | None:
        text = " ".join(part.strip() for part in parts if part.strip()).strip()
        return text or None

    for raw_line in lines:
        stripped = raw_line.strip()
        if stripped.startswith("## "):
            if current_heading.lower() == "summary":
                text = flush_paragraph(buffer)
                if text:
                    return text
                buffer = []
            current_heading = stripped[3:].strip()
            buffer = []
            continue
        if current_heading.lower() == "summary":
            if not stripped:
                text = flush_paragraph(buffer)
                if text:
                    return text
                buffer = []
                continue
            if not stripped.startswith("- "):
                buffer.append(stripped)
        else:
            if stripped.startswith("#"):
                continue
            if not stripped:
                text = flush_paragraph(first_paragraph)
                if text:
                    return text
                first_paragraph = []
                continue
            if not stripped.startswith("- "):
                first_paragraph.append(stripped)

    text = flush_paragraph(buffer) or flush_paragraph(first_paragraph)
    if text and text.endswith(":"):
        return text[:-1].rstrip() + "."
    return text


def story_artifact_path(root: Path, round_row: dict[str, Any]) -> Path | None:
    for path_str in as_list(round_row.get("artifacts")):
        lowered = path_str.lower()
        if "casefile" in lowered or "story" in lowered or "session-replay" in lowered:
            path = root / path_str
            if path.exists() and path.suffix.lower() == ".md":
                return path
    return None


def extract_story_artifact(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    sections = parse_markdown_sections(path)
    if not sections:
        return None

    for heading, section in sections.items():
        section["heading"] = heading

    def paragraph(heading: str) -> str | None:
        section = sections.get(heading, {})
        entry = first_paragraph(section)
        return entry.get("value") if entry else None

    def bullets(heading: str) -> list[str]:
        section = sections.get(heading, {})
        return [str(item.get("text", "")).strip() for item in section.get("items", []) if str(item.get("text", "")).strip()]

    def raw_text(heading: str) -> str | None:
        section = sections.get(heading)
        if not section:
            return None
        text = str(section.get("text", "")).strip()
        return text or None

    return {
        "path": str(path.relative_to(path.parent.parent.parent)) if path.parts else path.name,
        "summary": paragraph("Summary"),
        "ask": paragraph("The Ask"),
        "before": paragraph("The Situation Before The Round"),
        "sessionReplay": bullets("The Session Replay"),
        "contendersText": raw_text("The Contenders"),
        "decision": raw_text("The Decision"),
        "outcome": raw_text("The Outcome"),
        "unknowns": bullets("Unknowns And Limits"),
        "sourceFile": path.name,
    }


def classify_artifact(path_str: str) -> str | None:
    lowered = path_str.lower()
    name = Path(path_str).name.lower()
    if "casefile" in lowered or "story" in lowered or "session-replay" in lowered:
        return "story"
    if "critique" in lowered:
        return "critique"
    if "concept-ab" in lowered or "candidate-ab" in lowered or name.endswith("-ab.md"):
        return "ab"
    if "concept-b" in lowered or "candidate-b" in lowered or name.endswith("-b.md"):
        return "b"
    if "concept-a" in lowered or "candidate-a" in lowered or name.endswith("-a.md"):
        return "a"
    if "candidate-x" in lowered or "candidate-y" in lowered or "candidate-z" in lowered:
        return "candidate"
    return None


def classify_tribunal_artifact(path_str: str) -> str | None:
    lowered = path_str.lower()
    if "candidate-map" in lowered:
        return "candidate_map"
    if "tribunal-summary" in lowered:
        return "tribunal_summary"
    if "judge-" in lowered and "packet" in lowered:
        return "judge_packet"
    if "judge-" in lowered and "verdict" in lowered:
        return "judge_verdict"
    return None


def tribunal_artifact_paths(round_row: dict[str, Any]) -> list[str]:
    tribunal = round_row.get("tribunal")
    if not isinstance(tribunal, dict):
        return []

    paths: list[str] = []
    for key in ("candidateMapArtifact", "summaryArtifact", "summaryDataArtifact"):
        value = str(tribunal.get(key, "")).strip()
        if value:
            paths.append(value)

    for packet in as_list(tribunal.get("judgePackets")):
        if packet:
            paths.append(packet)

    raw_verdicts = tribunal.get("judgeVerdicts", [])
    if isinstance(raw_verdicts, list):
        for item in raw_verdicts:
            if isinstance(item, dict):
                value = str(item.get("artifact", "")).strip()
                if value:
                    paths.append(value)
            elif isinstance(item, str):
                value = item.strip()
                if value:
                    paths.append(value)

    return list(dict.fromkeys(paths))


def normalize_tribunal(round_row: dict[str, Any]) -> dict[str, Any]:
    tribunal = round_row.get("tribunal")
    if not isinstance(tribunal, dict):
        return {
            "candidateMapArtifact": "",
            "summaryArtifact": "",
            "summaryDataArtifact": "",
            "judgePackets": [],
            "aggregationMethod": "",
            "result": "",
            "note": "",
            "judgeVerdicts": [],
        }

    judge_verdicts: list[dict[str, Any]] = []
    raw_verdicts = tribunal.get("judgeVerdicts", [])
    if isinstance(raw_verdicts, list):
        for index, item in enumerate(raw_verdicts, start=1):
            if isinstance(item, dict):
                judge = str(item.get("judge", f"judge{index}")).strip() or f"judge{index}"
                artifact = str(item.get("artifact", "")).strip()
                ranking = as_list(item.get("ranking"))
                judge_verdicts.append(
                    {
                        "judge": judge,
                        "artifact": artifact,
                        "ranking": ranking,
                        "winner": str(item.get("winner", "")).strip(),
                        "rationale": str(item.get("rationale", "")).strip(),
                        "blockers": item.get("blockers", []) if isinstance(item.get("blockers", []), list) else [],
                    }
                )
            elif isinstance(item, str) and item.strip():
                judge_verdicts.append(
                    {
                        "judge": f"judge{index}",
                        "artifact": item.strip(),
                        "ranking": [],
                        "winner": "",
                        "rationale": "",
                        "blockers": [],
                    }
                )

    return {
        "candidateMapArtifact": str(tribunal.get("candidateMapArtifact", "")).strip(),
        "summaryArtifact": str(tribunal.get("summaryArtifact", "")).strip(),
        "summaryDataArtifact": str(tribunal.get("summaryDataArtifact", "")).strip(),
        "judgePackets": as_list(tribunal.get("judgePackets")),
        "aggregationMethod": str(tribunal.get("aggregationMethod", "")).strip(),
        "result": str(tribunal.get("result", "")).strip(),
        "note": str(tribunal.get("note", "")).strip(),
        "judgeVerdicts": judge_verdicts,
    }


def display_judge_name(name: str) -> str:
    lowered = name.lower().replace("-", "")
    if lowered.startswith("judge") and lowered[5:].isdigit():
        return f"Judge {lowered[5:]}"
    return name.replace("-", " ").title()


def tribunal_round_artifacts(round_row: dict[str, Any]) -> dict[str, list[str]]:
    grouped = {
        "candidate_map": [],
        "tribunal_summary": [],
        "judge_packet": [],
        "judge_verdict": [],
    }
    for path in as_list(round_row.get("artifacts")) + tribunal_artifact_paths(round_row):
        kind = classify_tribunal_artifact(path)
        if kind:
            grouped[kind].append(path)

    for key, items in grouped.items():
        grouped[key] = list(dict.fromkeys(items))
    return grouped


def collect_round_story(root: Path, round_row: dict[str, Any]) -> dict[str, Any]:
    artifact_paths = as_list(round_row.get("artifacts"))
    summaries: dict[str, str] = {}
    story_path: str | None = None
    tribunal = normalize_tribunal(round_row)
    for path_str in artifact_paths:
        kind = classify_artifact(path_str)
        if not kind:
            continue
        if kind == "story":
            story_path = path_str
            continue
        summary = read_markdown_summary(root / path_str)
        if summary and summary.endswith(":"):
            summary = summary[:-1].rstrip() + "."
        if summary:
            summaries[kind] = summary

    ranking = as_list(round_row.get("judgeRanking"))
    winner = str(round_row.get("winner", "A"))
    status = str(round_row.get("status", "keep"))
    winner_reason = str(round_row.get("winnerReason", "")).strip()

    if summaries.get("b") or summaries.get("ab") or summaries.get("a"):
        contenders: list[dict[str, Any]] = []
        for key, label in (("a", "A"), ("b", "B"), ("ab", "AB")):
            summary = summaries.get(key)
            if summary:
                contenders.append({"label": label, "summary": summary})
    else:
        contenders = [
            {"label": "A", "summary": "Keep the incumbent unchanged."},
            {"label": "B", "summary": "Revise the incumbent to answer the critique."},
            {"label": "AB", "summary": "Synthesize the strongest parts of A and B."},
        ]

    if ranking:
        ranking_text = " > ".join(ranking)
    else:
        ranking_text = f"{winner} won"

    if status == "promote":
        outcome_text = f"{winner} was promoted as the new incumbent."
    elif status == "keep":
        outcome_text = f"The incumbent survived and remained in place."
    else:
        outcome_text = f"The round ended with status {status}."

    return {
        "round": int(round_row.get("round", 0)),
        "critique": summaries.get("critique"),
        "contenders": contenders,
        "winner": winner,
        "status": status,
        "winnerReason": winner_reason,
        "rankingText": ranking_text,
        "outcomeText": outcome_text,
        "artifacts": artifact_paths,
        "promotions": as_list(round_row.get("promotions")),
        "benchmarkSummary": str(round_row.get("benchmarkSummary", "")).strip(),
        "notes": str(round_row.get("notes", "")).strip(),
        "hardChecks": str(round_row.get("hardChecks", "na")),
        "incumbentBefore": str(round_row.get("incumbentBefore", "")).strip(),
        "incumbentAfter": str(round_row.get("incumbentAfter", "")).strip(),
        "rowSpan": round_row.get("__sourceSpan"),
        "storyPath": story_path,
        "tribunal": tribunal,
    }


def render_source_note(spans: list[dict[str, Any]] | None = None, *, text: str | None = None) -> str:
    if spans:
        rendered = ", ".join(format_source_span(span) for span in spans)
        return f'<p class="source-note">Source: {rendered}</p>'
    if text:
        return f'<p class="source-note">{escape(text)}</p>'
    return ""


def build_story_mermaid(request_text: str, incumbent_text: str, stories: list[dict[str, Any]]) -> str:
    lines = ["flowchart TD"]
    lines.append(f'    ASK["User request: {sanitize(shorten(request_text, 72) or "No objective logged")}"]')
    lines.append(f'    START["Starting point: {sanitize(shorten(incumbent_text, 72) or "Current incumbent")}"]')
    lines.append("    ASK --> START")

    previous = "START"
    if not stories:
        lines.append("    START --> WAIT[No rounds logged yet]")
        return "\n".join(lines)

    for story in stories:
        rid = story["round"]
        challenge = f"R{rid}C"
        options = f"R{rid}O"
        verdict = f"R{rid}V"
        outcome = f"R{rid}N"
        critique_label = shorten(story.get("critique") or "The incumbent was challenged.", 68)
        winner_reason = shorten(story.get("winnerReason") or story.get("rankingText") or "A decision was made.", 68)
        lines.append(f'    {previous} --> {challenge}["Round {rid}: {sanitize(critique_label)}"]')
        lines.append(f'    {challenge} --> {options}["Contenders: {sanitize(", ".join(item["label"] for item in story["contenders"]))}"]')
        lines.append(f'    {options} --> {verdict}["Tribunal: {sanitize(story["rankingText"])}"]')
        lines.append(f'    {verdict} --> {outcome}["Winner {sanitize(story["winner"])}: {sanitize(winner_reason)}"]')
        previous = outcome

    lines.append(f'    {previous} --> END["Outcome: {sanitize(shorten(stories[-1]["outcomeText"], 72))}"]')
    return "\n".join(lines)


def render_scene(index: int, title: str, body: str, *, aside: str = "", source_note: str = "") -> str:
    aside_html = f'<p class="scene-aside">{escape(aside)}</p>' if aside else ""
    return (
        '<article class="scene">'
        f'<div class="scene-index">{index}</div>'
        '<div class="scene-body">'
        f'<h3>{escape(title)}</h3>'
        f'<p>{escape(body)}</p>'
        f'{aside_html}'
        f'{source_note}'
        '</div>'
        '</article>'
    )


def render_contender_card(label: str, summary: str, *, winner: bool = False) -> str:
    winner_html = '<p class="contender-kicker">Selected</p>' if winner else ""
    return (
        f'<article class="contender{" contender-winner" if winner else ""}">'
        f'{winner_html}'
        f'<h3>{escape(label)}</h3>'
        f'<p>{escape(summary)}</p>'
        '</article>'
    )


def render_unknown_list(claims: list[dict[str, Any]]) -> str:
    if not claims:
        return '<p class="empty-state">No explicit unknowns were detected.</p>'

    lines = ['<ul class="unknown-list">']
    for claim in claims:
        label = str(claim.get("label", "Unknown"))
        reason = str(claim.get("unknownReason", "")).strip()
        value = claim.get("value")
        if reason:
            text = reason
        elif value not in (None, ""):
            text = f"Current value: {value}"
        else:
            text = "Not logged."
        lines.append(f"<li><strong>{escape(label)}.</strong> {escape(text)}</li>")
    lines.append("</ul>")
    return "\n".join(lines)


def render_html_report(root: Path) -> str:
    rows = load_jsonl(root / "autocatalyst.jsonl")
    if not rows:
        return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>AutoCatalyst Report</title></head>
<body><h1>AutoCatalyst Report</h1><p>No session found.</p></body></html>
"""

    config, rounds = split_rows(rows)
    if config is None:
        raise ValueError("autocatalyst.jsonl must start with a config row")
    summary = collect_summary(config, rounds)
    brief = extract_session_brief(root)
    convergence = convergence_status(config, rounds)
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    latest = summary["latest"]
    stories = [collect_round_story(root, round_row) for round_row in rounds]
    latest_story = stories[-1] if stories else None
    authored_story = extract_story_artifact(story_artifact_path(root, rounds[-1])) if rounds else None
    objective = field_value(brief.get("objective")) or str(summary["name"])
    audience = field_value(brief.get("audience"))
    deliverables = field_value(brief.get("deliverables"))
    current_incumbent = field_value(brief.get("current_incumbent"))
    learned_items = field_items(brief.get("learned"))
    rubric_items = field_items(brief.get("rubric_snapshot"))
    constraints = field_items(brief.get("constraints"))
    off_limits = field_items(brief.get("off_limits"))

    convergence_reason = str(convergence["reason"])
    for prefix in ("Continue: ", "Stop: "):
        if convergence_reason.startswith(prefix):
            convergence_reason = convergence_reason[len(prefix) :]
            break

    request_source = brief.get("objective") or jsonl_span(config)
    request_note = (
        render_source_note([brief["objective"]], text=None)
        if brief.get("objective")
        else render_source_note(jsonl_span(config), text=None)
    )
    incumbent_problem = learned_items[0] if learned_items else (
        "The current report was not yet telling the session as a readable story."
    )
    request_summary = authored_story.get("ask") if authored_story else objective
    if latest_story and authored_story and authored_story.get("summary"):
        opening_summary = authored_story["summary"]
    elif latest_story:
        opening_summary = (
            f"Round {latest_story['round']} ended with {latest_story['winner']} winning "
            f"and status {latest_story['status']}. {latest_story['winnerReason'] or latest_story['outcomeText']}"
        )
    else:
        opening_summary = (
            "The redesign brief is configured, but no round outcome has been logged yet."
        )

    top_facts = [
        ("Task class", str(summary["task_class"])),
        ("Evidence mode", str(summary["evidence_mode"])),
        ("Rounds logged", str(summary["round_count"])),
        ("Convergence", f"{convergence['decision']} ({convergence['currentSurvivalStreak']}/{summary['survival_target']})"),
    ]
    if latest_story:
        top_facts.append(("Latest winner", str(latest_story["winner"])))
        top_facts.append(("Judge ranking", str(latest_story["rankingText"])))

    facts_rows = "".join(
        f"<tr><th scope=\"row\">{escape(label)}</th><td>{escape(value)}</td></tr>"
        for label, value in top_facts
    )

    scenes: list[str] = []
    if authored_story:
        scenes.append(
            render_scene(
                1,
                "The User Asked For A Real Session Replay",
                authored_story.get("ask") or request_summary,
                aside="This is the human-written session story artifact that the report now prefers over raw log reconstruction.",
                source_note=render_source_note(text=f"Source: {authored_story['sourceFile']}"),
            )
        )
        scenes.append(
            render_scene(
                2,
                "The Starting Point Was The Wrong Kind Of Report",
                authored_story.get("before") or (current_incumbent or "The incumbent was the current HTML report renderer output."),
                aside=incumbent_problem,
                source_note=render_source_note(text=f"Source: {authored_story['sourceFile']}"),
            )
        )
        for idx, step in enumerate(authored_story.get("sessionReplay", []), start=3):
            scenes.append(
                render_scene(
                    idx,
                    f"Session Replay Step {idx - 2}",
                    step,
                    source_note=render_source_note(text=f"Source: {authored_story['sourceFile']}"),
                )
            )
    else:
        scenes.append(
            render_scene(
                1,
                "The User Asked For A Real Session Replay",
                request_summary,
                aside="The report should explain the request, what happened, what was proposed, what was judged, why the winner won, and what changed.",
                source_note=request_note,
            )
        )
        scenes.append(
            render_scene(
                2,
                "The Starting Point Was The Wrong Kind Of Report",
                current_incumbent or "The incumbent was the current HTML report renderer output.",
                aside=incumbent_problem,
                source_note=render_source_note(
                    [brief["current_incumbent"]] if brief.get("current_incumbent") else jsonl_span(config),
                    text=None,
                ),
            )
        )

        scene_index = 3
        for story in stories:
            if story.get("critique"):
                scenes.append(
                    render_scene(
                        scene_index,
                        f"Round {story['round']} Produced A Critique",
                        str(story["critique"]),
                        aside="This critique defined what the challenger needed to fix.",
                        source_note=render_source_note([story["rowSpan"]] if story.get("rowSpan") else None),
                    )
                )
                scene_index += 1

            contender_line = " ".join(
                f"{item['label']}: {item['summary']}" for item in story["contenders"]
            )
            scenes.append(
                render_scene(
                    scene_index,
                    f"Round {story['round']} Explored Competing Directions",
                    contender_line,
                    aside="The contenders were compared as alternative editorial positions, not as raw log rows.",
                    source_note=render_source_note([story["rowSpan"]] if story.get("rowSpan") else None),
                )
            )
            scene_index += 1

            winner_reason = story["winnerReason"] or "The logged round selected it as the strongest option."
            if winner_reason.lower().startswith(story["winner"].lower()):
                decision_tail = winner_reason
            else:
                decision_tail = f"{story['winner']} won because {winner_reason}"
            decision_body = f"The judges ranked the options as {story['rankingText']}. {decision_tail}"
            decision_aside = f"Hard checks: {story['hardChecks']}. Outcome: {story['outcomeText']}"
            scenes.append(
                render_scene(
                    scene_index,
                    f"Round {story['round']} Reached A Verdict",
                    decision_body,
                    aside=decision_aside,
                    source_note=render_source_note([story["rowSpan"]] if story.get("rowSpan") else None),
                )
            )
            scene_index += 1

            if story.get("notes") or story.get("benchmarkSummary") or story.get("promotions"):
                outcome_bits = []
                if story.get("benchmarkSummary"):
                    outcome_bits.append(str(story["benchmarkSummary"]))
                if story.get("notes"):
                    outcome_bits.append(str(story["notes"]))
                if story.get("promotions"):
                    outcome_bits.append("Promoted criteria: " + "; ".join(story["promotions"]))
                scenes.append(
                    render_scene(
                        scene_index,
                        f"Round {story['round']} Changed The Direction",
                        " ".join(part for part in outcome_bits if part),
                        aside=(
                            f"Incumbent before: {story['incumbentBefore'] or 'not logged'}. "
                            f"Incumbent after: {story['incumbentAfter'] or 'not logged'}."
                        ),
                        source_note=render_source_note([story["rowSpan"]] if story.get("rowSpan") else None),
                    )
                )
                scene_index += 1

    contenders_html = ""
    if latest_story and authored_story and authored_story.get("contendersText"):
        contenders_html = (
            f'<article class="contender contender-winner"><h3>Casefile comparison</h3><p>{escape(authored_story["contendersText"])}</p></article>'
        )
    elif latest_story:
        contender_cards = [
            render_contender_card(
                item["label"],
                item["summary"],
                winner=item["label"] == latest_story["winner"],
            )
            for item in latest_story["contenders"]
        ]
        contenders_html = "\n".join(contender_cards)
    else:
        contenders_html = '<p class="empty-state">No contender set is available until a round is logged.</p>'

    if latest_story and authored_story and authored_story.get("decision"):
        verdict_reason = authored_story["decision"]
        latest_tribunal = latest_story.get("tribunal", {})
        tribunal_meta = []
        judge_verdicts = latest_tribunal.get("judgeVerdicts", []) if isinstance(latest_tribunal, dict) else []
        aggregation_method = latest_tribunal.get("aggregationMethod", "") if isinstance(latest_tribunal, dict) else ""
        if judge_verdicts:
            tribunal_meta.append(f"<div><dt>Blind judges</dt><dd>{len(judge_verdicts)} verdicts logged</dd></div>")
        if aggregation_method:
            tribunal_meta.append(f"<div><dt>Aggregation</dt><dd>{escape(aggregation_method)}</dd></div>")
        decision_html = f"""
        <div class="verdict">
          <p class="verdict-label">Winning direction</p>
          <h2>{escape(latest_story["winner"])}</h2>
          <p class="verdict-reason">{escape(verdict_reason)}</p>
          <dl class="verdict-meta">
            <div><dt>Ranking</dt><dd>{escape(latest_story["rankingText"])}</dd></div>
            <div><dt>Status</dt><dd>{escape(latest_story["status"])}</dd></div>
            <div><dt>Hard checks</dt><dd>{escape(latest_story["hardChecks"])}</dd></div>
            <div><dt>Convergence</dt><dd>{escape(convergence['decision'])} ({escape(str(convergence['currentSurvivalStreak']))}/{escape(str(summary['survival_target']))})</dd></div>
            {''.join(tribunal_meta)}
          </dl>
        </div>
        """
    elif latest_story:
        latest_tribunal = latest_story.get("tribunal", {})
        tribunal_meta = []
        judge_verdicts = latest_tribunal.get("judgeVerdicts", []) if isinstance(latest_tribunal, dict) else []
        aggregation_method = latest_tribunal.get("aggregationMethod", "") if isinstance(latest_tribunal, dict) else ""
        if judge_verdicts:
            tribunal_meta.append(f"<div><dt>Blind judges</dt><dd>{len(judge_verdicts)} verdicts logged</dd></div>")
        if aggregation_method:
            tribunal_meta.append(f"<div><dt>Aggregation</dt><dd>{escape(aggregation_method)}</dd></div>")
        decision_html = f"""
        <div class="verdict">
          <p class="verdict-label">Winning direction</p>
          <h2>{escape(latest_story["winner"])}</h2>
          <p class="verdict-reason">{escape(latest_story["winnerReason"] or latest_story["outcomeText"])}</p>
          <dl class="verdict-meta">
            <div><dt>Ranking</dt><dd>{escape(latest_story["rankingText"])}</dd></div>
            <div><dt>Status</dt><dd>{escape(latest_story["status"])}</dd></div>
            <div><dt>Hard checks</dt><dd>{escape(latest_story["hardChecks"])}</dd></div>
            <div><dt>Convergence</dt><dd>{escape(convergence['decision'])} ({escape(str(convergence['currentSurvivalStreak']))}/{escape(str(summary['survival_target']))})</dd></div>
            {''.join(tribunal_meta)}
          </dl>
        </div>
        """
    else:
        decision_html = """
        <div class="verdict">
          <p class="verdict-label">Current state</p>
          <h2>In progress</h2>
          <p class="verdict-reason">The brief exists, but the session has not logged a round outcome yet.</p>
        </div>
        """

    latest_promotions = latest_story.get("promotions", []) if latest_story else []
    outcome_lines = []
    if latest_story:
        outcome_lines.append(authored_story.get("outcome") if authored_story else latest_story["outcomeText"])
        if latest_story.get("incumbentAfter"):
            outcome_lines.append(f"The winning direction now points at {latest_story['incumbentAfter']}.")
        outcome_lines.append(convergence_reason)
    else:
        outcome_lines.append("The report can only show the ask and the starting position until a round result is logged.")

    unknowns = collect_unknowns(config, rounds, brief)
    artifacts = summary["artifact_paths"]
    latest_tribunal_html = render_tribunal_snapshot(root, latest_story)
    latest_critic_html = render_role_output_snapshot(latest or {}, "critic")
    latest_research_html = render_role_output_snapshot(latest or {}, "research")
    latest_tribunal_paths = []
    latest_role_artifacts = []
    if isinstance(latest, dict):
        for role_key in ("critic", "research"):
            payload = latest.get(role_key)
            if isinstance(payload, dict):
                artifact = str(payload.get("artifact", "")).strip()
                if artifact:
                    latest_role_artifacts.append(artifact)
    if latest_story:
        latest_tribunal_paths = list(
            dict.fromkeys(tribunal_round_artifacts({"artifacts": latest_story.get("artifacts", []), "tribunal": latest_story.get("tribunal", {})})["candidate_map"]
            + tribunal_round_artifacts({"artifacts": latest_story.get("artifacts", []), "tribunal": latest_story.get("tribunal", {})})["tribunal_summary"]
            + tribunal_round_artifacts({"artifacts": latest_story.get("artifacts", []), "tribunal": latest_story.get("tribunal", {})})["judge_packet"]
            + tribunal_round_artifacts({"artifacts": latest_story.get("artifacts", []), "tribunal": latest_story.get("tribunal", {})})["judge_verdict"])
        )
    generic_artifacts = [path for path in artifacts if path not in latest_tribunal_paths and path not in latest_role_artifacts]
    source_files = [
        "autocatalyst.jsonl",
        "autocatalyst.md",
        "autocatalyst-rubric.md",
        "autocatalyst-dashboard.md",
        "autocatalyst-artifacts/process-overview.md",
        "autocatalyst-artifacts/session-history.md",
        "autocatalyst-report.html",
    ]

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AutoCatalyst Report — {escape(str(summary['name']))}</title>
  <style>
    :root {{
      --page: #f4efe6;
      --paper: #fffdf8;
      --ink: #181512;
      --muted: #645b52;
      --line: #d8cec0;
      --line-strong: #a9957f;
      --accent: #7d2f0f;
      --accent-soft: #f6ebe4;
      --accent-2: #1f4e5f;
      --accent-2-soft: #e8f0f3;
      --success-soft: #eef3ea;
      --shadow: 0 1px 2px rgba(24, 21, 18, 0.06);
      font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
    }}
    body {{
      margin: 0;
      background: var(--page);
      color: var(--ink);
      line-height: 1.7;
    }}
    a {{
      color: var(--accent-2);
      text-decoration-thickness: 1px;
      text-underline-offset: 2px;
    }}
    .page {{
      max-width: 1040px;
      margin: 0 auto;
      padding: 28px 20px 56px;
    }}
    h1, h2, h3, h4 {{
      font-family: "Avenir Next", "Segoe UI", Helvetica, Arial, sans-serif;
      letter-spacing: -0.02em;
      line-height: 1.2;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(2.4rem, 5vw, 4rem);
    }}
    h2 {{
      margin: 0 0 14px;
      font-size: 1.5rem;
    }}
    h3 {{
      margin: 0 0 10px;
      font-size: 1.08rem;
    }}
    p, li, td, th, dd {{
      font-size: 1rem;
    }}
    .report-shell {{
      display: grid;
      grid-template-columns: minmax(0, 1.7fr) minmax(280px, 0.9fr);
      gap: 20px;
      align-items: start;
    }}
    .main-column,
    .side-column {{
      display: grid;
      gap: 18px;
    }}
    .lead-sheet,
    section,
    aside {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 12px;
      box-shadow: var(--shadow);
    }}
    .lead-sheet {{
      padding: 28px;
    }}
    section,
    aside {{
      padding: 22px;
    }}
    .deck-label,
    .verdict-label,
    .eyebrow {{
      margin: 0 0 10px;
      font: 600 0.82rem/1.2 "Avenir Next", "Segoe UI", Helvetica, Arial, sans-serif;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .lead-sheet p {{
      max-width: 62ch;
    }}
    .summary-line {{
      margin: 14px 0 0;
      font-size: 1.12rem;
    }}
    .lead-meta {{
      color: var(--muted);
      margin-top: 14px;
    }}
    .snapshot-table {{
      width: 100%;
      border-collapse: collapse;
    }}
    .snapshot-table th,
    .snapshot-table td {{
      text-align: left;
      padding: 10px 0;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    .snapshot-table th {{
      width: 46%;
      padding-right: 18px;
      font-weight: 600;
    }}
    .story-map {{
      margin-top: 18px;
    }}
    .story-map figcaption,
    .support-caption,
    .source-note,
    .evidence-note,
    .lead-meta,
    .scene-aside {{
      color: var(--muted);
      font-size: 0.93rem;
    }}
    .diagram {{
      margin-top: 10px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #fcfaf4;
      overflow: auto;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.92rem;
      white-space: pre-wrap;
    }}
    .storyline {{
      position: relative;
      padding-left: 32px;
    }}
    .storyline::before {{
      content: "";
      position: absolute;
      left: 9px;
      top: 8px;
      bottom: 8px;
      width: 2px;
      background: var(--line-strong);
    }}
    .scene {{
      position: relative;
      padding: 0 0 20px 20px;
    }}
    .scene:last-child {{
      padding-bottom: 0;
    }}
    .scene-index {{
      position: absolute;
      left: -32px;
      top: 2px;
      width: 24px;
      height: 24px;
      border-radius: 50%;
      background: var(--accent);
      color: #fff;
      display: grid;
      place-items: center;
      font: 700 0.82rem/1 "Avenir Next", "Segoe UI", Helvetica, Arial, sans-serif;
    }}
    .scene-body {{
      padding-bottom: 2px;
    }}
    .scene-body p {{
      margin: 0;
    }}
    .scene-aside {{
      margin-top: 8px;
    }}
    .contenders {{
      display: grid;
      gap: 12px;
    }}
    .contender {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 16px;
      background: #fbf8f2;
    }}
    .contender-winner {{
      background: var(--success-soft);
      border-color: #b8c3b2;
    }}
    .contender-kicker {{
      margin: 0 0 6px;
      color: var(--accent);
      font: 600 0.82rem/1.2 "Avenir Next", "Segoe UI", Helvetica, Arial, sans-serif;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}
    .verdict {{
      background: var(--accent-soft);
      border: 1px solid #dcc0b2;
      border-radius: 12px;
      padding: 18px;
    }}
    .verdict h2 {{
      margin: 0;
      font-size: 2rem;
    }}
    .verdict-reason {{
      margin: 12px 0 0;
      font-size: 1.05rem;
    }}
    .verdict-meta {{
      margin: 18px 0 0;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px 16px;
    }}
    .verdict-meta div {{
      padding-top: 10px;
      border-top: 1px solid rgba(125, 47, 15, 0.15);
    }}
    .verdict-meta dt {{
      font: 600 0.9rem/1.2 "Avenir Next", "Segoe UI", Helvetica, Arial, sans-serif;
      color: var(--muted);
    }}
    .verdict-meta dd {{
      margin: 4px 0 0;
    }}
    .plain-list,
    .unknown-list {{
      margin: 0;
      padding-left: 20px;
    }}
    .plain-list li + li,
    .unknown-list li + li {{
      margin-top: 8px;
    }}
    .evidence-drawer {{
      display: grid;
      gap: 18px;
    }}
    .drawer-block {{
      padding-top: 4px;
      border-top: 1px solid var(--line);
    }}
    .drawer-block:first-child {{
      padding-top: 0;
      border-top: 0;
    }}
    .empty-state {{
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #faf6ef;
      color: var(--muted);
    }}
    .pill-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 6px 10px;
      background: #fcfaf4;
      font: 500 0.9rem/1.2 "Avenir Next", "Segoe UI", Helvetica, Arial, sans-serif;
      color: var(--muted);
    }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.92em;
    }}
    @media (max-width: 720px) {{
      .page {{
        padding: 16px 14px 36px;
      }}
      .report-shell {{
        grid-template-columns: 1fr;
      }}
      .lead-sheet,
      section,
      aside {{
        padding: 18px;
      }}
      .verdict-meta {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="report-shell">
      <div class="main-column">
        <header class="lead-sheet">
          <p class="deck-label">Session Replay</p>
          <h1>{escape(request_summary)}</h1>
          <p class="summary-line">{escape(opening_summary)}</p>
          <p class="lead-meta">Generated {escape(generated_at)} from <code>autocatalyst.md</code>, <code>autocatalyst.jsonl</code>, and linked artifacts.</p>
          <div class="pill-list">
            {''.join(f'<span class="pill">{escape(item)}</span>' for item in ([f"Audience: {audience}"] if audience else []) + ([f"Deliverable: {deliverables}"] if deliverables else []) + ([f"Constraints: {len(constraints)} logged"] if constraints else []) + ([f"Off limits: {len(off_limits)} logged"] if off_limits else []))}
          </div>
        </header>

        <section>
          <p class="eyebrow">Story map</p>
          <h2>The Shape Of This Session</h2>
          <p>This diagram follows the actual path the session took: request, problem, contenders, tribunal, and outcome.</p>
          <figure class="story-map">
            <figcaption>The diagram is session-specific. It mirrors the logged round story instead of the generic AutoCatalyst workflow.</figcaption>
            <div class="diagram mermaid">{escape(build_story_mermaid(request_summary, current_incumbent or "Current report", stories))}</div>
          </figure>
        </section>

        <section>
          <p class="eyebrow">Chronology</p>
          <h2>What Happened</h2>
          <div class="storyline">
            {''.join(scenes) if scenes else '<p class="empty-state">No scenes are available.</p>'}
          </div>
        </section>

        <section>
          <p class="eyebrow">Contenders</p>
          <h2>The Competing Directions</h2>
          <p>The contenders are shown as editorial positions, not as raw candidate labels.</p>
          <div class="contenders">
            {contenders_html}
          </div>
        </section>

        <section>
          <p class="eyebrow">Decision</p>
          <h2>Why The Winner Won</h2>
          {decision_html}
          {html_list(latest_promotions, empty='No promoted criteria were logged for the latest round.')}
        </section>

        <section>
          <p class="eyebrow">Outcome</p>
          <h2>What Changed</h2>
          {html_list(outcome_lines, empty='No outcome was logged.')}
          <p class="support-caption">This closes the main story. Supporting evidence stays below so the first read remains focused on the session itself.</p>
        </section>
      </div>

      <div class="side-column">
        <aside>
          <p class="eyebrow">Snapshot</p>
          <h2>At A Glance</h2>
          <table class="snapshot-table">
            <tbody>
              {facts_rows}
            </tbody>
          </table>
        </aside>

        <aside>
          <p class="eyebrow">Rubric</p>
          <h2>What This Round Optimized For</h2>
          {html_list(rubric_items, empty='No rubric snapshot was logged.')}
        </aside>

        <aside>
          <p class="eyebrow">Evidence drawer</p>
          <h2>Supporting Material</h2>
          <div class="evidence-drawer">
            <div class="drawer-block">
              <h3>Core files</h3>
              {html_link_list(source_files, empty='No core report files are available.')}
            </div>
            <div class="drawer-block">
              <h3>Latest tribunal</h3>
              {latest_tribunal_html}
            </div>
            <div class="drawer-block">
              <h3>Latest critic</h3>
              {latest_critic_html}
            </div>
            <div class="drawer-block">
              <h3>Latest research</h3>
              {latest_research_html}
            </div>
            <div class="drawer-block">
              <h3>Round artifacts</h3>
              {html_link_list(generic_artifacts, empty='No non-tribunal round artifacts were linked.')}
            </div>
            <div class="drawer-block">
              <h3>Logged agents</h3>
              {html_list(summary['agent_names'], empty='No agent names were logged across rounds.')}
            </div>
            <div class="drawer-block">
              <h3>Still unknown</h3>
              {render_unknown_list(unknowns)}
            </div>
          </div>
          <p class="evidence-note">Evidence stays here on purpose. It is available for inspection, but it no longer drives the first read.</p>
        </aside>
      </div>
    </div>
  </div>
  <script type="module">
    import mermaid from "{MERMAID_CDN}";
    mermaid.initialize({{ startOnLoad: true, securityLevel: "loose", theme: "neutral" }});
  </script>
</body>
</html>
"""


def write_artifacts(root: Path) -> None:
    rows = load_jsonl(root / "autocatalyst.jsonl")
    if not rows:
        return
    config, rounds = load_session(root)

    artifacts_dir = root / "autocatalyst-artifacts"
    rounds_dir = artifacts_dir / "rounds"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    rounds_dir.mkdir(parents=True, exist_ok=True)

    (artifacts_dir / "process-overview.md").write_text(
        mermaid_markdown("AutoCatalyst Process Overview", process_overview_mermaid()),
        encoding="utf-8",
    )
    (artifacts_dir / "session-history.md").write_text(render_session_history(config, rounds), encoding="utf-8")
    for round_row in rounds:
        rid = int(round_row.get("round", 0))
        path = rounds_dir / f"round-{rid:03d}-flow.md"
        path.write_text(render_round_flow(round_row), encoding="utf-8")

    (root / "autocatalyst-report.html").write_text(render_html_report(root), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render AutoCatalyst dashboard and report files")
    parser.add_argument("--root", default=".", help="repository root or working directory")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = render_dashboard(root)
    out_path = root / "autocatalyst-dashboard.md"
    out_path.write_text(output, encoding="utf-8")
    write_artifacts(root)
    print(f"wrote {out_path} and autocatalyst-report.html")


if __name__ == "__main__":
    main()
