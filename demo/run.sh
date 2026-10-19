#!/usr/bin/env sh
# Live demo: change skills in a web page and watch Claude Code pick them up.
#
#   demo/run.sh ui              the demo page, http://127.0.0.1:8766 (terminal 1)
#   demo/run.sh claude          Claude Code with the skills server and the mods (terminal 2)
#   demo/run.sh claude-native   the same, with Claude Code's native MCP skills (see README)
#   demo/run.sh reset           start over: delete the demo workspaces and activity
#
# Run from anywhere; paths resolve against this repository. See demo/SCRIPT.md for the talk track.
set -eu

REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$REPO/demo/.work"
MODS="--plugin-dir $REPO/mods/skills-mcp --plugin-dir $REPO/mods/skills-mcp-commands --plugin-dir $REPO/mods/skills-mcp-browser"

case "${1:-}" in
  ui)
    exec uv run --directory "$REPO/server" skills-mcp-ui --demo-dir "$REPO/demo"
    ;;
  claude | claude-native)
    [ -L "$WORK/active" ] || { echo "Start the demo page first: demo/run.sh ui" >&2; exit 1; }
    cd "$REPO"
    if [ "$1" = claude-native ]; then
      export CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF=1
    fi
    # shellcheck disable=SC2086
    exec claude --mcp-config demo/mcp.json --strict-mcp-config $MODS
    ;;
  reset)
    rm -rf "$WORK"
    echo "Removed $WORK; demo/run.sh ui makes a fresh 'main' workspace with the starter skills."
    ;;
  *)
    sed -n '2,10p' "$0"
    exit 2
    ;;
esac
