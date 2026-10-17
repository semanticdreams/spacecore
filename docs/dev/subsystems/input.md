---
type: subsystem
tags:
  - subsystem
  - input
created: 2026-07-14
---

# Input system

Keyboard, mouse, gamepad, touch, and stylus input handling. Composable state architecture for per-widget input routing, directional focus traversal, focus ordering, and SDL3 event pipeline.

## Key files

- `src/input_state.h`, `src/input_keyboard_state.h`, `src/input_mouse_state.h`, `src/input_gamepad_state.h`
- `assets/lua/state-handlers/` — focus, hover, pointer, camera, gamepad, touch, pen handlers
- `assets/lua/input-state-router.fnl`, `assets/lua/touch-router.fnl`

## Dependencies

- Depends on: [Core Platform](/dev/features/core-platform)
- Depended on by: [Layout Widget Engine](/dev/features/layout-widget-engine), [Activities Architecture](/dev/features/activities)

## Native dial adapter boundary

`dial-type.InputDialType(input-state)` requires a non-null native `InputState` userdata (normally `app.engine.input`), not a Lua input fixture table or another userdata type. The factory checks full userdata and native type before extracting the pointer, then checks for null before constructing the adapter. Invalid arguments, including an omitted argument, raise a Lua error containing `InputDialType requires a non-null InputState userdata`.

The adapter retains a borrowed pointer. Callers must keep the input state and its owner alive throughout the adapter's lifetime; this boundary check neither extends ownership nor detects stale, correctly typed userdata. Argument rejection is covered by isolated native child processes in `tests.dial-type-invalid-argument`, with parent assertions in `tests.test-dial-type`; the valid path still uses the real Engine input and explicit gamepad updates.

## Dev notes

- [Composable States](/dev/notes/composable-states) — composable state architecture over inheritance
- [Directional Focus Traversal](/dev/notes/directional-focus-traversal) — focus movement between widgets
- [Focus Change Ordering](/dev/notes/focus-change-ordering) — focus event ordering
- [Sdl3 Input Migration](/dev/notes/sdl3-input-migration) — SDL2 to SDL3 migration
- [Selection](/dev/notes/selection) — selection model

## See also

- [Core Platform](/dev/features/core-platform)
- [Composable States](/dev/adrs/adr-composable-states)
- [Subsystems](/dev/subsystems/)
