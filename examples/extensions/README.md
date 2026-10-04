# Core2 scalar, reference and bulk operation conformance

This example tests `ecosystem::wasm` through its public API against the official
[Core2 `wg-2.0` source](https://github.com/WebAssembly/spec/tree/fffc6e12fa454e475455a7b58d3b5dc343980c10/test/core),
pinned to `fffc6e12fa454e475455a7b58d3b5dc343980c10`.

The suite retains **90 top-level scripts and 27,437 binary commands**. It covers
sign extension, saturating float-to-integer conversion, multiple results and
block parameters, reference values, typed select, multiple tables, passive and
declarative segments, bulk memory/table operations, and the existing scalar
instruction set. Registered modules share imports through one store; external
reference tokens are cached and compared by reference identity.

The 58 scripts in the upstream `simd` directory are outside this release's
feature set. Exactly 581 WAT syntax assertions are also outside the binary input
API. Every excluded script and omitted assertion is listed with its source in
[`tests/data/spec/manifest.json`](tests/data/spec/manifest.json). The two
text-only scripts (`obsolete-keywords` and `utf8-invalid-encoding`) have no binary
commands. The library does not claim complete
Core2 support including SIMD.

## Run offline

From the repository root:

```sh
python3 tools/extensions.py check
goml test --example extensions --timeout 300s
goml verify --example extensions --timeout 300s
```

The normal `goml test` and `goml verify` workflows include this example. Tests
read retained JSON containing embedded Wasm bytes; they do not invoke WABT or
another Wasm runtime. `tools/extensions.py sync` copies the maintained conformance
runner into this example so it remains an independent consumer when verification
copies it into a fresh module. `check` detects divergence between runner copies.

## Regenerate

Verify and extract WABT 1.0.42 Linux x64, then run:

```sh
python3 tools/extensions.py generate \
  --spec-archive /path/to/spec2.tar.gz \
  --wast2json /path/to/wabt-1.0.42/bin/wast2json
goml fmt
python3 tools/extensions.py check
```

The tool authenticates the entire upstream archive and the `wast2json` executable
before generating anything. It also requires the complete regenerated manifest
to match its pinned hash before replacing retained files. Sources, exclusions,
omissions, conversion corrections, and fixture hashes are all covered by that
manifest. See [detailed fixture provenance](tests/data/spec/README.md).

## Two text-to-binary encoding corrections

For `memory_init.wast` lines 190 and 227, WABT `--no-check` omits the required
zero data-count section when converting an invalid text module that has no data
segments but uses `data.drop` or `memory.init`. The resulting binary would fail
**decoding**, preventing the intended official **validation** assertion.

The generator inserts exactly `0c 01 00` before the code section for those two
pinned inputs. Source location and complete input/output SHA-256 must match the
recorded correction. No original binary-malformed assertion is rewritten, and
the runner keeps decode, validation, linking and trap expectations distinct.

## Earlier specification fixtures

`examples/conformance` retains the original 18,902 Core1 commands separately.
Its fixed 45-entry migration manifest explicitly updates assertions whose
meaning changed under Core2. This new example uses the Core2 assertions directly
without applying those migrations. The earlier 160-outcome WABT differential
corpus remains part of the conformance example.
