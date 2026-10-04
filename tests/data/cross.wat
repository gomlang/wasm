(module
 (import "other" "add" (func $add (param i32 i32) (result i32)))
 (func (export "run") (param i32) (result i32) local.get 0 i32.const 5 call $add)
)
