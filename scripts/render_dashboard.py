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


MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
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
    rows = load_jsonl(root / "autocatalyst.jsonl")
    if not rows:
        return "# AutoCatalyst Dashboard\n\nNo session found.\n"

    config, rounds = split_rows(rows)
    if config is None:
        raise ValueError("autocatalyst.jsonl must start with a config row")

    summary = collect_summary(config, rounds)
    counts = summary["counts"]
    winner_counts = summary["winner_counts"]
    latest = summary["latest"]

    lines: list[str] = []
    lines.append(f"# AutoCatalyst Dashboard: {summary['name']}")
    lines.append("")
    lines.append(f"**Task class:** {summary['task_class']}  ")
    lines.append(f"**Evidence mode:** {summary['evidence_mode']}  ")
    lines.append(f"**Survival target:** {summary['survival_target']}  ")
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


def html_badge(text: str, tone: str = "neutral") -> str:
    return f'<span class="badge badge-{escape(tone)}">{escape(text)}</span>'


def html_list(items: list[str], empty: str = "none") -> str:
    if not items:
        return f"<p class=\"muted\">{escape(empty)}</p>"
    lines = ["<ul class=\"list\">"]
    for item in items:
        lines.append(f"  <li>{escape(item)}</li>")
    lines.append("</ul>")
    return "\n".join(lines)


