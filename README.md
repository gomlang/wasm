# `ecosystem::wasm`

A WebAssembly Core 1.0 interpreter written in GoML. Decode and validate a binary
module, bind explicitly supplied imports, instantiate it in a store, and call
its exported functions. The implementation uses an explicit instruction loop and
call frames. Runtime execution depends only on the GoML standard library.

Requires GoML 0.1.57 or newer. Module coordinate: `ecosystem::wasm`.

## Example

```goml
use ecosystem::wasm;

fn run(bytes: Slice[u8]) -> Result[Vec[wasm::Value], wasm::Error] {
    let module = wasm::Module::new(bytes)?;
    let store = wasm::Store::new();
    let instance = store.instantiate(module, wasm::Linker::new())?;
    store.call(instance, "add", Vec::from_array([
        wasm::Value::I32(20), wasm::Value::I32(22),
    ]))
}
```

`examples/basic` contains a complete, executable addition module and independent
consumer tests. `goml run --example basic` prints `42`.

## Compatibility

The compatibility baseline is
[WebAssembly Core 1.0](https://www.w3.org/TR/wasm-core-1/), with the official
`w3c-1.0` test sources pinned at
[`f750d21dcc4903280b4db80ca81795968c5557f4`](https://github.com/WebAssembly/spec/tree/f750d21dcc4903280b4db80ca81795968c5557f4).

| Capability | Implemented scope |
| --- | --- |
| Binary decoding | Version 1 header, all Core 1.0 sections, custom-section names, bounded signed/unsigned LEB128 including permitted padded encodings |
| Validation | Operand/control stacks, unreachable polymorphism, instruction types, indexes, limits, const expressions, imports, exports and start signature |
| Values | `i32`, `i64`, `f32`, `f64`; all 123 numeric instructions, wrapping integers, explicit traps, bit-preserving reinterpretation |
| Control | Blocks, loops, conditional branches, branch tables, returns, direct/indirect calls and recursion |
| State | Locals, mutable/immutable globals, one linear memory and one function table per module, active data/element segments |
| Embedding | All four import/export kinds, host functions, cross-instance calls and shared imported state in the same store |
| Initialization | Import matching, segment preflight, initialization, start function execution |

Post-Core-1.0 instructions and module features are rejected. Text-format parsing,
WASI, components, SIMD, threads, reference-type extensions, bulk memory, multi-value
and GC are future work. Producers must target this baseline; current compiler
output may enable newer features by default. WAT/WAST tooling is used to generate
test fixtures and is not a runtime dependency.

## API and ownership

- `Module::new(bytes)` and `Module::with_limits(bytes, limits)` decode and fully
  validate before producing a module. A module owns its decoded data and can be
  reused across instances and stores. `Module::exports()` returns a fresh list.
- `Store::new()` uses standard limits; `Store::with_limits(limits)` selects them.
  A store owns instantiated functions and state for its lifetime.
- `Linker::define(module, name, external)` binds an import; duplicate bindings
  return a link error. `Store::instantiate(module, linker)` checks all import
  types and store identities before initialization.
- `Store::call(instance, export, arguments)` invokes an exported function.
  `Store::invoke(function, arguments)` also supports a `Func` handle.
- `Store::export(instance, name)` returns `Extern::Func`, `Memory`, `Table` or
  `Global`. Handles retain shared state and require their originating store.
- `Store::host_func(signature, callback)` copies its signature. The callback takes
  `(Caller, Vec[Value])`, returns `Result[Vec[Value], Error]`, and may access the
  calling instance's exports using `Caller::export`. Return types are checked.
  Argument vectors are copied for callbacks; returned values are collected into
  an independent vector.
- `Store::memory`, `table` and `global` create objects for host-defined imports.
  Memory reads return copies; writes check the complete range before mutation.
  `Func::function_type()` returns a copied signature. Table operations check
  indexes and function ownership; global writes enforce mutability and type.

Stores and their mutable handles are intended for one executing host thread at a
time. Shared handles alias state; independent stores can execute separately.
Recursive host reentry into an executing store returns `Error::Argument`.
Callbacks may access memory, tables and globals, but must enforce their own I/O
and time limits. The interpreter's fuel cannot interrupt a blocking host callback.
Host callback errors propagate; a panic raised by host code remains a host panic.

## Errors and initialization

`Error` distinguishes `Decode(byte_offset, message)`,
`Validation(function_index, byte_offset, message)`, `Link(message)`, `Trap(kind)`,
`Limit(message)` and invalid embedding `Argument(message)`. Module-level
validation uses function index `-1`. Trap variants identify unreachable code,
integer arithmetic/conversion errors, memory/table bounds, indirect-call failures,
exhausted fuel/stack, and host failures.

Every active segment is bounds-checked before any imported memory/table is
changed. Out-of-bounds segments are link failures. A start function runs after
initialization; a start trap retains state changes already performed, including
changes to imported objects. Allocated objects remain in the store after a start
trap because initialized tables can retain references to their functions. Calls
likewise preserve effects preceding a trap. There is no transactional rollback.

## Resource limits

`Limits::standard()` supplies:

| Limit | Default |
| --- | ---: |
| Module bytes | 16 MiB |
| Decoded structural items | 100,000 |
| Locals including parameters per function | 100,000 |
| Instructions across function bodies and initializers | 1,000,000 |
| Validation operand/control stack limit | 100,000 |
| Runtime value, local and label slots combined | 100,000 |
| Active Wasm call frames | 1,024 |
| Linear memory pages across a store | 256 (16 MiB) |
| Table elements across a store | 100,000 |
| Store objects across instances | 100,000 |
| Initial fuel | 10,000,000 |

`Module::with_limits` controls decoding and validation; store limits govern
allocation and execution. Structural counting includes section-vector entries,
function type entries, branch labels and expanded locals. Store objects include
instances, functions, memories, tables, globals, imported bindings and copied host-signature entries. Input limits apply to the
already supplied byte slice; callers reading untrusted files should bound reads.

Fuel is shared across calls and initialization. Each executed instruction costs one unit; invocation costs one plus its parameter
count and defined local count, charged before argument/local allocation. Initialization
additionally charges global count,
allocated memory pages/table elements, and copied segment bytes/elements.
Successful memory growth charges the requested page count. A growth rejected by
a declared/store maximum returns `-1` without a page-allocation charge.
`Store::fuel()` inspects the remainder; `set_fuel()` resets it when idle. Fuel
exhaustion sets the remainder to zero and traps. Runtime limits may reject valid
modules or interrupt their execution; they do not extend the compatibility scope.

## Development

```sh
goml fmt --check
goml test
goml verify --timeout 300s
goml run --example basic
```

The conformance example runs all 74 pinned official scripts offline: 18,902
binary commands, including cross-module registration and linking. The 492
WAT-syntax-only assertions are individually listed as outside the binary API.
An additional 160 retained outcomes were produced by executing an independent
WABT 1.0.42 interpreter (152 exact results and eight traps). Its provenance, regeneration instructions,
coverage and exclusions are recorded beside those fixtures. Binary parser,
validator, numeric edge and runtime regression tests supplement the official
suite. GitHub Actions uses the ecosystem's pinned verification toolchain and
independent registry checks.
