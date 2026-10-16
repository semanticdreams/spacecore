#!/usr/bin/env bash
# Private shared admission consumer. No receipt is sourced or evaluated as shell.

resolve_wine_cmd() {
    local selected
    if [ -n "${WINE_CMD:-}" ]; then
        selected="${WINE_CMD}"
    elif command -v wine64 >/dev/null 2>&1; then
        selected=wine64
    elif command -v wine >/dev/null 2>&1; then
        selected=wine
    else
        echo "Missing required command: wine64 or wine" >&2
        return 1
    fi
    command -v "${selected}" || return 1
}

configure_admitted_wine_runtime() {
    local configuration
    local -a values
    python3 "${ROOT_DIR}/scripts/wine/artifacts.py" check-build || return 1
    # Lock the directory inode, not a symlink-following lockfile. Keep this FD
    # open through exec so preparation/package replacement cannot race the app.
    exec {WINDOWS_RUNTIME_LOCK}<"${ROOT_DIR}/build"
    flock -x "${WINDOWS_RUNTIME_LOCK}" || return 1
    configuration="$(python3 "${ROOT_DIR}/scripts/wine/artifacts.py" configuration)" || return 1
    mapfile -t values <<< "${configuration}"
    if [ "${#values[@]}" -ne 2 ]; then
        echo "Invalid admission configuration" >&2
        return 1
    fi
    WINE_CMD="${values[0]}"
    export WINEDLLOVERRIDES="${values[1]}"
    CLI_EXE="${ROOT_DIR}/build/wine/windows/space-cli.exe"
    export SPACE_BIN="${CLI_EXE}"
    export SPACE_ASSETS_PATH="${ROOT_DIR}/build/wine/windows/assets"
    export FENNEL_PATH="${SPACE_ASSETS_PATH}/lua/?.fnl;${SPACE_ASSETS_PATH}/lua/?/init.fnl"
    export FENNEL_MACRO_PATH="${FENNEL_PATH}"
}
