(module
 (import "env" "counter" (global $counter (mut i32)))
 (func $start i32.const 99 global.set $counter unreachable)
 (start $start)
)
