#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$#" -ne 0 ]; then
    echo "Usage: test-windows-under-wine.sh (no arguments; requires admitted overlay)" >&2
    exit 1
fi
for setting in TEST_FILTER SPACE_TEST_CASE_TIMEOUT_SECONDS TEST_SUITE SPACE_TEST_SUITE TEST_MODULES SPACE_TEST_MODULES; do
    if [ -n "${!setting:-}" ]; then
        echo "Conflicting inherited full-fast setting: ${setting}" >&2
        exit 1
    fi
done
for setting in SPACE_MATRIX_TEST SPACE_REALTIME_TEST; do
    if [ "${!setting:-}" = 1 ]; then
        echo "Conflicting inherited full-fast setting: ${setting}" >&2
        exit 1
    fi
done
source "${ROOT_DIR}/scripts/wine/runtime.sh"
configure_admitted_wine_runtime
cd "${ROOT_DIR}"
echo "[LAUNCH] Wine full fast module=tests.fast:main deadline=180s TEST_VERBOSE=1 SPACE_TEST_TIMINGS=1"
exec timeout 180s env \
    TEST_VERBOSE=1 \
    SPACE_TEST_TIMINGS=1 \
    SKIP_KEYRING_TESTS=1 \
    XDG_DATA_HOME=/tmp/space/tests/xdg-data \
    PWD="${ROOT_DIR}" \
    SPACE_DISABLE_AUDIO=1 \
    "${WINE_CMD}" "${CLI_EXE}" -m tests.fast:main
