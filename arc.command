#!/bin/bash
#
# arc.command -- double-click this file to connect to the Transition Arc
# warehouse.
#
# It prepares the Python environment (creating it on first run), checks that
# .env is filled in, signs you in to Snowflake, reports what your session can
# see, and caches the schema for the Arc Explorer GUI.
#
# Sign-in follows SNOWFLAKE_AUTHENTICATOR in .env: browser single sign-on by
# default, or Snowflake's own login, a key pair, or a token. See .env.example.
#
# Nothing here hardcodes a Snowflake account, role or warehouse: every
# coordinate comes from .env, which mirrors .env.example.
#
# Usage (double-click, or from a terminal):
#   ./arc.command                    connect, verify, cache the schema if missing
#   ./arc.command --refresh-schema   re-read the table/column catalogue
#   ./arc.command --no-schema        only check the connection
#   ./arc.command --authenticator snowflake
#                                    try one sign-in method without editing .env
#   ./arc.command --reinstall        rebuild the Python environment first
#   ./arc.command --help             this message
#
# Set ARC_NO_PAUSE=1 to skip the "press Return" prompt in scripted use.

set -euo pipefail

SCRIPT_PATH="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/$(basename -- "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname -- "$SCRIPT_PATH")"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
STAMP_FILE="$VENV_DIR/.arc-bootstrap"
CONNECT_SCRIPT="$SCRIPT_DIR/gui/scripts/connect.py"
LOG_DIR="$SCRIPT_DIR/gui/data"
LOG_FILE="$LOG_DIR/arc-launcher.log"
MIN_PYTHON="3.11"

PAUSE_AT_END=1
REINSTALL=0
PYTHON_ARGS=()

# ---------------------------------------------------------------- output ----

say()  { printf '%s\n' "$*"; }
step() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; }

# Print the header comment block, which is the only copy of the usage text.
usage() {
    awk 'NR < 3 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' \
        "$SCRIPT_PATH"
}

# Keep the Terminal window readable when Finder launched it: without this the
# window closes on exit and the reader never sees the error.
finish() {
    local code=$?
    if [ "$PAUSE_AT_END" -eq 1 ] && [ -t 0 ]; then
        printf '\nLog written to %s\n' "$LOG_FILE"
        printf 'Press Return to close this window. '
        read -r _ || true
    fi
    exit "$code"
}

# ------------------------------------------------------------ interpreter ----

