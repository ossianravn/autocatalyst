#!/usr/bin/env python3
"""Run the first matching AutoCatalyst checks hook in a cross-platform way."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

HOOK_PRIORITY = [
    "autocatalyst.checks.py",
    "autocatalyst.checks.ps1",
    "autocatalyst.checks.cmd",
    "autocatalyst.checks.bat",
    "autocatalyst.checks.sh",
]


def find_hook(repo_root: Path) -> Path | None:
    for name in HOOK_PRIORITY:
        candidate = repo_root / name
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def launcher_for(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".py":
        python = sys.executable or shutil.which("python3") or shutil.which("python")
        if not python:
            raise RuntimeError("No Python interpreter found to run autocatalyst.checks.py")
        return [python, str(path)]
    if suffix == ".ps1":
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not powershell:
            raise RuntimeError("No PowerShell launcher found to run autocatalyst.checks.ps1")
        return [powershell, "-ExecutionPolicy", "Bypass", "-File", str(path)]
    if suffix in {".cmd", ".bat"}:
        comspec = os.environ.get("COMSPEC") or shutil.which("cmd") or shutil.which("cmd.exe")
        if not comspec:
            raise RuntimeError(f"No cmd launcher found to run {path.name}")
        return [comspec, "/c", str(path)]
    if suffix == ".sh":
        shell = shutil.which("sh") or shutil.which("bash")
        if not shell:
            raise RuntimeError("No POSIX shell found to run autocatalyst.checks.sh")
        return [shell, str(path)]
    raise RuntimeError(f"Unsupported checks hook: {path.name}")


def run_hook(repo_root: Path, extra_args: Sequence[str]) -> dict[str, object]:
    hook = find_hook(repo_root)
    if hook is None:
        return {
            "status": "na",
            "hook": None,
            "exitCode": 0,
            "stdout": "",
            "stderr": "",
            "message": "No checks hook found.",
        }

    command = launcher_for(hook) + list(extra_args)
    result = subprocess.run(
        command,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    status = "pass" if result.returncode == 0 else "fail"
    return {
        "status": status,
        "hook": hook.name,
        "exitCode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": command,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the first matching AutoCatalyst checks hook")
    parser.add_argument("--root", default=".", help="repository root or working directory")
    parser.add_argument(
        "hook_args",
        nargs=argparse.REMAINDER,
        help="optional arguments passed through to the hook after `--`",
    )
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    extra_args = list(args.hook_args)
    if extra_args and extra_args[0] == "--":
        extra_args = extra_args[1:]
    payload = run_hook(repo_root, extra_args)
    print(json.dumps(payload, indent=2))
    if payload["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
