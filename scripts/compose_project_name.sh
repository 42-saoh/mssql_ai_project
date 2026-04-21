#!/usr/bin/env sh
set -eu

slugify() {
  printf '%s' "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//; s/-+/-/g'
}

prefix_raw="${TEST_COMPOSE_PROJECT_PREFIX:-codex}"
prefix="$(slugify "$prefix_raw")"
if [ -z "$prefix" ]; then
  prefix="codex"
fi

worktree_path="${WORKTREE_PATH:-}"
if [ -z "$worktree_path" ]; then
  if git rev-parse --show-toplevel >/dev/null 2>&1; then
    worktree_path="$(git rev-parse --show-toplevel)"
  else
    worktree_path="$(pwd)"
  fi
fi

if git -C "$worktree_path" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  branch="$(git -C "$worktree_path" rev-parse --abbrev-ref HEAD 2>/dev/null || printf 'detached')"
else
  branch="nogit"
fi

worktree_base="$(basename "$worktree_path")"
slug="$(slugify "${worktree_base}-${branch}")"
if [ -z "$slug" ]; then
  slug="workspace"
fi
slug="$(printf '%s' "$slug" | cut -c1-40)"

path_hash="$(printf '%s' "$worktree_path" | cksum | awk '{print $1}' | cut -c1-6)"

printf '%s-%s-%s\n' "$prefix" "$slug" "$path_hash"
