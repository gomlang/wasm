# Embedded Wasm example

Run `goml run --example basic` from the repository root to instantiate a binary
module and call its exported addition function. It prints `42`.

The example shares the root manifest. Its tests run both through `goml test`
and as an independent consumer through `goml verify --timeout 300s`.
