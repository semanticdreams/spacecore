# SSE Closure Finalizers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate wrong finalization of Lua SSE callbacks and prove safe GC before server shutdown.

**Architecture:** Replace the three capturing Lua-bound lambdas with distinct private named callable types in HttpServer. Preserve all API and ownership behavior. One coherent implementation unit contains a mandatory unchanged-native RED checkpoint and renewed diagnostic-advisor approval before native edits.

**Tech Stack:** C++, sol2, cpp-httplib, embedded Lua/Fennel, CMake/Make, CTest.

**Spec:** `docs/specs/2026-10-21-sse-closure-finalizers-design.md`

## Global Constraints

- Do not read sensitive cores, user collections, or credentials.
- Keep each callable's existing captured state, argument scanning, return values, error messages, and colon/dot call behavior.
- On-close must retain existing registration and native enqueue semantics, including Lua-thread dispatch.
- Do not expose new Lua methods or broaden native APIs for testing.
- Do not redesign HttpServer ownership, raw server captures, or the independently observed stream close-handler self-cycle.
- First demonstrate RED against the existing native binding.
- Use bounded condition polling rather than a fixed six-second sleep, and unconditional teardown so failed assertions do not strand a listener.
- If local RED differs from the supplied diagnosis, return to diagnosis rather than broadening the patch speculatively.
- Native fix prerequisite: `make build` with tool timeout 14400000 ms.
- All code and test changes require implementer followed by independent reviewer pass before committing.

## File structure

- Modify `src/lua_http_server.cpp`: named private callables, existing stream-table assignments only.
- Modify `assets/lua/tests/test-http-server.fnl`: identity, API compatibility, and real lifecycle regressions with test-local cleanup.
- Read `external/sol2/sol/sol.hpp`, `src/lua_http.cpp`, `src/lua_sysinfo.cpp`, `assets/lua/tests/runner.fnl`, `assets/lua/tests/test-mcp-http.fnl`, `Makefile`, and `CMakeLists.txt` for existing contracts.
- Do not modify sol2, MCP implementation, CMake, or unrelated architecture documentation.

## Validation environment

Use these exports for direct tests and suite commands; suppress core creation for intentional RED:

```bash
export SKIP_KEYRING_TESTS=1 XDG_DATA_HOME=/tmp/space/tests/xdg-data
export SPACE_DISABLE_AUDIO=1 SPACE_ASSETS_PATH="$PWD/assets"
export FENNEL_PATH="$PWD/assets/lua/?.fnl;$PWD/assets/lua/?/init.fnl"
export FENNEL_MACRO_PATH="$FENNEL_PATH"
ulimit -c 0
```

### Task 1: Prove and repair SSE finalizer identity

**Files:** the two modification paths above.

**Interfaces:** Existing `stream.send(...) -> bool`, `stream.close(...) -> no values`, `stream["on-close"](...) -> no values`, server route/listen/stop and `http.request`/`http.cancel`. Use `sysinfo.now-ms` for monotonic bounded waits and runner per-case teardown. Produce private `SseSend`, `SseClose`, and `SseOnClose` with `operator()(sol::variadic_args) const`; the first returns bool, others void.

- [ ] Record base SHA, branch, clean status, native source hashes and compiler configured in CMakeCache; run `make build` before editing tests or native code. Record binary hash and compiler version. Confirm `git diff HEAD -- src/lua_http_server.cpp external/sol2/sol/sol.hpp` is empty.
- [ ] Add a test-local fixture owning mutable server/stream/request fields, weak-value witnesses, received data/completion flags, and close count. Per-case teardown must attempt cancellation, stop, bounded completion draining and reference release even on assertion failure; aggregate errors instead of dropping them. Do not leave local strong aliases alive across collection. Existing CPU-clock waits may be converted narrowly to `sysinfo.now-ms` without swallowing predicate errors.
- [ ] Add `http-server: SSE finalizers distinct callable identities`. Establish real loopback SSE on port 0, observe delivered data, inspect callable userdata in `debug.getupvalue callable 2`, and obtain its metatable and `__gc`. Snapshot registry names and pairwise equality as primitives only, allowing inspector userdata references to leave scope. Print/flush diagnostics before asserting pairwise distinct metatables:

```fennel
(local (name userdata) (debug.getupvalue stream.send 2))
(assert (= (type userdata) "userdata"))
(local mt (debug.getmetatable userdata))
;; Repeat inside a scoped helper for close and on-close, recording
;; registry names and __gc equality without returning strong userdata roots.
(assert (not comparison.same-metatable)
        (.. "SSE callable finalizer identities must be distinct: " comparison.pair))
```

