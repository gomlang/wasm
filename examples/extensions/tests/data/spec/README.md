# Pinned Core2 fixtures

Upstream [WebAssembly/spec test/core](https://github.com/WebAssembly/spec/tree/fffc6e12fa454e475455a7b58d3b5dc343980c10/test/core)
at commit `fffc6e12fa454e475455a7b58d3b5dc343980c10` (`wg-2.0`).
The upstream tests retain their Apache-2.0 [LICENSE](LICENSE).

| Authenticated input | SHA-256 |
| --- | --- |
| [Source archive](https://codeload.github.com/WebAssembly/spec/tar.gz/fffc6e12fa454e475455a7b58d3b5dc343980c10) | `597e3ea796ac08bb5f041513afa9f538b1e7f7619d865225ac482983a7af35cf` |
| [WABT 1.0.42 Linux x64 archive](https://github.com/WebAssembly/wabt/releases/download/1.0.42/wabt-1.0.42-linux-x64.tar.gz) | `84895407a6bbb80e918f33b16b2fb2206021c150b6bc9ff6f761263a745ab131` |
| `wast2json` executable from that archive | `2785953b9de5bf26d62cdfa7563607ed83a560097ec0d4ad1d69e5b8b2ecda86` |

`manifest.json` lists all 90 scripts, 27,437 executed binary commands, 581 omitted
WAT syntax assertions, 58 excluded SIMD scripts, and two bounded encoding
corrections. Its own hash is pinned in `tools/extensions.py`, so changing a
fixture together with its manifest entry does not pass provenance checking.
Each source and generated file also has its own SHA-256 entry.

The only encoding corrections add a zero data-count section to WABT's encoding
of text assertions at `memory_init.wast:190` and `:227`. Exact original and
corrected hashes are in `encoding_corrections`. All 719 binary malformed
assertions are retained without correction. There are no runtime-dependent
skips or relaxed error-category comparisons.

See [example instructions](../../../README.md) for offline test, isolated
verification and authenticated regeneration commands.
