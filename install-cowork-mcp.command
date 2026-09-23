#!/bin/bash
#
# install-cowork-mcp.command -- double-click to register the Arc MCP server
# with the Claude desktop app (Cowork).
#
# Why this exists: the desktop app rewrites claude_desktop_config.json from its
# own in-memory state whenever it is running, so an entry added while the app is
# open is silently discarded. The entry only sticks if it is written while the
# app is fully quit. This script quits the app, writes the entry, and reopens it.
#
# Run it from Finder (double-click), not from a terminal inside the Claude app:
# quitting the app would kill that terminal along with it.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
ENTRY="$SCRIPT_DIR/gui/scripts/run_mcp.py"
APP_PATTERN='[C]laude.app/Contents/MacOS/Claude'

say()  { printf '%s\n' "$*"; }
step() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; }

finish() {
    local code=$?
    if [ -t 0 ]; then
        printf '\nPress Return to close this window. '
        read -r _ || true
    fi
    exit "$code"
}
trap finish EXIT

say "Arc MCP -> Claude desktop app (Cowork)"

step "Checking the Arc MCP server"
[ -x "$VENV_PYTHON" ] || { fail "No Python environment at $VENV_PYTHON
  Run ./arc.command once first -- it builds the environment."; exit 1; }
[ -f "$ENTRY" ]       || { fail "Missing $ENTRY"; exit 1; }
"$VENV_PYTHON" "$ENTRY" --help >/dev/null 2>&1 \
    || { fail "The MCP server failed to start. Run ./arc.command --reinstall."; exit 1; }
say "Server entry point OK."

step "Quitting the Claude app"
if pgrep -f "$APP_PATTERN" >/dev/null 2>&1; then
    osascript -e 'quit app "Claude"' >/dev/null 2>&1 || true
    for _ in $(seq 1 40); do
        pgrep -f "$APP_PATTERN" >/dev/null 2>&1 || break
        sleep 0.5
    done
    if pgrep -f "$APP_PATTERN" >/dev/null 2>&1; then
        fail "The Claude app is still running. Quit it manually (Cmd+Q), then run this again."
        exit 1
    fi
    say "App quit."
    sleep 3   # let the app finish its own last write
else
    say "App was not running."
fi

step "Writing the configuration"
[ -f "$CONFIG" ] || printf '{"mcpServers":{}}\n' > "$CONFIG"
cp "$CONFIG" "$CONFIG.bak-$(date +%Y%m%d%H%M%S)"

PYTHON3="$(command -v python3 || true)"
[ -n "$PYTHON3" ] || PYTHON3="$VENV_PYTHON"

"$PYTHON3" - "$CONFIG" "$VENV_PYTHON" "$ENTRY" <<'PY'
import json, sys

config_path, python_path, entry_path = sys.argv[1:4]
with open(config_path) as stream:
    config = json.load(stream)
config.setdefault("mcpServers", {})["arc"] = {
    "command": python_path,
    "args": [entry_path],
}
with open(config_path, "w") as stream:
    json.dump(config, stream, indent=2, ensure_ascii=False)
print("  mcpServers now: " + ", ".join(config["mcpServers"]))
PY

step "Reopening the Claude app"
open -a Claude
say "Done."
say ""
say "Check: Claude app -> connector/MCP list -> 'arc' with 8 tools."
say ""
say "If the tools are listed but return \"No active Arc session\", that is"
say "expected: run ./arc.command, finish the password/MFA login, and keep that"
say "terminal open. The MCP server reads that session; it never stores your"
say "Snowflake credentials."
