#!/usr/bin/env python3
"""Initialize repo-local AutoCatalyst session files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from textwrap import dedent

from install_subagents import install_subagents
from render_dashboard import render_dashboard, write_artifacts

AGENTS_BLOCK = dedent(
    """
    <!-- autocatalyst:start -->
    ## AutoCatalyst session rules
    When `autocatalyst.md` exists at the repository root:
    - Read `autocatalyst.md`, `autocatalyst.jsonl`, `autocatalyst-rubric.md`, `autocatalyst-dashboard.md`, and `autocatalyst-artifacts/` before proposing the next round.
    - Bootstrap missing session files or missing `.codex/agents/` files before the first round.
    - Run full AutoCatalyst mode with real subagents from `.codex/agents/`; do not simulate critic or judges in the main thread.
    - If subagents do not actually spawn, say `degraded single-agent mode` and stop unless the user explicitly accepts fallback.
    - Preserve the incumbent as a control arm.
    - Promote recurring critiques into rubric items, tests, or checks whenever possible.
    - Refresh the dashboard, Mermaid artifacts, and browser report after each logged round.
    <!-- autocatalyst:end -->
    """
).lstrip()

VALID_TASK_CLASSES = {"ideation", "planning", "implementation", "hybrid"}
VALID_EVIDENCE_MODES = {"judge-first", "benchmark-first", "hybrid"}

PROCESS_OVERVIEW = dedent(
    """
    # AutoCatalyst Process Overview

    ```mermaid
    flowchart TD
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
        N --> L
    ```
    """
).lstrip()

SESSION_HISTORY_PLACEHOLDER = dedent(
    """
    # Session History

    ```mermaid
    flowchart TD
        START[Session start] --> I0[Initial incumbent]
        I0 --> NEXT[No rounds logged yet]
    ```
    """
).lstrip()

ARTIFACTS_README = dedent(
    """
    # AutoCatalyst Artifacts

    Store durable deliverables here, such as:
    - concept.md
    - proposal.md
    - wireframe.md
    - spec.md
    - implementation-plan.md
    - change-summary.md
    - research-notes.md

    Auto-generated visualization files:
    - process-overview.md
    - session-history.md
    - rounds/round-<n>-flow.md
    - ../autocatalyst-report.html
    """
).lstrip()

ROUNDS_README = dedent(
    """
    # AutoCatalyst Round Artifacts

    Keep candidate-specific or round-specific files here, for example:
    - round-001-critique.md
    - round-001-candidate-b.md
    - round-001-candidate-ab.md
    - round-001-flow.md
    """
).lstrip()


def default_goal_for(repo_root: Path) -> str:
    repo_name = repo_root.name.strip() or "repository"
    return f"AutoCatalyst session for {repo_name}"


def write_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def ensure_agents_block(repo_root: Path) -> None:
    agents = repo_root / "AGENTS.md"
    text = agents.read_text(encoding="utf-8") if agents.exists() else ""
    if "<!-- autocatalyst:start -->" in text and "<!-- autocatalyst:end -->" in text:
        return
    if text and not text.endswith("\n"):
        text += "\n"
    text += ("\n" if text else "") + AGENTS_BLOCK
    agents.write_text(text, encoding="utf-8")


def init_session(
    repo_root: Path,
    goal: str,
    task_class: str,
    evidence_mode: str,
    survival_target: int,
    install_agents_md: bool,
    install_subagents_flag: bool,
) -> None:
    artifacts_dir = repo_root / "autocatalyst-artifacts"
    rounds_dir = artifacts_dir / "rounds"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    rounds_dir.mkdir(parents=True, exist_ok=True)

    session_md = dedent(
        f"""
        # AutoCatalyst: {goal}

        ## Objective
        {goal}

        ## Task Class
        {task_class}

        ## Evidence Mode
        {evidence_mode}

        ## Audience and Deliverables
        - Audience: [fill in]
        - Deliverables: [fill in]

        ## Constraints
        [fill in]

        ## Inputs
        [fill in]

        ## Files in Scope
        [fill in]

        ## Off Limits
        [fill in]

        ## Current Incumbent
        [fill in]

        ## Rubric Snapshot
        - Fits the stated objective and audience
        - Meets hard constraints
        - Is specific enough to act on
        - Improves the task materially, not cosmetically

        ## Survival Target
        {survival_target}

        ## What Has Been Learned
        [fill in]
        """
    ).lstrip()

    rubric_md = dedent(
        """
        # AutoCatalyst Rubric

        ## Core criteria
        - Fits the stated objective and audience
        - Meets hard constraints
        - Is specific enough to act on
        - Improves the task materially, not cosmetically

        ## Promoted criteria
        - [add recurring critiques here]
        """
    ).lstrip()

    dashboard_md = dedent(
        f"""
        # AutoCatalyst Dashboard: {goal}

        **Task class:** {task_class}  
        **Evidence mode:** {evidence_mode}  
        **Survival target:** {survival_target}  
        **Browser report:** `autocatalyst-report.html`

        No rounds logged yet.
        """
    ).lstrip()

    config = {
        "type": "config",
        "name": goal,
        "taskClass": task_class,
        "evidenceMode": evidence_mode,
        "survivalTarget": survival_target,
    }

    write_if_missing(repo_root / "autocatalyst.md", session_md)
    write_if_missing(repo_root / "autocatalyst-rubric.md", rubric_md)
    write_if_missing(repo_root / "autocatalyst-dashboard.md", dashboard_md)
    write_if_missing(artifacts_dir / "README.md", ARTIFACTS_README)
    write_if_missing(rounds_dir / "README.md", ROUNDS_README)
    write_if_missing(artifacts_dir / "process-overview.md", PROCESS_OVERVIEW)
    write_if_missing(artifacts_dir / "session-history.md", SESSION_HISTORY_PLACEHOLDER)

    jsonl = repo_root / "autocatalyst.jsonl"
    if not jsonl.exists():
        jsonl.write_text(json.dumps(config, ensure_ascii=False) + "\n", encoding="utf-8")

    if install_agents_md:
        ensure_agents_block(repo_root)

    if install_subagents_flag:
        install_subagents(repo_root=repo_root, overwrite=False, write_config_example=True)

    (repo_root / "autocatalyst-dashboard.md").write_text(render_dashboard(repo_root), encoding="utf-8")
    write_artifacts(repo_root)


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize AutoCatalyst session files")
    parser.add_argument("--root", default=".", help="repository root or working directory")
    parser.add_argument("--goal", default="", help="session goal/title; defaults to the repository name")
    parser.add_argument("--task-class", default="hybrid", choices=sorted(VALID_TASK_CLASSES))
    parser.add_argument("--evidence-mode", default="hybrid", choices=sorted(VALID_EVIDENCE_MODES))
    parser.add_argument("--survival-target", type=int, default=2)
    parser.add_argument("--install-agents-md", action="store_true")
    parser.add_argument("--install-agents", action="store_true", help="alias for --install-agents-md")
    parser.add_argument("--install-subagents", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    repo_root.mkdir(parents=True, exist_ok=True)
    goal = args.goal.strip() or default_goal_for(repo_root)
    init_session(
        repo_root=repo_root,
        goal=goal,
        task_class=args.task_class,
        evidence_mode=args.evidence_mode,
        survival_target=args.survival_target,
        install_agents_md=(args.install_agents_md or args.install_agents),
        install_subagents_flag=args.install_subagents,
    )
    print(f"initialized autocatalyst session in {repo_root}")


if __name__ == "__main__":
    main()
