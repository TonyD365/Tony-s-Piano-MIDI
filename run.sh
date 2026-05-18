#!/usr/bin/env bash
# Starts midi_bridge.py + cloudflared, prints + copies the tunnel URL.
# All the heavy lifting is in launcher.py so this stays trivially simple.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="${HERE}/.venv/bin/python"

if [[ -x "${VENV_PY}" ]]; then
    exec "${VENV_PY}" "${HERE}/launcher.py"
else
    echo "Python venv not found at ${VENV_PY}"
    echo "Create it first:"
    echo "  python3 -m venv \"${HERE}/.venv\""
    echo "  \"${HERE}/.venv/bin/pip\" install -r \"${HERE}/requirements.txt\""
    exit 1
fi
