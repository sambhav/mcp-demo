#!/usr/bin/env sh
# Turns on Claude Code's native MCP Skills support (SEP-2640, io.modelcontextprotocol/skills).
#
# Claude Code (seen in 2.1.296) ships a client for the MCP Skills extension behind the
# remote feature flag `tengu_mcp_skills`, off by default. This script turns it on locally:
#
#   1. sets cachedGrowthBookFeatures.tengu_mcp_skills = true in ~/.claude.json (the flag cache)
#   2. tells you to export the two variables that make Claude Code read that cache instead of
#      fetching flags:
#        CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1    stops the flag fetch (and telemetry,
#                                                      error reporting, other non-essential calls)
#        CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF=1  reads the flag cache while it is stopped
#
# UNSUPPORTED: this relies on undocumented internals that can change in any release. Every
# other flag stays at its cached value while the fetch is off. Works with the Anthropic API
# (or a first-party-compatible gateway), not Bedrock/Vertex/Foundry.
#
# Usage:
#   scripts/enable-native-mcp-skills.sh            enable (backs up ~/.claude.json first)
#   scripts/enable-native-mcp-skills.sh --rc FILE  enable and append the exports to FILE
#   scripts/enable-native-mcp-skills.sh --status   show whether it is on
#   scripts/enable-native-mcp-skills.sh --disable  remove the flag from the cache
set -eu

CONFIG="${CLAUDE_CONFIG_DIR:-$HOME}/.claude.json"
FLAG=tengu_mcp_skills
EXPORTS='export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
export CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF=1'

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
[ -f "$CONFIG" ] || { echo "No $CONFIG: run claude once first" >&2; exit 1; }

set_flag() { # $1: true | delete
  python3 - "$CONFIG" "$FLAG" "$1" <<'PY'
import json, os, sys
path, flag, action = sys.argv[1:]
config = json.load(open(path))
cache = config.setdefault("cachedGrowthBookFeatures", {})
if action == "true":
    cache[flag] = True
else:
    cache.pop(flag, None)
tmp = path + ".tmp"
with open(tmp, "w") as f:
    json.dump(config, f, indent=2)
os.replace(tmp, path)
PY
}

status() {
  cached=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('cachedGrowthBookFeatures',{}).get(sys.argv[2]))" "$CONFIG" "$FLAG")
  echo "flag cache ($CONFIG): $FLAG = $cached"
  echo "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = ${CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC:-<unset>}"
  echo "CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF = ${CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF:-<unset>}"
}

case "${1:-}" in
  --status)
    status
    ;;
  --disable)
    set_flag delete
    echo "Removed $FLAG from $CONFIG. Unset the two exports (or drop them from your shell rc) as well."
    ;;
  ""|--rc)
    backup="$CONFIG.bak-mcp-skills.$(date +%Y%m%d%H%M%S)"
    cp "$CONFIG" "$backup"
    set_flag true
    echo "Set $FLAG = true in $CONFIG (backup: $backup)."
    if [ "${1:-}" = "--rc" ]; then
      rc="${2:?--rc needs a file, e.g. ~/.zshrc}"
      if ! grep -q CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF "$rc" 2>/dev/null; then
        printf '\n# Claude Code: native MCP skills (scripts/enable-native-mcp-skills.sh)\n%s\n' "$EXPORTS" >> "$rc"
      fi
      echo "Added the exports to $rc; open a new shell."
    else
      echo "Now export these in the shell you start claude from (or rerun with --rc ~/.zshrc):"
      echo "$EXPORTS"
    fi
    echo "Check: claude --debug, then look for 'Found N skills via skills/list' in the debug log."
    ;;
  *)
    sed -n '2,25p' "$0"
    exit 2
    ;;
esac
