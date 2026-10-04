#!/usr/bin/env python3
"""Retain a deterministic, independently executed WABT reference corpus.

The generator creates its own input programs, then asks wasm-interp for every
expected outcome. It does not compute expected interpreter outcomes in Python.
Normal tests consume the retained JSON; WABT is needed only for regeneration.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "examples/conformance/tests/data/reference"
WABT_VERSION = "1.0.42"
WABT_ARCHIVE_SHA256 = "84895407a6bbb80e918f33b16b2fb2206021c150b6bc9ff6f761263a745ab131"
TOOL_SHA256 = {
    "wat2wasm": "9e9ec8f737c890553951defcb1ee7f82de99fcafa32bef54990de27413794e7f",
    "wasm-interp": "d5d4e96e1dbdd4ec7a36d198726cd7673d213561a7e507159eeedc844e99245d",
}
SEED = 0x5741534D5F4D5650
EXPECTED_CATEGORIES = {"integer": 96, "memory": 24, "control": 20, "float_bits": 12, "trap": 8}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def programs() -> tuple[str, list[dict]]:
    state = SEED
    exports: list[dict] = []
    source = [
        "(module", "  (memory 1)",
        "  (type $unary (func (param i32) (result i32)))",
        "  (func $add17 (type $unary) (i32.add (local.get 0) (i32.const 17)))",
        "  (func $times3 (type $unary) (i32.mul (local.get 0) (i32.const 3)))",
        "  (table 2 funcref)", "  (elem (i32.const 0) $add17 $times3)",
        "  (func $factorial (param i32) (result i32)",
        "    (if (result i32) (i32.eqz (local.get 0)) (then (i32.const 1))",
        "      (else (i32.mul (local.get 0) (call $factorial (i32.sub (local.get 0) (i32.const 1)))))))",
    ]

    def random_word(width: int) -> int:
        nonlocal state
        state ^= state << 13 & 0xFFFFFFFFFFFFFFFF
        state ^= state >> 7
        state ^= state << 17 & 0xFFFFFFFFFFFFFFFF
        return state & ((1 << width) - 1)

    def export(category: str, kind: str, body: str) -> None:
        name = f"{category}_{len(exports):03d}"
        exports.append({"name": name, "category": category, "result": kind})
        source.append(f'  (func (export "{name}") (result {kind}) {body})')

    binary = "add sub mul div_s div_u rem_s rem_u and or xor shl shr_s shr_u rotl rotr".split()
    for width in (32, 64):
        kind = f"i{width}"
        for _ in range(3):
            for op in binary:
                left = random_word(width)
                right = random_word(width) or 1
                export("integer", kind, f"({kind}.{op} ({kind}.const 0x{left:x}) ({kind}.const 0x{right:x}))")
        for op in ("clz", "ctz", "popcnt"):
            export("integer", kind, f"({kind}.{op} ({kind}.const 0x{random_word(width):x}))")

    loads = [
        ("i32", "load8_s"), ("i32", "load8_u"), ("i32", "load16_s"), ("i32", "load16_u"), ("i32", "load"),
        ("i64", "load8_s"), ("i64", "load8_u"), ("i64", "load16_s"), ("i64", "load16_u"), ("i64", "load32_s"), ("i64", "load32_u"), ("i64", "load"),
    ]
    for repeat in range(2):
        for index, (kind, op) in enumerate(loads):
            address = 31 + repeat * 256 + index * 13
            bits = random_word(64)
            export("memory", kind, f"(i64.store offset=3 align=1 (i32.const {address}) (i64.const 0x{bits:x})) ({kind}.{op} offset=3 align=1 (i32.const {address}))")

    for limit in (0, 1, 17, 257):
        body = f"""(local $n i32) (local $sum i32)
    (local.set $n (i32.const {limit}))
    (block $done (loop $again
      (br_if $done (i32.eqz (local.get $n)))
      (local.set $sum (i32.add (local.get $sum) (local.get $n)))
      (local.set $n (i32.sub (local.get $n) (i32.const 1))) (br $again))) (local.get $sum)"""
        export("control", "i32", body)
    for value in (-2147483648, -1, 0, 2147483647):
        export("control", "i32", f"(block $exit (result i32) (br_if $exit (i32.const 71) (i32.lt_s (i32.const {value}) (i32.const 0))) (drop) (i32.const 99))")
    for index in range(4):
        export("control", "i32", f"(call_indirect (type $unary) (i32.const {random_word(32)}) (i32.const {index % 2}))")
    for index in (0, 1, 2, 255):
        export("control", "i32", f"(block $out (result i32) (block $second (block $first (br_table $first $second $second (i32.const {index}))) (br $out (i32.const 101))) (i32.const 202))")
    for argument in (0, 1, 6, 12):
        export("control", "i32", f"(call $factorial (i32.const {argument}))")

    for width in (32, 64):
        float_kind, kind = f"f{width}", f"i{width}"
        snan = "nan:0x123"
        expressions = [
            f"({float_kind}.abs ({float_kind}.const -{snan}))",
            f"({float_kind}.neg ({float_kind}.const {snan}))",
            f"({float_kind}.copysign ({float_kind}.const {snan}) ({float_kind}.const -0))",
            f"({float_kind}.nearest ({float_kind}.const -0.5))",
            f"({float_kind}.min ({float_kind}.const 0) ({float_kind}.const -0))",
            f"({float_kind}.max ({float_kind}.const -0) ({float_kind}.const 0))",
        ]
        for expression in expressions:
            export("float_bits", kind, f"({kind}.reinterpret_{float_kind} {expression})")
    for kind, op in [("i32", "div_s"), ("i64", "div_u"), ("i32", "rem_s"), ("i64", "rem_u")]:
        export("trap", kind, f"({kind}.{op} ({kind}.const 123) ({kind}.const 0))")
    for width in (32, 64):
        kind = f"i{width}"
        export("trap", kind, f"({kind}.div_s ({kind}.const {-2 ** (width - 1)}) ({kind}.const -1))")
    export("trap", "i32", "(i32.load (i32.const 65535))")
    export("trap", "i32", "unreachable")
    source.append(")")
    if Counter(item["category"] for item in exports) != EXPECTED_CATEGORIES:
        raise SystemExit("unexpected reference program categories")
    return "\n".join(source) + "\n", exports


def oracle_commands(stdout: str, exports: list[dict]) -> list[dict]:
    lines = stdout.splitlines()
    if len(lines) != len(exports):
        raise SystemExit(f"oracle produced {len(lines)} outcomes, expected {len(exports)}")
    commands = []
    for index, (line, item) in enumerate(zip(lines, exports, strict=True), 1):
        prefix = f"{item['name']}() => "
        if not line.startswith(prefix):
            raise SystemExit(f"unexpected oracle output: {line}")
        outcome = line[len(prefix):]
        action = {"type": "invoke", "field": item["name"], "args": []}
        if outcome.startswith("error: "):
            reason = outcome.removeprefix("error: ")
            if reason == "unreachable executed":
                reason = "unreachable"
            if reason.startswith("out of bounds memory access"):
                reason = "out of bounds memory access"
            if reason not in {"integer divide by zero", "integer overflow", "out of bounds memory access", "unreachable"}:
                raise SystemExit(f"unexpected oracle trap: {reason}")
            commands.append({"type": "assert_trap", "line": index, "action": action, "text": reason})
        else:
            match = re.fullmatch(r"(i32|i64):([0-9]+)", outcome)
            if not match or match[1] != item["result"]:
                raise SystemExit(f"unexpected oracle value: {outcome}")
            commands.append({"type": "assert_return", "line": index, "action": action, "expected": [{"type": match[1], "value": match[2]}]})
    return commands


def generate(args: argparse.Namespace) -> None:
    tools = {name: args.wabt_bin / name for name in TOOL_SHA256}
    for name, tool in tools.items():
        if digest(tool.read_bytes()) != TOOL_SHA256[name]:
            raise SystemExit(f"expected the pinned WABT {WABT_VERSION} Linux x64 executable: {name}")
        if subprocess.check_output([str(tool), "--version"], text=True).strip() != WABT_VERSION:
            raise SystemExit(f"unexpected {name} version")
    wat, exports = programs()
    with tempfile.TemporaryDirectory(prefix="gomlang-wasm-differential-") as raw:
        temp = Path(raw)
        (temp / "reference.wat").write_text(wat)
        subprocess.run([str(tools["wat2wasm"]), str(temp / "reference.wat"), "-o", str(temp / "reference.wasm")], check=True)
        binary = (temp / "reference.wasm").read_bytes()
        stdout = subprocess.check_output([str(tools["wasm-interp"]), str(temp / "reference.wasm"), "--run-all-exports"], text=True)
    commands = [{"type": "module", "line": 0, "wasm": base64.b64encode(binary).decode("ascii")}]
    commands.extend(oracle_commands(stdout, exports))
    fixture = json.dumps({"source": "WABT-1.0.42-reference.wat", "commands": commands}, separators=(",", ":")) + "\n"
    files = {"reference.wat": wat.encode(), "reference.out": stdout.encode(), "reference.json": fixture.encode()}
    manifest = {
        "oracle": "WABT wasm-interp", "wabt_version": WABT_VERSION,
        "wabt_url": f"https://github.com/WebAssembly/wabt/releases/tag/{WABT_VERSION}",
        "wabt_linux_x64_archive_sha256": WABT_ARCHIVE_SHA256,
        "tool_sha256": TOOL_SHA256, "seed": f"0x{SEED:x}",
        "categories": EXPECTED_CATEGORIES, "outcomes": 160,
        "command_counts": dict(sorted(Counter(c["type"] for c in commands).items())),
        "files": {name: digest(data) for name, data in files.items()},
    }
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (FIXTURES / name).write_bytes(data)
    (FIXTURES / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    check()
    print("Generated 160 WABT reference outcomes: 152 exact integer/float-bit results and 8 traps")


def check() -> None:
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    if (manifest["wabt_version"] != WABT_VERSION
            or manifest["wabt_linux_x64_archive_sha256"] != WABT_ARCHIVE_SHA256
            or manifest["tool_sha256"] != TOOL_SHA256
            or manifest["seed"] != f"0x{SEED:x}"
            or manifest["categories"] != EXPECTED_CATEGORIES or manifest["outcomes"] != 160):
        raise SystemExit("unexpected differential provenance or coverage")
    if set(manifest["files"]) != {"reference.wat", "reference.out", "reference.json"}:
        raise SystemExit("unexpected differential fixture file set")
    for name, checksum in manifest["files"].items():
        if digest((FIXTURES / name).read_bytes()) != checksum:
            raise SystemExit(f"differential fixture checksum mismatch: {name}")
    wat, exports = programs()
    if (FIXTURES / "reference.wat").read_text() != wat:
        raise SystemExit("reference input differs from deterministic generator")
    commands = json.loads((FIXTURES / "reference.json").read_text())["commands"]
    if commands[1:] != oracle_commands((FIXTURES / "reference.out").read_text(), exports):
        raise SystemExit("reference expectations differ from recorded independent oracle output")
    counts = dict(sorted(Counter(c["type"] for c in commands).items()))
    if counts != {"assert_return": 152, "assert_trap": 8, "module": 1} or counts != manifest["command_counts"]:
        raise SystemExit("expected 152 reference results, 8 traps, and 1 module")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    generate_parser = modes.add_parser("generate")
    generate_parser.add_argument("--wabt-bin", type=Path, required=True)
    modes.add_parser("check")
    args = parser.parse_args()
    if args.mode == "generate":
        generate(args)
    else:
        check()
        print("Verified 160 independently recorded WABT reference outcomes")


if __name__ == "__main__":
    main()
