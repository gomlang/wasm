# Binary conformance and independent reference tests

This example exercises `ecosystem::wasm` through its public embedding API.
The checked-in fixtures run offline with the GoML standard library. WABT is
needed only to regenerate them.

From the repository root:

```sh
goml test --example conformance --timeout 300s
goml verify --example conformance --timeout 300s
python3 tools/conformance.py check
python3 tools/differential.py check
```

`goml verify` also includes this example and copies its fixtures into the
independent consumer checkout. There are 74 official script tests plus one
independent reference test.

## Official Core 1.0 corpus

[WebAssembly/spec](https://github.com/WebAssembly/spec/tree/f750d21dcc4903280b4db80ca81795968c5557f4/test/core)
is pinned to `f750d21dcc4903280b4db80ca81795968c5557f4`, the `w3c-1.0`
baseline. The 74 source scripts contain **18,902 binary commands** tested here.
They include malformed and invalid modules, linking and initialization failures,
traps, exhaustion, module registration, imported state, and exact scalar results.
Float assertions distinguish canonical NaNs, arithmetic NaNs and exact bit
patterns, including signed zero.

The binary library has no WAT parser. Exactly **492 WAT syntax assertions** are
outside its input API and individually listed in
[`tests/data/spec/manifest.json`](tests/data/spec/manifest.json). Three scripts
(`table`, `token`, `utf8-invalid-encoding`) contain only those assertions and thus
have zero binary commands. No binary assertions are excluded. The source
fixtures retain their upstream Apache-2.0 license.

See [fixture provenance and regeneration](tests/data/spec/README.md).

## Independent reference corpus

`tools/differential.py` creates deterministic programs from the fixed
`0x5741534d5f4d5650` seed, compiles them with WABT `wat2wasm`, and obtains every
expected outcome by executing WABT `wasm-interp` **1.0.42**. It produces
**160 reference outcomes**:

| Category | Outcomes |
| --- | ---: |
| Integer arithmetic, bit operations and shifts | 96 |
| Unaligned memory access and signed/unsigned loads | 24 |
| Loops, branches, branch tables, recursion and indirect calls | 20 |
| Float bit operations, signed zero and nearest rounding | 12 |
| Arithmetic, bounds and unreachable traps | 8 |

Float results are reinterpreted as integers before observation, preserving every
bit. The generator parses oracle output rather than calculating expected results
itself. `tests/data/reference` retains the generated WAT, unmodified oracle
stdout, runnable JSON and a manifest with tool and artifact SHA-256 checksums.
These programs were authored for this library and use its repository license.

Regenerate using the pinned Linux x64 WABT binaries:

```sh
python3 tools/differential.py generate --wabt-bin /path/to/wabt-1.0.42/bin
python3 tools/differential.py check
goml test --example conformance independent_wabt_reference
```

The generator verifies the version and SHA-256 of both WABT executables before
running them. Normal tests read the retained outcomes without invoking WABT.
