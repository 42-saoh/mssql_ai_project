#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PYTHON_BIN=${PYTHON:-python}
LOCK_FILE=${PYTHON_LOCK_FILE:-$REPO_ROOT/requirements/lock/py314-dev.txt}

if [ ! -f "$LOCK_FILE" ]; then
  echo "Python lock file not found: $LOCK_FILE" >&2
  exit 2
fi

cd "$REPO_ROOT"
"$PYTHON_BIN" -m pip install -c "$LOCK_FILE" -e ".[dev]"
