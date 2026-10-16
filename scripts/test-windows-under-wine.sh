#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$#" -ne 0 ]; then
    echo "Usage: test-windows-under-wine.sh (no arguments; requires admitted overlay)" >&2
    exit 1
fi
exec python3 "${ROOT_DIR}/scripts/wine/artifacts.py" fast1800
