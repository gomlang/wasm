# Embedded Wasm example

Run `goml run --example basic` from the repository root to instantiate a binary
module and call its exported addition function. It prints `42`.

The example shares the root manifest. Its tests run through `goml test`
and the shared ecosystem verifier, `(cd ../workflows && just ecosystem-test wasm)`,
from the library root.
