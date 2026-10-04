(module
 (import "env" "double" (func $double (param i32) (result i32)))
 (import "env" "memory" (memory 1 2))
 (import "env" "counter" (global $counter (mut i32)))
 (export "memory" (memory 0))
 (func $start i32.const 17 global.set $counter)
 (start $start)
 (func (export "run") (param i32) (result i32) local.get 0 call $double)
)
