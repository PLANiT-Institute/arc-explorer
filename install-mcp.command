#!/bin/bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
finish() { local code=$?; if [ -t 0 ]; then read -r -p "Press Return to close. " _ || true; fi; exit "$code"; }
trap finish EXIT
PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    PYTHON="$(command -v python3)"
fi
"$PYTHON" "$ROOT/gui/scripts/install_mcp.py" "$@"
