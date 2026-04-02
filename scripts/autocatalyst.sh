#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN=${AUTOCATALYST_PYTHON:-}

if [ -z "$PYTHON_BIN" ]; then
  for candidate in python3 python py; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN=$candidate
      break
    fi
  done
fi

if [ -z "$PYTHON_BIN" ]; then
  echo "AutoCatalyst: could not find python3, python, or py in PATH." >&2
  exit 1
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/bootstrap.py" "$@"
