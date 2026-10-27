#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$#" -ne 0 ]; then
    echo "Usage: prepare-windows-wine-runtime.sh (no arguments)" >&2
    exit 1
fi
exec python3 "${ROOT_DIR}/scripts/wine/artifacts.py" prepare
