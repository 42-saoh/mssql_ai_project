#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PNPM_BIN=${PNPM:-pnpm}
LOCK_FILE="$REPO_ROOT/pnpm-lock.yaml"

cd "$REPO_ROOT"

if [ -f "$LOCK_FILE" ]; then
  exec "$PNPM_BIN" install --frozen-lockfile
fi

if [ "${ALLOW_UNLOCKED_PNPM_INSTALL:-0}" = "1" ]; then
  echo "WARN: pnpm-lock.yaml missing; proceeding with unlocked install because ALLOW_UNLOCKED_PNPM_INSTALL=1" >&2
  exec "$PNPM_BIN" install --no-frozen-lockfile
fi

cat >&2 <<'EOF'
pnpm-lock.yaml is missing.
For reproducible parallel Codex runs, generate and commit the lockfile once from the coordinator worktree:
  corepack enable
  corepack use pnpm@10.33.0
  pnpm install
Then rerun the command.
To bypass temporarily, set ALLOW_UNLOCKED_PNPM_INSTALL=1.
EOF
exit 2
