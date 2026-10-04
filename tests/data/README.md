# Runtime regression fixtures

The adjacent WAT sources are authored for this project. Generate their binary
counterparts with WABT 1.0.42:

```sh
for input in tests/data/*.wat; do
  wat2wasm "$input" -o "${input%.wat}.wasm"
done
```

Tests consume committed binaries; WABT is not needed to run them. The fixtures
exercise control flow, memory, initialization, host imports, cross-instance
function calls, and initialization/execution failures. `extensions.wat` also
exercises Core 2 block parameters, references, multiple tables, passive segments,
bulk operations and nested trap frames.
