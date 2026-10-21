# SSE callback finalizer identity repair

## Scope and success criteria

Repair the native HTTP/SSE binding shutdown abort reported by the user, preserving
the existing Lua stream-table API. This is a high-risk memory-corruption fix with
a narrowly bounded implementation. Do not read sensitive cores, user collections,
or credentials. The prior report's read-only scope describes that investigation;
the current request authorizes fixing the issue.

Success means the three Lua-bound SSE callables have distinct GC identities,
SSE send/close/on-close behavior remains compatible, and full Lua collections
after disconnect cannot corrupt the stream before server stop/destruction.

## Diagnostic evidence brief

The user reports two SIGABRT cores from the same executable, one during reload
cleanup and one ordinary shutdown. Both stop in HttpServer::stop/close_streams
while SSEStream::mark_closed locks a mutex whose owner is -1, kind 0, nusers 0.
The shared_ptr control block remains recognizable with strong=3, weak=2.
Reported glibc assertion: `mutex->__data.__owner == 0`.

The user's standalone native SSE reproducer disconnects, waits for close
processing, runs two full Lua collections, and stops the server. Without the
collections it succeeds; with them it aborts. A reported hardware watchpoint
caught owner 0 becoming -1 in shared_ptr::_M_release called by sol2's
user_alloc_destroy for the send lambda during Lua full GC. These are supplied
observations, not independently rerun in this workspace. External reproduction
artifact access was denied; this work does not require those artifacts.

Read-only source inspection confirms the relevant mechanism:

- src/lua_http_server.cpp:606-639 installs send and close with a shared_ptr
  capture, then on-close with HttpServer* plus shared_ptr captures.
- external/sol2/sol/sol.hpp:9113-9149 derives names from compiler type strings;
  :9277-9279 derives GC metatable names from those names.
- sol.hpp:15603-15624 installs a type-specific destructor only when creating
  the string-named metatable; :11523-11530 destroys the compile-time type.
- sol.hpp:20151-20173 stores the callable wrapper in a userdata upvalue.

Hypothesis: compiler-derived lambda names collide, reusing the send finalizer
for the differently laid-out on-close closure. That finalizer interprets the
stream pointer as a shared_ptr control-block pointer and decrements stream+8,
which is the mutex owner field in the investigated binary. No source finding
requires an already-freed HttpServer, book extraction, or MCP application data
to explain this writer. Actual runtime identity collision and regression RED
evidence must still be demonstrated locally before applying the native fix.

The ignored debug evidence artifact could not be written through the available
implementer capability. This spec contains the complete evidence brief instead;
the diagnostic advisor should review this path and the relevant source files.

## Alternatives and chosen architecture

1. **Chosen: distinct named callable types** for send, close, and on-close,
   local to lua_http_server.cpp. Their explicit names avoid ambiguous lambda
   type identities without changing vendored sol2 or the public API.
2. General sol2 type-unique finalizer identity: potentially broader protection,
   but changes every callable binding and needs a separate compatibility and
   portability design. Not part of this fix.
3. Alter shutdown ordering or suppress collections: rejected because the wrong
   finalizer has already corrupted live memory.

Keep each callable's existing captured state, argument scanning, return values,
error messages, and colon/dot call behavior. On-close must retain existing
registration and native enqueue semantics, including Lua-thread dispatch. Use
the smallest access arrangement required for the named on-close callable, with
its implementation after HttpServer is complete if necessary. Do not expose
new Lua methods or broaden native APIs for testing.

Do not redesign HttpServer ownership, raw server captures, or the independently
observed stream close-handler self-cycle. Those deserve separate evidence and
scope; they are not the confirmed corruption writer in the supplied report.

## Regression and error behavior

Extend assets/lua/tests/test-http-server.fnl, using loopback and ephemeral ports.
First demonstrate RED against the existing native binding. A direct comparison
of the native callable userdata GC metatables can fail deterministically before
corruption; avoid retaining callable userdata references across the GC phase.
Do not rely solely on debug internals: also exercise an actual connection,
send data, disconnect/close, observe exactly-once Lua on-close dispatch, release
stream-table/callback references, run two full collections while the server is
rooted, stop it, release it, and collect again. Cover collection before stopping
an open stream as well. Use bounded condition polling rather than a fixed
six-second sleep, and unconditional teardown so failed assertions do not strand
a listener. Preserve existing invalid-argument errors and send results.

Test failure must be explicit. Do not turn server errors into no-ops or disable
GC/stop/assertions. If local RED differs from the supplied diagnosis, return to
diagnosis rather than broadening the patch speculatively.

## Validation

Native fix prerequisite: `make build` with tool timeout 14400000 ms. For direct
tests use SKIP_KEYRING_TESTS=1, XDG_DATA_HOME=/tmp/space/tests/xdg-data,
SPACE_DISABLE_AUDIO=1, absolute SPACE_ASSETS_PATH, and FENNEL_PATH plus
FENNEL_MACRO_PATH pointing to assets/lua/?.fnl and assets/lua/?/init.fnl.

After rebuilding, run in order:

1. `./build/space -m tools.fennel-check:main -- --target files --file assets/lua/tests/test-http-server.fnl`
2. `make constraints`
3. Focused new regressions, then full `./build/space -m tests.test-http-server:main`
4. `./build/space -m tests.test-mcp-http:main`
5. `ctest --test-dir build -R '^space_fnl_tests_integration$' --output-on-failure`
6. Standard isolated `make test` for final native-binding lifecycle validation.

The integration target is required separately: make test excludes it. Record
RED/GREEN evidence, compiler/constraint results, and constraint impact. All code
and test changes require implementer followed by independent reviewer pass.
Before final validation/integration, fetch origin, evaluate current origin/main,
safe-merge if behind, then validate reviewed committed code from a clean tree.
