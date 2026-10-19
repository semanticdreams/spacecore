# Native SHA-256

`require("sha256").hash(string)` returns exactly 64 lowercase hexadecimal
characters. The module is always preloaded by the base runtime, independent of
wallet support. It rejects absent, nil and all non-string inputs without Lua
string coercion. Counted Lua string bytes (including NUL and bytes 0–255) go to
the existing `sha256_Data(const uint8_t*, size_t, char[65])` API. No subprocess,
external executable, download or alternate hashing implementation is used.

The canonical Fennel `repo/sha256.hash(content)` and `hash-file(path)` APIs
retain strict string assertions. `hash-file` uses binary `fs.read-file`; open
and read errors propagate rather than producing a digest of partial input.

## Provider and provenance

`cmake/sha256.cmake` defines `space_sha256_backend` after optional wallet setup.
If the real `TrezorCrypto` target exists, an interface target links only that
provider. Otherwise a static library compiles exactly the already-vendored
`external/wallet-core/trezor-crypto/crypto/sha2.c` and `crypto/memzero.c`, using
`include/TrezorCrypto` headers. It does not enable the optional wallet product;
the Windows wallet-off policy is unchanged. Neither branch compiles a second
implementation or suppresses duplicate symbols.

CMake `TestBigEndian` supplies target-private numeric `LITTLE_ENDIAN=1234`,
`BIG_ENDIAN=4321` and detected `BYTE_ORDER` definitions to the selected provider.
This avoids relying on the vendor header's little-endian default. The only
vendor source patch changes `<Windows.h>` to `<windows.h>` in `memzero.c` for
case-sensitive MinGW include lookup; the algorithm and zeroing logic are intact.

`memzero.c` attributes its adaptation to libsodium's implementation:
<https://github.com/jedisct1/libsodium/blob/1647f0d53ae0e370378a9195477e3df0a792408f/src/libsodium/sodium/utils.c#L102-L130>.
That attribution remains in the vendored source. The bundled crypto MIT notice
and the SHA source/header BSD notice are reproduced in full below.

The page installs to `share/doc/space/native-sha256.md`. The private Windows
native package also includes the canonical page at `docs/dev/notes/native-sha256.md`
before sealing; admission verifies canonical bytes in both native and overlay
payloads using the existing required-resource lifecycle and recursive inventories.

## SHA source and header notice

From `crypto/sha2.c` and `include/TrezorCrypto/sha2.h` (identical notices):

```text
/**
 * Copyright (c) 2000-2001 Aaron D. Gifford
 * Copyright (c) 2013-2014 Pavol Rusnak
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 * 3. Neither the name of the copyright holder nor the names of contributors
 *    may be used to endorse or promote products derived from this software
 *    without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTOR(S) ``AS IS'' AND
 * ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTOR(S) BE LIABLE
 * FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
 * OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
 * HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
 * LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
 * OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
 * SUCH DAMAGE.
 */
```

## Bundled crypto license

From `external/wallet-core/trezor-crypto/crypto/LICENSE`:

```text
The MIT License (MIT)

Copyright (c) 2013 Tomas Dzetkulic
Copyright (c) 2013 Pavol Rusnak

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Focused validation

The native binding CTest checks the five published vectors (empty, `abc`, one
NUL, the standard multi-block message and bytes 0–255), strict type rejection
and real `memzero` linkage. Configure/build/CTest `tests/cmake/sha256-backend`
with `SPACE_SHA256_TEST_WALLET_TARGET=OFF` and `ON` to exercise exclusive real
providers without building the whole optional wallet. Fennel tests cover file
equivalence, filesystem errors and an exception-safe throwing `Process.run`
seam proving no subprocess is used; downstream External Unit MCP tests exercise
hashes, stale-hash rejection and JSON responses through the unchanged APIs.
