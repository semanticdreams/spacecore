#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$#" -gt 1 ]; then
    echo "Usage: package-windows-runtime.sh [new-or-owned-output-directory]" >&2
    exit 1
fi
exec python3 "${ROOT_DIR}/scripts/wine/artifacts.py" package "$@"
