#!/usr/bin/env python3
"""Idempotent AutoCatalyst bootstrap for any repository and any supported shell."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from init_session import default_goal_for, ensure_agents_block, init_session
from install_subagents import install_subagents
from render_dashboard import load_jsonl, render_dashboard, split_rows, write_artifacts

REQUIRED_AGENT_FILES = [
    "autocatalyst_planner.toml",
    "autocatalyst_researcher.toml",
    "autocatalyst_critic.toml",
    "autocatalyst_rewriter.toml",
    "autocatalyst_synthesizer.toml",
    "autocatalyst_judge.toml",
]

REQUIRED_SESSION_FILES = [
    "autocatalyst.md",
    "autocatalyst.jsonl",
    "autocatalyst-rubric.md",
    "autocatalyst-dashboard.md",
    "autocatalyst-artifacts/process-overview.md",
    "autocatalyst-artifacts/session-history.md",
]


def existing_config(repo_root: Path) -> dict[str, object] | None:
    rows = load_jsonl(repo_root / "autocatalyst.jsonl")
    config, _ = split_rows(rows)
    return config


def missing_session_files(repo_root: Path) -> list[str]:
    return [name for name in REQUIRED_SESSION_FILES if not (repo_root / name).exists()]


def missing_agent_files(repo_root: Path) -> list[str]:
    return [name for name in REQUIRED_AGENT_FILES if not (repo_root / ".codex" / "agents" / name).exists()]


def bootstrap(
    repo_root: Path,
    goal: str,
    task_class: str,
    evidence_mode: str,
    survival_target: int,
    install_agents_md: bool,
    overwrite_subagents: bool,
    skip_subagents: bool,
) -> dict[str, object]:
    repo_root.mkdir(parents=True, exist_ok=True)

    actions: list[str] = []
    session_missing_before = missing_session_files(repo_root)
    agent_missing_before = missing_agent_files(repo_root)
    config = existing_config(repo_root)

    if not skip_subagents and (overwrite_subagents or agent_missing_before):
        install_subagents(repo_root=repo_root, overwrite=overwrite_subagents, write_config_example=True)
        actions.append("installed subagents" if overwrite_subagents or agent_missing_before else "checked subagents")

    if config is None or session_missing_before:
        existing_goal = str(config.get("name", "")).strip() if config else ""
        existing_task_class = str(config.get("taskClass", "")).strip() if config else ""
        existing_evidence_mode = str(config.get("evidenceMode", "")).strip() if config else ""
        chosen_goal = goal.strip() or existing_goal or default_goal_for(repo_root)
        chosen_task_class = task_class or existing_task_class or "hybrid"
        chosen_evidence_mode = evidence_mode or existing_evidence_mode or "hybrid"
        init_session(
            repo_root=repo_root,
            goal=chosen_goal,
            task_class=chosen_task_class,
            evidence_mode=chosen_evidence_mode,
            survival_target=survival_target if survival_target > 0 else int(config.get("survivalTarget", 2)) if config else 2,
            install_agents_md=install_agents_md,
            install_subagents_flag=(not skip_subagents),
        )
        actions.append("initialized session")
    else:
        if install_agents_md:
            ensure_agents_block(repo_root)
            actions.append("updated AGENTS.md")
        (repo_root / "autocatalyst-dashboard.md").write_text(render_dashboard(repo_root), encoding="utf-8")
        write_artifacts(repo_root)
        actions.append("refreshed dashboard and report")

    return {
        "repoRoot": str(repo_root),
        "actions": actions,
        "missingSessionFilesBefore": session_missing_before,
        "missingAgentFilesBefore": agent_missing_before,
        "missingSessionFilesAfter": missing_session_files(repo_root),
        "missingAgentFilesAfter": missing_agent_files(repo_root),
        "report": str(repo_root / "autocatalyst-report.html"),
        "dashboard": str(repo_root / "autocatalyst-dashboard.md"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap AutoCatalyst in a repository")
    parser.add_argument("--root", default=".", help="repository root or working directory")
    parser.add_argument("--goal", default="", help="goal or session title; defaults to the repository name")
    parser.add_argument("--task-class", default="hybrid", choices=["ideation", "planning", "implementation", "hybrid"])
    parser.add_argument("--evidence-mode", default="hybrid", choices=["judge-first", "benchmark-first", "hybrid"])
    parser.add_argument("--survival-target", type=int, default=2)
    parser.add_argument("--install-agents-md", action="store_true")
    parser.add_argument("--install-agents", action="store_true", help="alias for --install-agents-md")
    parser.add_argument("--overwrite-subagents", action="store_true")
    parser.add_argument("--skip-subagents", action="store_true")
    args = parser.parse_args()

    payload = bootstrap(
        repo_root=Path(args.root).resolve(),
        goal=args.goal,
        task_class=args.task_class,
        evidence_mode=args.evidence_mode,
        survival_target=args.survival_target,
        install_agents_md=(args.install_agents_md or args.install_agents),
        overwrite_subagents=args.overwrite_subagents,
        skip_subagents=args.skip_subagents,
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
