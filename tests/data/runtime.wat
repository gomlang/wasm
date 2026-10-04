(module
  (type $unary (func (param i32) (result i32)))
  (memory (export "memory") 1 2)
  (global $counter (export "counter") (mut i32) (i32.const 0))
  (table (export "table") 3 funcref)
  (data (i32.const 8) "wasm")
  (func $double (type $unary) local.get 0 i32.const 2 i32.mul)
  (elem (i32.const 0) $double)
  (func (export "add") (param i32 i32) (result i32) local.get 0 local.get 1 i32.add)
  (func $fac (export "fac") (param i32) (result i32)
    local.get 0 i32.eqz
    if (result i32) i32.const 1
    else local.get 0 local.get 0 i32.const 1 i32.sub call $fac i32.mul end)
  (func (export "sum") (param i32) (result i32) (local i32)
    block $exit loop $next
      local.get 0 i32.eqz br_if $exit
      local.get 1 local.get 0 i32.add local.set 1
      local.get 0 i32.const 1 i32.sub local.set 0 br $next
    end end local.get 1)
  (func (export "dispatch") (param i32 i32) (result i32)
    local.get 0 local.get 1 call_indirect (type $unary))
  (func (export "load8") (param i32) (result i32) local.get 0 i32.load8_s)
  (func (export "load") (param i32) (result i64) local.get 0 i64.load)
  (func (export "store") (param i32 i64) local.get 0 local.get 1 i64.store)
  (func (export "grow") (param i32) (result i32) local.get 0 memory.grow)
  (func (export "bump") (result i32) global.get $counter i32.const 1 i32.add global.set $counter global.get $counter)
  (func (export "infinite") loop br 0 end)
  (func $recurse (export "recurse") call $recurse)
  (func (export "choose") (param i32) (result i32)
    block $out (result i32)
      i32.const 42 local.get 0 br_if $out drop i32.const 7
    end)
  (func (export "brtable") (param i32) (result i32)
    block $outer (result i32) block $inner (result i32)
      i32.const 10 local.get 0 br_table $inner $outer
    end i32.const 1 i32.add end)
)
