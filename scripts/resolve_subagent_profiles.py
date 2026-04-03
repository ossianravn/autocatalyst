#!/usr/bin/env python3
"""Resolve repo-local AutoCatalyst subagent model profiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for older Python
    import tomli as tomllib  # type: ignore

ALIASES = {
    "planner": "autocatalyst_planner",
    "researcher": "autocatalyst_researcher",
    "critic": "autocatalyst_critic",
    "rewriter": "autocatalyst_rewriter",
    "synthesizer": "autocatalyst_synthesizer",
    "judge": "autocatalyst_judge",
    "autocatalyst_planner": "autocatalyst_planner",
    "autocatalyst_researcher": "autocatalyst_researcher",
    "autocatalyst_critic": "autocatalyst_critic",
    "autocatalyst_rewriter": "autocatalyst_rewriter",
    "autocatalyst_synthesizer": "autocatalyst_synthesizer",
    "autocatalyst_judge": "autocatalyst_judge",
}

ROLE_ORDER = [
    "autocatalyst_planner",
    "autocatalyst_researcher",
    "autocatalyst_critic",
    "autocatalyst_rewriter",
    "autocatalyst_synthesizer",
    "autocatalyst_judge",
]

VALID_REASONING_EFFORTS = {"low", "medium", "high", "xhigh"}


def normalize_profile(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    profile: dict[str, str] = {}
    for key in ("model", "reasoning_effort"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            profile[key] = value.strip()
    return profile


def canonical_role(name: str) -> str:
    key = name.strip()
    if key not in ALIASES:
        raise KeyError(f"Unknown AutoCatalyst role: {name}")
    return ALIASES[key]


def default_config_path(repo_root: Path) -> Path:
    return repo_root / ".codex" / "autocatalyst-models.toml"


def resolve_profiles(repo_root: Path, config_path: Path | None = None) -> dict[str, object]:
    path = (config_path or default_config_path(repo_root)).resolve()
    exists = path.exists()
    if not exists:
        return {
            "configPath": None,
            "profiles": {role: {} for role in ROLE_ORDER},
            "warnings": [],
        }

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    defaults = normalize_profile(data.get("defaults"))
    roles = data.get("roles") if isinstance(data.get("roles"), dict) else {}
    profiles: dict[str, dict[str, str]] = {}
    warnings: list[str] = []
    normalized_roles: dict[str, object] = {}

    default_effort = defaults.get("reasoning_effort")
    if default_effort and default_effort not in VALID_REASONING_EFFORTS:
        warnings.append(
            f"Invalid default reasoning_effort '{default_effort}'. Expected one of: "
            + ", ".join(sorted(VALID_REASONING_EFFORTS))
        )

    for key, value in roles.items():
        try:
            normalized_roles[canonical_role(str(key))] = value
        except KeyError:
            warnings.append(f"Ignoring unknown role key '{key}' in {path.name}.")

    for role in ROLE_ORDER:
        merged = dict(defaults)
        raw_role_profile = normalized_roles.get(role, {})
        role_profile = normalize_profile(raw_role_profile)
        effort = role_profile.get("reasoning_effort")
        if effort and effort not in VALID_REASONING_EFFORTS:
            warnings.append(
                f"Invalid reasoning_effort '{effort}' for {role}. Expected one of: "
                + ", ".join(sorted(VALID_REASONING_EFFORTS))
            )
        merged.update(role_profile)
        profiles[role] = merged

    return {
        "configPath": str(path),
        "profiles": profiles,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve AutoCatalyst subagent model profiles")
    parser.add_argument("--root", default=".", help="repository root or working directory")
    parser.add_argument("--config", default="", help="explicit path to autocatalyst-models.toml")
    parser.add_argument("--role", default="", help="optional role alias or agent name to filter")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    config_path = Path(args.config).resolve() if args.config else None
    payload = resolve_profiles(repo_root=repo_root, config_path=config_path)
    if args.role:
        role = canonical_role(args.role)
        payload["profiles"] = {role: payload["profiles"][role]}
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
