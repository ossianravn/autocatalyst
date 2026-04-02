#!/usr/bin/env python3
"""Install project-scoped AutoCatalyst custom agents into .codex/agents/."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PLACEHOLDER = "__SKILL_MD_PATH_JSON__"


def write_text(path: Path, content: str, overwrite: bool) -> bool:
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def install_subagents(repo_root: Path, overwrite: bool = False, write_config_example: bool = True) -> dict[str, list[str]]:
    script_dir = Path(__file__).resolve().parent
    skill_root = script_dir.parent
    skill_md = (skill_root / "SKILL.md").resolve()
    assets_dir = skill_root / "assets" / "subagents"
    config_asset = skill_root / "assets" / "config" / "autocatalyst-config.example.toml"

    if not skill_md.exists():
        raise FileNotFoundError(f"Missing SKILL.md at {skill_md}")
    if not assets_dir.exists():
        raise FileNotFoundError(f"Missing subagent templates at {assets_dir}")

    agent_dir = repo_root / ".codex" / "agents"
    agent_dir.mkdir(parents=True, exist_ok=True)

    skill_md_json = json.dumps(str(skill_md))
    written: list[str] = []
    skipped: list[str] = []

    for template in sorted(assets_dir.glob("*.toml.template")):
        target = agent_dir / template.name.replace(".template", "")
        content = template.read_text(encoding="utf-8").replace(PLACEHOLDER, skill_md_json)
        if write_text(target, content, overwrite=overwrite):
            written.append(str(target.relative_to(repo_root)))
        else:
            skipped.append(str(target.relative_to(repo_root)))

    if write_config_example and config_asset.exists():
        config_target = repo_root / ".codex" / "autocatalyst-config.example.toml"
        if write_text(config_target, config_asset.read_text(encoding="utf-8"), overwrite=overwrite):
            written.append(str(config_target.relative_to(repo_root)))
        else:
            skipped.append(str(config_target.relative_to(repo_root)))

    readme = repo_root / ".codex" / "README.autocatalyst.md"
    readme_text = (
        "# AutoCatalyst subagents\n\n"
        "These project-scoped custom agents were installed by the AutoCatalyst skill.\n\n"
        "The generated agent files live in `.codex/agents/`.\n\n"
        "## Refreshing the install\n\n"
        "Re-run the AutoCatalyst bootstrap from the repository root after the repo moves or after you update the skill.\n\n"
        "### Repo-local skill install\n\n"
        "- PowerShell: `./.agents/skills/autocatalyst/scripts/autocatalyst.ps1 --root . --overwrite-subagents`\n"
        "- macOS / Linux / WSL: `sh ./.agents/skills/autocatalyst/scripts/autocatalyst.sh --root . --overwrite-subagents`\n\n"
        "### Global skill install\n\n"
        "Run the matching wrapper or `bootstrap.py` by absolute path, but keep `--root .` pointed at this repository.\n"
    )
    if write_text(readme, readme_text, overwrite=overwrite):
        written.append(str(readme.relative_to(repo_root)))
    else:
        skipped.append(str(readme.relative_to(repo_root)))

    return {"written": written, "skipped": skipped}


def main() -> None:
    parser = argparse.ArgumentParser(description="Install AutoCatalyst project-scoped custom agents")
    parser.add_argument("--root", default=".", help="repository root or working directory")
    parser.add_argument("--overwrite", action="store_true", help="overwrite existing agent files")
    parser.add_argument(
        "--skip-config-example",
        action="store_true",
        help="do not write .codex/autocatalyst-config.example.toml",
    )
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    repo_root.mkdir(parents=True, exist_ok=True)
    result = install_subagents(
        repo_root=repo_root,
        overwrite=args.overwrite,
        write_config_example=not args.skip_config_example,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
