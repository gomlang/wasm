# Official Core 1.0 binary fixtures

Source: [WebAssembly/spec test/core at f750d21d](https://github.com/WebAssembly/spec/tree/f750d21dcc4903280b4db80ca81795968c5557f4/test/core).
The original tests are Apache-2.0 licensed; see [LICENSE](LICENSE).

`manifest.json` records the exact source-file and generated-file hashes, tool
version, generation flags, command counts and all omitted WAT syntax assertions.
Each script JSON embeds its Wasm binaries as base64; no downloaded files are
needed when tests run.

- 74 source scripts; 18,902 executable binary commands.
- 492 WAT syntax assertions omitted because this library accepts binary input.
- The `table`, `token` and `utf8-invalid-encoding` scripts contain zero binary
  commands. All binary commands in the pinned source corpus are retained.
- WABT 1.0.42 `wast2json` performs WAST-to-binary conversion. Expected values and
  errors originate in the official assertions, not in this interpreter.

## Pinned inputs

| Input | SHA-256 |
| --- | --- |
| [Spec source archive](https://codeload.github.com/WebAssembly/spec/tar.gz/f750d21dcc4903280b4db80ca81795968c5557f4) | `303372fc8002304495053646732373c38982e4b4b4af6ec16d7cab7556aa3425` |
| [WABT 1.0.42 Linux x64 archive](https://github.com/WebAssembly/wabt/releases/download/1.0.42/wabt-1.0.42-linux-x64.tar.gz) | `84895407a6bbb80e918f33b16b2fb2206021c150b6bc9ff6f761263a745ab131` |

After verifying and extracting those archives, run from the repository root:

```sh
python3 tools/conformance.py generate \
  --spec-root /path/to/spec-f750d21dcc4903280b4db80ca81795968c5557f4 \
  --wast2json /path/to/wabt-1.0.42/bin/wast2json
goml fmt
python3 tools/conformance.py check
goml test --example conformance --timeout 300s
goml verify --example conformance --timeout 300s
```

Generation first authenticates all 74 source files and the upstream license
against the retained pinned manifest. It rejects source changes before writing
any output. Regenerated scripts and exclusions must reproduce the retained
baseline before any fixtures are replaced. `check` enforces the exact unique
script set, provenance checksums and fixed 18,902/492 counts.

`python3 tools/conformance.py run` is an optional command-line runner that builds
the same example and reports each script independently. The usual GoML example
tests and isolated verification already run the corpus.

## Current runtime semantics

These Core1 source fixtures remain byte-for-byte intact. The runner uses the
fixed [`../core2_migrations.json`](../core2_migrations.json) for 45 assertions whose
expected behavior changed under Core2: 32 active-segment bounds traps, 8 newly
valid modules, 1 reserved-byte-to-table-index validation change, and 4 results
observing effects of segments completed before an initialization trap. Each
replacement includes and checks the complete original command. The migration
manifest has a pinned SHA-256 enforced by `tools/conformance.py check`.
