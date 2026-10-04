# `ecosystem::wasm`

A WebAssembly interpreter written in GoML, supporting Core 1.0 numeric and control
operations plus Core 2 multi-value, reference types and bulk memory/table operations. Decode and validate a binary
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

The implemented scalar feature set follows
[WebAssembly Core 2.0](https://www.w3.org/TR/wasm-core-2/), excluding SIMD.
The official `wg-2.0` sources are pinned at
[`fffc6e12fa454e475455a7b58d3b5dc343980c10`](https://github.com/WebAssembly/spec/tree/fffc6e12fa454e475455a7b58d3b5dc343980c10).

| Capability | Implemented scope |
| --- | --- |
| Binary decoding | Version 1 header, sections including data count, all element/data segment encodings, custom-section names, bounded signed/unsigned LEB128 including signed 33-bit block types |
| Validation | Operand/control stacks, unreachable polymorphism, instruction types, indexes, limits, const expressions, declared function references, imports, exports and start signature |
| Numeric values | `i32`, `i64`, `f32`, `f64`; 123 original numeric instructions, five sign extensions and eight saturating float-to-integer conversions |
| References | Nullable `funcref` and `externref`, reference locals/globals, `ref.null`, `ref.is_null`, `ref.func` and typed select |
| Control | Multiple parameters/results in functions and blocks, loop parameters, branches, direct/indirect calls and recursion |
| State | One linear memory, multiple typed tables, mutable/immutable globals; active/passive data and active/passive/declarative elements |
| Bulk operations | Memory/table init, copy and fill; segment drop; table get/set, size and grow |
| Embedding | All four import/export kinds, multi-result host functions, cross-instance calls and shared state within a store, Wasm backtraces |

SIMD, threads, WASI, components, text-format parsing, memory64, multiple memories,
tail calls, exceptions, GC and JIT/AOT compilation remain future work. Unsupported
binary features are rejected. WAT/WAST tooling generates test fixtures and is not
a runtime dependency.

### Changes from the original Core 1.0 release

Core 2 allows module forms that Core 1 rejected, including multiple function
results and tables. Active segment bounds failures now return a memory/table
`Error::Trap`, and earlier successful segments retain their effects. Constant
expressions may read only imported immutable globals. The original Core 1 corpus
is retained unchanged; its explicit, checked migration list records assertions
whose expected outcome changes under Core 2. See
[conformance tests](examples/conformance/README.md) for details.

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

- `Store::typed_table(kind, minimum, maximum)` creates a `funcref` or `externref`
  table. `Table::element_type`, `get_value`, `set_value` and `grow(delta, value)`
  support both types. Existing `Store::table` and `Table::get`/`set` remain
  convenient function-table APIs. Growth returns `None` when a limit prevents it.
- `Store::extern_ref(data)` creates a reference with a distinct identity and an
  opaque `u64` host token; `ExternRef::data()` retrieves that token. Applications
  may use tokens to index their own host-object maps. Equal tokens do not make
  two references equal. Wasm cannot inspect the token. Reference arguments,
  callback results, globals and tables enforce store ownership.
- `Store::backtrace()` copies the most recent execution failure's active Wasm
  frames, innermost first. Each `TrapFrame` contains the store-local instance
  index (also available as `Instance::id()`), module function index (including
  imports), and module byte offset.
  Starting an invocation clears the previous trace. Host-only failures and
  failures before a Wasm frame is entered have no Wasm frames. Name sections and
  source/debug mappings are not yet exposed.

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

Each memory/table bulk operation checks its complete source and destination ranges
before mutation, including zero-length operations. Overlapping copies preserve
source values. Segment drop is idempotent; dropped segments behave as empty.
Segment state belongs to each instance, so dropping a segment leaves other
instances of the same module unaffected.

Instantiation initializes active element segments, drops declarative elements,
then initializes active data segments, in module order. An out-of-bounds segment
traps; effects of earlier successful segments remain. A start function runs after
initialization and similarly retains preceding effects on failure. Allocated
objects remain owned by the store after initialization/start traps because
imported tables can retain references to their functions. There is no rollback.

## Resource limits

`Limits::standard()` supplies:

| Limit | Default |
| --- | ---: |
| Module bytes | 16 MiB |
| Decoded structural items | 100,000 |
| Locals including parameters per function | 100,000 |
| Instructions across function bodies and initializers | 1,000,000 |
| Validation work across the module | 10,000,000 |
| Validation operand/control stack limit | 100,000 |
| Runtime value, local and label slots combined | 100,000 |
| Active Wasm call frames | 1,024 |
| Linear memory pages across a store | 256 (16 MiB) |
| Table elements across a store | 100,000 |
| Store objects across instances | 100,000 |
| Initial fuel | 10,000,000 |

`Module::with_limits` controls decoding and validation; store limits govern
allocation and execution. Structural counting includes section-vector entries,
function type entries, branch labels and expanded locals. `max_validation_work`
bounds cumulative type/operand/metadata checking, including multi-value and
branch-table comparisons. Store objects include
instances, functions, memories, tables, globals, imported bindings, host references,
segment records/element entries and copied host-signature entries. Input limits apply to the
already supplied byte slice; callers reading untrusted files should bound reads.

Fuel is shared across calls and initialization. Each executed instruction costs one unit; invocation costs one plus its parameter
count and defined local count, charged before argument/local allocation. Initialization
additionally charges global count,
allocated memory pages/table elements, and copied segment bytes/elements.
Successful memory growth charges the requested page count; table growth charges
the new element count. Bulk operations charge bytes/elements processed, and
branches/returns charge values that must be moved within the operand stack.
Host result collection charges one unit per returned value. A growth rejected by
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
The additional Core 2 example runs all 90 top-level official scripts: 27,437
binary commands, with 581 WAT syntax assertions and 58 SIMD scripts explicitly
outside scope. An additional 160 retained outcomes were produced by executing an independent
WABT 1.0.42 interpreter (152 exact results and eight traps). Its provenance, regeneration instructions,
coverage and exclusions are recorded beside those fixtures. Binary parser,
validator, numeric edge and runtime regression tests supplement the official
suite. GitHub Actions uses the ecosystem's pinned verification toolchain and
independent registry checks.