def html_link_list(items: list[str], empty: str = "none") -> str:
    if not items:
        return f"<p class=\"muted\">{escape(empty)}</p>"
    lines = ["<ul class=\"list\">"]
    for item in items:
        href = rel_href(item)
        lines.append(f'  <li><a href="{href}">{escape(item)}</a></li>')
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
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    round_rows: list[str] = []
    for round_row in rounds:
        rid = int(round_row.get("round", 0))
        winner = sanitize(round_row.get("winner", "A"))
        status = sanitize(round_row.get("status", "keep"))
        reason = sanitize(round_row.get("winnerReason", "")) or "No reason logged."
        hard_checks = sanitize(round_row.get("hardChecks", "na"))
        ranking = ", ".join(as_list(round_row.get("judgeRanking"))) or "not logged"
        agents = as_list(round_row.get("agentNames"))
        promotions = as_list(round_row.get("promotions"))
        artifacts = as_list(round_row.get("artifacts"))
        benchmark_summary = sanitize(round_row.get("benchmarkSummary", ""))
        notes = sanitize(round_row.get("notes", ""))
        degraded = bool(round_row.get("degradedMode"))
        tone = {
            "promote": "good",
            "keep": "neutral",
            "mixed": "warn",
            "blocked": "bad",
            "rejected": "bad",
        }.get(status, "neutral")
        round_rows.append(
            f"""
<details class="round-card" {'open' if rid == len(rounds) else ''}>
  <summary>
    <div class="round-summary">
      <strong>Round {rid}</strong>
      <div class="badge-row">
        {html_badge(f'winner {winner}', 'good' if winner in {'B', 'AB'} else 'neutral')}
        {html_badge(status, tone)}
        {html_badge(f'hard checks {hard_checks}', 'neutral')}
        {html_badge('degraded mode' if degraded else 'full mode', 'warn' if degraded else 'good')}
      </div>
    </div>
  </summary>
  <div class="round-body">
    <p>{escape(reason)}</p>
    <div class="diagram mermaid">{escape(round_flow_mermaid(round_row))}</div>
    <div class="round-grid">
      <section>
        <h4>Judge ranking</h4>
        <p>{escape(ranking)}</p>
      </section>
      <section>
        <h4>Agents logged</h4>
        {html_list(agents, empty='No agents logged.')}
      </section>
      <section>
        <h4>Artifacts</h4>
        {html_link_list(artifacts, empty='No artifacts logged.')}
      </section>
      <section>
        <h4>Promoted criteria</h4>
        {html_list(promotions, empty='No promoted criteria logged.')}
      </section>
    </div>
    {f'<p><strong>Benchmark summary:</strong> {escape(benchmark_summary)}</p>' if benchmark_summary else ''}
    {f'<p><strong>Notes:</strong> {escape(notes)}</p>' if notes else ''}
  </div>
</details>
"""
        )

    round_table_rows = []
    for round_row in rounds:
        ranking = ", ".join(as_list(round_row.get("judgeRanking"))) or "—"
        degraded = "yes" if bool(round_row.get("degradedMode")) else "no"
        round_table_rows.append(
            "<tr>"
            f"<td>{escape(str(round_row.get('round', '')))}</td>"
            f"<td>{escape(str(round_row.get('winner', '')))}</td>"
            f"<td>{escape(str(round_row.get('status', '')))}</td>"
            f"<td>{escape(sanitize(round_row.get('hardChecks', 'na')))}</td>"
            f"<td>{escape(ranking)}</td>"
            f"<td>{escape(degraded)}</td>"
            f"<td>{escape(sanitize(round_row.get('winnerReason', '')))}</td>"
            "</tr>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AutoCatalyst Report — {escape(str(summary['name']))}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #0b1020;
      --panel: #121a2f;
      --panel-2: #18213a;
      --text: #eef3ff;
      --muted: #b7c2e3;
      --accent: #7aa2ff;
      --good: #2bb673;
      --warn: #d9a441;
      --bad: #d65c5c;
      --border: rgba(255,255,255,0.12);
      --shadow: 0 20px 40px rgba(0,0,0,0.28);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    body {{
      margin: 0;
      background: linear-gradient(180deg, #0b1020 0%, #10182d 100%);
      color: var(--text);
      line-height: 1.5;
    }}
    a {{ color: #93b4ff; }}
    .page {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 72px; }}
    .hero, .panel, .round-card {{ background: rgba(18, 26, 47, 0.88); border: 1px solid var(--border); border-radius: 18px; box-shadow: var(--shadow); }}
    .hero {{ padding: 28px; margin-bottom: 24px; }}
    .hero h1 {{ margin: 0 0 12px; font-size: clamp(2rem, 4vw, 3rem); line-height: 1.1; }}
    .hero p {{ margin: 8px 0 0; color: var(--muted); max-width: 72ch; }}
    .chip-row, .badge-row {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .chip-row {{ margin-top: 16px; }}
    .badge {{ display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 999px; font-size: 0.9rem; border: 1px solid var(--border); background: rgba(255,255,255,0.05); }}
    .badge-good {{ border-color: rgba(43,182,115,.45); color: #b9f5d5; background: rgba(43,182,115,.14); }}
    .badge-warn {{ border-color: rgba(217,164,65,.45); color: #ffe6b3; background: rgba(217,164,65,.14); }}
    .badge-bad {{ border-color: rgba(214,92,92,.45); color: #ffd2d2; background: rgba(214,92,92,.14); }}
    .grid {{ display: grid; gap: 20px; }}
    .summary-grid {{ grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin-bottom: 24px; }}
    .two-up {{ grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }}
    .card {{ background: rgba(255,255,255,0.035); border: 1px solid var(--border); border-radius: 16px; padding: 18px; }}
    .card h3, .panel h2, .panel h3 {{ margin-top: 0; }}
    .metric {{ font-size: 1.8rem; font-weight: 700; margin: 6px 0; }}
    .muted {{ color: var(--muted); }}
    .panel {{ padding: 24px; margin-bottom: 24px; }}
    .diagram {{ background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 14px; padding: 12px; overflow: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.95rem; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 600; }}
    .round-card {{ margin-bottom: 16px; overflow: hidden; }}
    .round-card summary {{ list-style: none; cursor: pointer; padding: 18px 20px; }}
    .round-card summary::-webkit-details-marker {{ display: none; }}
    .round-summary {{ display: flex; gap: 16px; align-items: center; justify-content: space-between; flex-wrap: wrap; }}
    .round-body {{ padding: 0 20px 20px; }}
    .round-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-top: 16px; }}
    .list {{ margin: 0; padding-left: 18px; }}
    .footer {{ margin-top: 32px; color: var(--muted); font-size: 0.92rem; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <h1>AutoCatalyst Report</h1>
      <p>{escape(str(summary['name']))}</p>
      <div class="chip-row">
        {html_badge(f"task class: {summary['task_class']}", 'neutral')}
        {html_badge(f"evidence mode: {summary['evidence_mode']}", 'neutral')}
        {html_badge(f"rounds: {summary['round_count']}", 'neutral')}
        {html_badge(f"survival target: {summary['survival_target']}", 'neutral')}
        {html_badge(f"degraded rounds: {summary['degraded_count']}", 'warn' if summary['degraded_count'] else 'good')}
      </div>
      <p class="muted">Generated {escape(generated_at)} from <code>autocatalyst.jsonl</code>. This report stays readable even if Mermaid does not load; diagrams will then appear as raw source blocks.</p>
    </section>

    <section class="grid summary-grid">
      <div class="card"><h3>Rounds logged</h3><div class="metric">{summary['round_count']}</div><p class="muted">Total tribunal decisions captured so far.</p></div>
      <div class="card"><h3>Latest winner</h3><div class="metric">{escape(str(summary['latest'].get('winner', '—')) if summary['latest'] else '—')}</div><p class="muted">{escape(sanitize(summary['latest'].get('winnerReason', 'No rounds logged yet.')) if summary['latest'] else 'No rounds logged yet.')}</p></div>
      <div class="card"><h3>Status counts</h3><div class="metric">P {summary['counts'].get('promote', 0)} · K {summary['counts'].get('keep', 0)}</div><p class="muted">Mixed {summary['counts'].get('mixed', 0)} · Blocked {summary['counts'].get('blocked', 0)} · Rejected {summary['counts'].get('rejected', 0)}</p></div>
      <div class="card"><h3>Winner counts</h3><div class="metric">A {summary['winner_counts'].get('A', 0)} / B {summary['winner_counts'].get('B', 0)} / AB {summary['winner_counts'].get('AB', 0)}</div><p class="muted">How often the incumbent, rewrite, or synthesis won.</p></div>
      <div class="card"><h3>Agents observed</h3><div class="metric">{len(summary['agent_names'])}</div><p class="muted">Unique agent names logged across rounds.</p></div>
      <div class="card"><h3>Promoted criteria</h3><div class="metric">{len(summary['promotions'])}</div><p class="muted">Recurring critiques converted into durable checks or rubric items.</p></div>
    </section>

    <section class="panel grid two-up">
      <div>
        <h2>Process overview</h2>
        <div class="diagram mermaid">{escape(process_overview_mermaid())}</div>
      </div>
      <div>
        <h2>Session history</h2>
        <div class="diagram mermaid">{escape(session_history_mermaid(config, rounds))}</div>
      </div>
    </section>

    <section class="panel">
      <h2>What happened</h2>
      <table>
        <thead>
          <tr>
            <th>Round</th>
            <th>Winner</th>
            <th>Status</th>
            <th>Hard checks</th>
            <th>Judge ranking</th>
            <th>Degraded</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {''.join(round_table_rows) if round_table_rows else '<tr><td colspan="7" class="muted">No rounds logged yet.</td></tr>'}
        </tbody>
      </table>
    </section>

    <section class="panel grid two-up">
      <div>
        <h2>Agents that actually ran</h2>
        {html_list(summary['agent_names'], empty='No agents logged yet.')}
      </div>
      <div>
        <h2>Promoted criteria</h2>
        {html_list(summary['promotions'], empty='No promoted criteria yet.')}
      </div>
      <div>
        <h2>Artifact files</h2>
        {html_link_list(summary['artifact_paths'], empty='No artifact files logged yet.')}
      </div>
      <div>
        <h2>Core report files</h2>
        <ul class="list">
          <li><a href="autocatalyst.md">autocatalyst.md</a></li>
          <li><a href="autocatalyst-rubric.md">autocatalyst-rubric.md</a></li>
          <li><a href="autocatalyst-dashboard.md">autocatalyst-dashboard.md</a></li>
          <li><a href="autocatalyst-artifacts/process-overview.md">autocatalyst-artifacts/process-overview.md</a></li>
          <li><a href="autocatalyst-artifacts/session-history.md">autocatalyst-artifacts/session-history.md</a></li>
        </ul>
      </div>
    </section>

    <section class="panel">
      <h2>Round details</h2>
      {''.join(round_rows) if round_rows else '<p class="muted">No rounds logged yet. Run AutoCatalyst and then refresh this report.</p>'}
    </section>

    <p class="footer">AutoCatalyst browser report. Mermaid diagrams load from <code>{escape(MERMAID_CDN)}</code>.</p>
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
    config, rounds = split_rows(rows)
    if config is None:
        raise ValueError("autocatalyst.jsonl must start with a config row")

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
