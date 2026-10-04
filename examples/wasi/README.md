# WASI Preview1 with real C compiler output

This example runs two checked-in WebAssembly modules compiled from the project's
own C sources with **wasi-sdk 24.0**, using Clang **18.1.2-wasi-sdk** and real
wasi-libc. The GoML interpreter executes them through its public API.
Normal tests need no SDK, external WebAssembly engine, network, or guest access
to the host filesystem.

From the repository root:

```sh
goml test --example wasi
goml verify --example wasi
python3 tools/wasi_fixtures.py check
```

The command example supplies arguments, environment variables, standard input,
an in-memory `/sandbox` preopen, and deterministic clock/random callbacks using
`WasiConfig`. `Wasi::link` supplies the imports; `Wasi::run` invokes `_start` and
returns the exit code. Output is available through `stdout()` and `stderr()`;
created files remain available through the configured `WasiFs` handle.

## Seven public API tests

- A C command uses `printf`, UTF-8 arguments/environment, `read` on stdin, and
  POSIX `open`, `write`, `lseek`, `read`, `fstat`, and `close` under its preopen.
  Clock/random results, file contents, stdout, stderr, exit zero, and output
  snapshot isolation are checked exactly.
- A second command path flushes stderr and exits with code 23.
- A C reactor probes ten malformed guest pointers, including invalid output
  pointers and a later invalid iovec, plus four misaligned typed pointers.
  Calls must trap before consuming input,
  producing output, modifying the guest buffer, or calling clock/random hooks.
- Missing system callbacks, absent preopens, and writing stdin are rejected.
  An unavailable clock returns `INVAL` (28); unavailable randomness returns
  `NOTSUP` (58).
- Parent-path escape, file write without rights, and an invalid `path_open`
  result pointer are rejected without creating or changing files.
- `proc_exit(37)` through the direct call API produces `Error::Exit(37)`.
- An independently generated module imports all **46** Preview1 functions with
  their exact WITX signatures. Instantiation verifies every parameter/result
  type, including mixed `i32`/`i64` signatures, socket imports, and the absence
  of a result on `proc_exit`.

The reactor is compiled with `-mexec-model=reactor` and initialized by calling
`_initialize`. The command uses wasi-libc's normal `_start` entry point.

## Provenance and rebuilding

[`tests/data/manifest.json`](tests/data/manifest.json) records the archive URL,
compiler/version/source commits, exact flags, C sources, WebAssembly outputs,
and all notice SHA-256 hashes. The SDK archive is:

```text
https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-24/wasi-sdk-24.0-x86_64-linux.tar.gz
SHA-256 c6c38aab56e5de88adf6c1ebc9c3ae8da72f88ec2b656fb024eda8d4167a0bc5
```

The compiler uses `wasm32-wasip1`, `-O1`, `-fno-builtin`, disabled SIMD/relaxed
SIMD, stripped metadata, a 64 KiB stack, and a 16 MiB maximum linear memory.
These programs target the library's supported Core2 scalar instruction set.

```sh
python3 tools/wasi_fixtures.py generate --sdk-archive /path/to/wasi-sdk-24.0-x86_64-linux.tar.gz
python3 tools/wasi_fixtures.py check
goml test --example wasi
```

Generation authenticates the retained source/provenance and SDK archive, then
extracts and builds in a temporary directory. Both outputs must match their
reviewed hashes before either retained binary is replaced. `check` independently
pins the complete manifest and file set, so editing a fixture and its manifest
together cannot silently change the expected corpus.

The project-authored C programs use this repository's MIT license. The compiled
modules also contain wasi-libc and compiler runtime code; their upstream
Apache/LLVM, MIT, BSD and public-domain notices are retained under
[`tests/data/licenses`](tests/data/licenses), with pinned origins in the
manifest.

## Independent ABI source

The signature fixture is derived from the official
[WebAssembly/WASI source](https://github.com/WebAssembly/WASI/tree/41c4383548ba7a06df5df7232b68a6f0bbb93e2d/legacy/preview1/witx),
pinned to commit `41c4383548ba7a06df5df7232b68a6f0bbb93e2d`.
`tests/data/abi` retains both WITX inputs, their ABI documentation, license,
and the generated signatures. The specification files retain their upstream
W3C Community Contributor License terms.

The generator resolves WITX type aliases and enum/flag representations, lowers
strings/lists to pointer-length pairs, and adds output pointers for `expected`
success values. It emits the import module directly; it never reads the
interpreter's signature table to obtain expected types. Every WITX function is
included, including `sock_accept`, for a total of 46. The documentation also
specifies pointer traps: out-of-bounds dereferences produce
`Trap::MemoryOutOfBounds`; misaligned typed pointers produce
`Trap::MisalignedPointer`.
