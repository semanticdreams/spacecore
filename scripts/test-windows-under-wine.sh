#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$#" -ne 0 ]; then
    echo "Usage: test-windows-under-wine.sh (no arguments; requires admitted overlay)" >&2
    exit 1
fi
source "${ROOT_DIR}/scripts/wine/runtime.sh"
configure_admitted_wine_runtime
cd "${ROOT_DIR}"
exec timeout 180s env \
    SKIP_KEYRING_TESTS=1 \
    XDG_DATA_HOME=/tmp/space/tests/xdg-data \
    PWD="${ROOT_DIR}" \
    SPACE_DISABLE_AUDIO=1 \
    "${WINE_CMD}" "${CLI_EXE}" -m tests.fast:main