# Finder-launched scripts can start with a thinner PATH than a login shell, so
# probe the usual install locations before giving up on a tool.
find_tool() {
    local name="$1" candidate
    if command -v "$name" >/dev/null 2>&1; then
        command -v "$name"
        return 0
    fi
    for candidate in "$HOME/.local/bin/$name" "/opt/homebrew/bin/$name" \
                     "/usr/local/bin/$name"; do
        if [ -x "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

# Echo the first python3 that is new enough to run this project.
find_python() {
    local candidate
    for candidate in "$(command -v python3 2>/dev/null || true)" \
                     /opt/homebrew/bin/python3 /usr/local/bin/python3 \
                     /usr/bin/python3; do
        [ -n "$candidate" ] && [ -x "$candidate" ] || continue
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
             >/dev/null 2>&1; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

# Does the environment already have everything the connection needs?
venv_is_usable() {
    [ -x "$VENV_PYTHON" ] || return 1
    "$VENV_PYTHON" - <<'PY' >/dev/null 2>&1
import importlib.util
import sys

for module in ("snowflake.connector", "dotenv", "pandas", "arc_explorer.connection"):
    if importlib.util.find_spec(module) is None:
        sys.exit(1)
PY
}

pyproject_fingerprint() {
    /sbin/md5 -q "$SCRIPT_DIR/pyproject.toml" 2>/dev/null \
        || md5 -q "$SCRIPT_DIR/pyproject.toml" 2>/dev/null \
        || md5sum "$SCRIPT_DIR/pyproject.toml" | cut -d' ' -f1
}

bootstrap_with_uv() {
    local uv="$1"
    say "Using uv ($uv) to sync the environment from pyproject.toml."
    "$uv" sync --extra dev --extra mcp
}

bootstrap_with_pip() {
    local python="$1"
    say "uv not found; falling back to $python and pip."

    if [ ! -x "$VENV_PYTHON" ]; then
        say "Creating $VENV_DIR ..."
        "$python" -m venv "$VENV_DIR"
    fi

    # A uv-created environment has no pip; add one before installing.
    if ! "$VENV_PYTHON" -m pip --version >/dev/null 2>&1; then
        "$VENV_PYTHON" -m ensurepip --upgrade >/dev/null 2>&1 || true
    fi
    if ! "$VENV_PYTHON" -m pip --version >/dev/null 2>&1; then
        fail "The environment at $VENV_DIR has no pip and ensurepip failed.
  Install uv (https://docs.astral.sh/uv/) or delete .venv and run this again."
        return 1
    fi

    "$VENV_PYTHON" -m pip install --upgrade pip >/dev/null
    "$VENV_PYTHON" -m pip install -e ".[dev,mcp]"
}

bootstrap() {
    local fingerprint uv python
    fingerprint="$(pyproject_fingerprint)"

    if [ "$REINSTALL" -eq 0 ] && venv_is_usable \
       && [ -f "$STAMP_FILE" ] && [ "$(cat "$STAMP_FILE")" = "$fingerprint" ]; then
        say "Python environment is up to date."
        return 0
    fi

    if [ "$REINSTALL" -eq 1 ] && [ -d "$VENV_DIR" ]; then
        say "Removing $VENV_DIR ..."
        rm -rf "$VENV_DIR"
    fi

    if uv="$(find_tool uv)"; then
        bootstrap_with_uv "$uv"
    elif python="$(find_python)"; then
        bootstrap_with_pip "$python"
    else
        fail "No Python $MIN_PYTHON or newer was found, and neither was uv.
  Install uv, which brings its own Python:
      curl -LsSf https://astral.sh/uv/install.sh | sh
  then double-click this file again."
        return 1
    fi

    if ! venv_is_usable; then
        fail "The environment was installed but is still missing packages.
  Try again with:  ./arc.command --reinstall"
        return 1
    fi

    printf '%s' "$fingerprint" > "$STAMP_FILE"
    say "Python environment ready."
}

# ------------------------------------------------------------------- .env ----

ensure_env_file() {
    if [ -f "$SCRIPT_DIR/.env" ]; then
        return 0
    fi
    if [ ! -f "$SCRIPT_DIR/.env.example" ]; then
        fail "Neither .env nor .env.example exists in $SCRIPT_DIR."
        return 1
    fi

    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    fail "No .env file existed, so one was created from .env.example.

  Open this file:
      $SCRIPT_DIR/.env
  set SNOWFLAKE_USER to your own work email address, save it,
  then double-click arc.command again."
    return 1
}

# The connection check lives in the PLANiT-local gui/ layer, which is kept out
# of the shared Arc sandbox repository.
ensure_connect_script() {
    if [ -f "$CONNECT_SCRIPT" ]; then
        return 0
    fi
    fail "This clone has no $CONNECT_SCRIPT.

  arc.command drives the PLANiT-local gui/ layer, which is excluded from the
  shared arc-sandbox/planit-sandbox repository. Copy the gui/ directory in
  from a colleague, or use the Arc-supplied helper instead:
      examples/example_python_script.py"
    return 1
}

# ------------------------------------------------------------------- main ----

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)   usage; exit 0 ;;
        --reinstall) REINSTALL=1 ;;
        --no-pause)  PAUSE_AT_END=0 ;;
        *)           PYTHON_ARGS+=("$1") ;;
    esac
    shift
done

[ "${ARC_NO_PAUSE:-0}" = "1" ] && PAUSE_AT_END=0
[ -t 1 ] && printf '\033]0;Transition Arc\007'

mkdir -p "$LOG_DIR"
# Keep a copy of everything for support, while still showing it live.
exec > >(tee "$LOG_FILE") 2>&1
trap finish EXIT

say "Transition Arc -- $(date '+%Y-%m-%d %H:%M:%S')"
say "Repository: $SCRIPT_DIR"

step "Checking the Python environment"
ensure_connect_script
bootstrap

step "Checking configuration"
ensure_env_file
say "Reading connection settings from $SCRIPT_DIR/.env"

step "Terminal sign-in (username, password and current MFA code)"
# Unbuffered, or stdout arrives after stderr once tee makes it a pipe and the
# report reads out of order.
PYTHONUNBUFFERED=1 "$VENV_PYTHON" "$CONNECT_SCRIPT" \
    ${PYTHON_ARGS[@]+"${PYTHON_ARGS[@]}"}