- [ ] Add separately filterable lifecycle cases under `http-server: SSE finalizers `: dot explicit-close, colon explicit-close, client-disconnect, and open-stream collection before stop. Deliver two recognizable payloads and assert successful send returns. Preserve scanning past table/boolean arguments, invalid send/on-close error strings, no-value returns, and send-after-close false. Close twice and prove Lua close count becomes exactly one only through polling. For disconnect assert active `http.cancel` succeeds, then observe completion and close dispatch. For open-stream GC do not cancel before stop or require stop-time Lua notification.

```fennel
(set state.stream nil)
(collectgarbage :collect)
(collectgarbage :collect)
(assert (= state.weak.stream nil))
(assert (= state.weak.send nil))
(assert (= state.weak.close nil))
(assert (= state.weak.on-close nil))
(assert (rawequal state.weak.server state.server))
(state.server:stop)
(set state.server nil)
(collectgarbage :collect)
(collectgarbage :collect)
(assert (= state.weak.server nil))
```

- [ ] Run touched-file compile, then `make constraints`, then identity RED against unchanged native source:

```bash
./build/space -m tools.fennel-check:main -- --target files --file assets/lua/tests/test-http-server.fnl
make constraints
TEST_VERBOSE=1 TEST_FILTER='http-server: SSE finalizers distinct callable identities' ./build/space -m tests.test-http-server:main
```

Expected RED is the explicit identity assertion plus matching runtime metatables, not just a timeout or crash. Run each lifecycle case in a separate bounded process if safe, recording output and native aborts. Verify native source hashes/diff unchanged. Report compiler, exact commands/status, metatable registry names and __gc equality, root audit, and lifecycle results. **Return PAUSED_FOR_ADVISOR; no native edits or commits.**

- [ ] Supervisor sends this evidence and spec to debug-advisor. Resume same implementer only on `confirmed`; on missing evidence gather requested information, on wrong cause return to diagnosis. Inline reports are acceptable when ignored-artifact writes are unavailable.
- [ ] After confirmation, define private named functors storing the same state. Implement send and close with original bodies. Define on-close after HttpServer is complete if needed. Its inner native enqueue lambda must capture stored server/stream by value, never the callable object's `this`:

```cpp
struct SseSend { std::shared_ptr<SSEStream> stream; bool operator()(sol::variadic_args args) const; };
struct SseClose { std::shared_ptr<SSEStream> stream; void operator()(sol::variadic_args args) const; };
struct SseOnClose { HttpServer* server; std::shared_ptr<SSEStream> stream; void operator()(sol::variadic_args args) const; };
// In make_request_table:
stream_tbl["send"] = SseSend{stream};
stream_tbl["close"] = SseClose{stream};
stream_tbl["on-close"] = SseOnClose{this, stream};
// Within on-close, preserve registration then set_close_handler:
// [server = server, stream = stream](uint64_t id) { ...enqueue_sse_close(id, stream)... }
```

- [ ] Rebuild with `make build` timeout 14400000. Repeat touched-file compile and constraints, identity GREEN, all finalizer cases, whole HTTP module, whole MCP HTTP module, then separate integration CTest:

```bash
TEST_VERBOSE=1 TEST_FILTER='http-server: SSE finalizers ' ./build/space -m tests.test-http-server:main
TEST_VERBOSE=1 ./build/space -m tests.test-http-server:main
TEST_VERBOSE=1 ./build/space -m tests.test-mcp-http:main
xvfb-run -a ctest --test-dir build -R '^space_fnl_tests_integration$' --output-on-failure
```

- [ ] Report complete RED/GREEN and constraint-impact evidence. Dispatch independent FULL reviewer with spec, plan, working-tree diff and reports. Resolve material findings through implementer and independent re-review, adjudicating at breaker cap. Reviewer must inspect GC roots, actual lifecycle execution, cleanup and API compatibility. Do not treat equal folded destructor pointers as a failure if metatable identities remain distinct.
- [ ] After review pass, commit only reviewed source/tests with `fix(lua): give SSE callables distinct finalizer identities` and validation summary. Obtain required final whole-branch review for this high-risk change.

### Task 2: Current-base validation and integration

**Files:** no planned edits. Any discovered repository fixes require diagnosis and reviewed implementation.

- [ ] Invoke finishing skill. Through git-integrator fetch origin and evaluate current branch against origin/main; safe-merge if behind, never rebase/force-push. If local main, use guarded wrap-up branch creation. Conflicts go through implementer/reviewer.
- [ ] From reviewed committed clean tree run separate integration CTest again and standard isolated `make test` (timeout 14400000). If native/base changed rebuild and repeat focused ladder first. `make test` excludes integration, so neither gate replaces the other.
- [ ] Any required failure invokes systematic-debugging; capture command, cases, output, branch and porcelain status. Diagnose even apparently unrelated failures and obtain advisor/review for fixes; do not bypass.
- [ ] Verify clean tree, push feature branch through git-integrator, create main-targeting PR through github-operator and enable guarded merge queue policy. Poll until mergedAt exists; diagnose actionable CI/queue failures. Do not safe-merge just because main advances after queue entry.
