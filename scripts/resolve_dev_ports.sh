#!/bin/sh
set -eu

worktree_path=${WORKTREE_PATH:-$(pwd)}
worktree_name=$(basename "$worktree_path")
slot_override=${WORKTREE_PORT_SLOT:-}

resolve_slot() {
  if [ -n "$slot_override" ]; then
    printf '%s\n' "$slot_override"
    return 0
  fi

  case "$worktree_name" in
    p[0-9][0-9]-*|p[0-9][0-9])
      printf '%s\n' "$worktree_name" | sed -E 's/^p0*([0-9]+).*/\1/'
      return 0
      ;;
  esac

  cksum_value=$(printf '%s' "$worktree_path" | cksum | awk '{print $1}')
  printf '%s\n' $((cksum_value % 40 + 20))
}

slot=$(resolve_slot)
case "$slot" in
  ''|*[!0-9]*)
    echo "WORKTREE_PORT_SLOT must be numeric when provided: $slot" >&2
    exit 2
    ;;
esac

app_port=$((8000 + slot))
mcp_port=$((8100 + slot))
web_port=$((3000 + slot))

output=${1:-ALL}
case "$output" in
  PORT_SLOT)
    printf '%s\n' "$slot"
    ;;
  APP_PORT)
    printf '%s\n' "$app_port"
    ;;
  MCP_PORT)
    printf '%s\n' "$mcp_port"
    ;;
  WEB_PORT)
    printf '%s\n' "$web_port"
    ;;
  ALL)
    printf 'WORKTREE_NAME=%s\n' "$worktree_name"
    printf 'PORT_SLOT=%s\n' "$slot"
    printf 'APP_PORT=%s\n' "$app_port"
    printf 'MCP_PORT=%s\n' "$mcp_port"
    printf 'WEB_PORT=%s\n' "$web_port"
    ;;
  *)
    echo "Unsupported output selector: $output" >&2
    exit 2
    ;;
esac
