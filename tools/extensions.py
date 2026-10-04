#!/usr/bin/env python3
"""Regenerate the pinned Core 2.0 scalar/reference/bulk-memory corpus offline.

Generate requires the authenticated upstream source archive and pinned WABT
wast2json. Tests use retained fixtures only; no engine is invoked at runtime.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "examples/extensions/tests/data/spec"
SPEC_COMMIT = "fffc6e12fa454e475455a7b58d3b5dc343980c10"
SPEC_SHA256 = "597e3ea796ac08bb5f041513afa9f538b1e7f7619d865225ac482983a7af35cf"
WABT_VERSION = "1.0.42"
WABT_ARCHIVE_SHA256 = "84895407a6bbb80e918f33b16b2fb2206021c150b6bc9ff6f761263a745ab131"
WAST2JSON_SHA256 = "2785953b9de5bf26d62cdfa7563607ed83a560097ec0d4ad1d69e5b8b2ecda86"
MANIFEST_SHA256 = "b8595b2cae13a1873ff67f3ee72dc9a005736598ff14900b5078d71477d0ac09"
LICENSE_SHA256 = "c6596eb7be8581c18be736c846fb9173b69eccf6ef94c5135893ec56bd92ba08"
FLAGS = ["--no-check", "--disable-simd", "--disable-tail-call", "--disable-memory64", "--disable-multi-memory", "--disable-extended-const", "--disable-relaxed-simd"]
COUNTS = {"action": 155, "assert_exhaustion": 15, "assert_invalid": 1477, "assert_malformed": 719, "assert_return": 21453, "assert_trap": 2354, "assert_uninstantiable": 34, "assert_unlinkable": 83, "module": 1126, "register": 21}
ENCODING_CORRECTIONS = [
    {"source": "memory_init.wast", "line": 190,
     "input_sha256": "47ebb6382fc1d9222cc6e9eed7c405d64f3e468998d058cf734c14c47b50a958",
     "output_sha256": "9e78de937e44ce99e09662c1bc467c2aab5669c0e67e21963275f618328a1b90",
     "reason": "WABT --no-check omits required data_count=0 for text data.drop with no data segments; add section 12 before code to preserve the official validation assertion"},
    {"source": "memory_init.wast", "line": 227,
     "input_sha256": "edd265999b169d67f8e3556b9952c82aa3dc39d1a85c0098a1a98c05e4791d5e",
     "output_sha256": "7ae8b8f1e8948ed5d6c8d1c4660555369098a34d8150c708db557eeba94ec67a",
     "reason": "WABT --no-check omits required data_count=0 for text memory.init with no data segments; add section 12 before code to preserve the official validation assertion"},
]
EXPECTED_FILES = frozenset("""
address align binary-leb128 binary block br br_if br_table bulk call call_indirect
comments const conversions custom data elem endianness exports f32 f32_bitwise f32_cmp
f64 f64_bitwise f64_cmp fac float_exprs float_literals float_memory float_misc forward
func func_ptrs global i32 i64 if imports inline-module int_exprs int_literals labels
left-to-right linking load local_get local_set local_tee loop memory memory_copy
memory_fill memory_grow memory_init memory_redundancy memory_size memory_trap names
nop obsolete-keywords ref_func ref_is_null ref_null return select skip-stack-guard-page
stack start store switch table-sub table table_copy table_fill table_get table_grow
table_init table_set table_size token traps type unreachable unreached-invalid
unreached-valid unwind utf8-custom-section-id utf8-import-field utf8-import-module
utf8-invalid-encoding
""".split())


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def correct_encoding(source: str, command: dict, binary: bytes) -> bytes:
    for correction in ENCODING_CORRECTIONS:
        if source != correction["source"] or command["line"] != correction["line"]:
            continue
        if command["type"] != "assert_invalid" or sha(binary) != correction["input_sha256"]:
            raise SystemExit("encoding correction input differs from the pinned official text assertion")
        cursor = 8
        while cursor < len(binary):
            start = cursor
            section = binary[cursor]
            cursor += 1
            length, shift = 0, 0
            while True:
                value = binary[cursor]
                cursor += 1
                length |= (value & 127) << shift
                if value < 128:
                    break
                shift += 7
            if section == 10:
                output = binary[:start] + bytes([12, 1, 0]) + binary[start:]
                if sha(output) != correction["output_sha256"]:
                    raise SystemExit("encoding correction output differs from the pinned bytes")
                return output
            cursor += length
        raise SystemExit("encoding correction could not find code section")
    return binary


def runner_source() -> str:
    return (ROOT / "examples/conformance/main.goml").read_text().replace("examples/conformance", "examples/extensions")


def sync() -> None:
    (ROOT / "examples/extensions").mkdir(parents=True, exist_ok=True)
    (ROOT / "examples/extensions/main.goml").write_text(runner_source())
    source = ["package tests;", "", "use ecosystem::wasm::examples::extensions as runner;", "use std::testing;", ""]
    for name in sorted(EXPECTED_FILES):
        source.extend(["#[test]", f"fn core2_{name.replace('-', '_')}() -> () {{", f'    testing::expect_ok(runner::run_fixture("{name}.json"), "Core2 {name}");', "}", ""])
    (ROOT / "examples/extensions/tests").mkdir(parents=True, exist_ok=True)
    (ROOT / "examples/extensions/tests/extensions_test.goml").write_text("\n".join(source))


def generate(args: argparse.Namespace) -> None:
    if sha(args.spec_archive.read_bytes()) != SPEC_SHA256:
        raise SystemExit("unexpected Core2 source archive checksum; retained fixtures unchanged")
    if sha(args.wast2json.read_bytes()) != WAST2JSON_SHA256:
        raise SystemExit("expected the pinned WABT1.0.42 Linux x64 wast2json executable")
    if subprocess.check_output([str(args.wast2json), "--version"], text=True).strip() != WABT_VERSION:
        raise SystemExit("unexpected wast2json version")
    records, omissions, exclusions, outputs = [], [], [], {}
    counts: Counter[str] = Counter()
    with tempfile.TemporaryDirectory(prefix="gomlang-wasm-core2-") as raw:
        temp = Path(raw)
        with tarfile.open(args.spec_archive) as archive:
            archive.extractall(temp, filter="data")
        spec = temp / f"spec-{SPEC_COMMIT}"
        scripts = sorted((spec / "test/core").glob("*.wast"))
        if {source.stem for source in scripts} != EXPECTED_FILES:
            raise SystemExit("source archive does not contain the expected 90 top-level scripts")
        for source in sorted((spec / "test/core/simd").glob("*.wast")):
            exclusions.append({"source": "simd/" + source.name, "source_sha256": sha(source.read_bytes()), "reason": "SIMD/v128 is outside this release's implemented feature set"})
        for source in scripts:
            generated = temp / f"{source.stem}.json"
            subprocess.run([str(args.wast2json), str(source), "-o", str(generated), *FLAGS], check=True)
            commands = []
            for command in json.loads(generated.read_text())["commands"]:
                kind = command["type"]
                if kind not in COUNTS:
                    raise SystemExit(f"unknown script command {kind}")
                if kind == "assert_malformed" and command.get("module_type") == "text":
                    omissions.append({"source": source.name, "line": command["line"], "text": command["text"], "reason": "WAT syntax; interpreter API accepts binary modules"})
                    continue
                if "filename" in command:
                    file = temp / command.pop("filename")
                    if file.suffix != ".wasm":
                        raise SystemExit(f"unexpected fixture suffix {file}")
                    command["wasm"] = base64.b64encode(correct_encoding(source.name, command, file.read_bytes())).decode("ascii")
                commands.append(command)
                counts[kind] += 1
            encoded = (json.dumps({"source": source.name, "revision": "core2", "commands": commands}, ensure_ascii=True, separators=(",", ":")) + "\n").encode()
            outputs[generated.name] = encoded
            records.append({"file": generated.name, "sha256": sha(encoded), "source_sha256": sha(source.read_bytes()), "commands": len(commands)})
        license_bytes = (spec / "test/LICENSE").read_bytes()
    if dict(counts) != COUNTS or len(omissions) != 581 or len(exclusions) != 58 or sha(license_bytes) != LICENSE_SHA256:
        raise SystemExit("generated corpus differs from the pinned count/license baseline")
    manifest = {
        "spec_commit": SPEC_COMMIT, "spec_archive_sha256": SPEC_SHA256,
        "spec_url": f"https://github.com/WebAssembly/spec/tree/{SPEC_COMMIT}/test/core",
        "wabt_version": WABT_VERSION, "wabt_linux_x64_archive_sha256": WABT_ARCHIVE_SHA256,
        "wast2json_sha256": WAST2JSON_SHA256, "wast2json_flags": FLAGS,
        "scripts": records, "executed_commands": sum(counts.values()), "command_counts": dict(sorted(counts.items())),
        "omitted_commands": omissions, "excluded_scripts": exclusions, "encoding_corrections": ENCODING_CORRECTIONS, "license_sha256": LICENSE_SHA256,
    }
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode()
    if sha(manifest_bytes) != MANIFEST_SHA256:
        raise SystemExit("regenerated Core2 manifest differs from pinned baseline; fixtures unchanged")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, encoded in outputs.items():
        (FIXTURES / name).write_bytes(encoded)
    (FIXTURES / "LICENSE").write_bytes(license_bytes)
    (FIXTURES / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    sync()
    check()
    print("Generated 90 Core2 scripts / 27437 binary commands; 581 WAT assertions and 58 SIMD scripts explicitly outside scope")


def check() -> dict:
    manifest_bytes = (FIXTURES / "manifest.json").read_bytes()
    if sha(manifest_bytes) != MANIFEST_SHA256:
        raise SystemExit("Core2 manifest differs from pinned source, fixture, correction, and exclusion hashes")
    manifest = json.loads(manifest_bytes)
    if (manifest["spec_commit"] != SPEC_COMMIT or manifest["spec_archive_sha256"] != SPEC_SHA256
            or manifest["wabt_version"] != WABT_VERSION or manifest["wabt_linux_x64_archive_sha256"] != WABT_ARCHIVE_SHA256
            or manifest["wast2json_sha256"] != WAST2JSON_SHA256 or manifest["wast2json_flags"] != FLAGS):
        raise SystemExit("unexpected Core2 provenance")
    names = [record["file"] for record in manifest["scripts"]]
    expected = {name + ".json" for name in EXPECTED_FILES}
    if len(names) != 90 or len(set(names)) != 90 or set(names) != expected:
        raise SystemExit("expected the exact 90 unique Core2 script files")
    if {path.name for path in FIXTURES.glob("*.json")} != expected | {"manifest.json"}:
        raise SystemExit("unexpected Core2 fixture JSON file set")
    if manifest["executed_commands"] != 27437 or len(manifest["omitted_commands"]) != 581 or len(manifest["excluded_scripts"]) != 58:
        raise SystemExit("Core2 fixture coverage differs from its pinned baseline")
    if manifest["encoding_corrections"] != ENCODING_CORRECTIONS:
        raise SystemExit("unexpected Core2 encoding corrections")
    counts: Counter[str] = Counter()
    for record in manifest["scripts"]:
        path = FIXTURES / record["file"]
        if sha(path.read_bytes()) != record["sha256"]:
            raise SystemExit(f"Core2 checksum mismatch: {path.name}")
        script = json.loads(path.read_text())
        if script["source"] != path.with_suffix(".wast").name or script["revision"] != "core2" or len(script["commands"]) != record["commands"]:
            raise SystemExit(f"Core2 metadata mismatch: {path.name}")
        counts.update(command["type"] for command in script["commands"])
    if dict(counts) != COUNTS or manifest["command_counts"] != COUNTS:
        raise SystemExit("Core2 command counts differ from the pinned baseline")
    if manifest["license_sha256"] != LICENSE_SHA256 or sha((FIXTURES / "LICENSE").read_bytes()) != LICENSE_SHA256:
        raise SystemExit("Core2 source license checksum mismatch")
    if (ROOT / "examples/extensions/main.goml").read_text() != runner_source():
        raise SystemExit("extensions runner has drifted; use tools/extensions.py sync")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    gen = modes.add_parser("generate")
    gen.add_argument("--spec-archive", type=Path, required=True)
    gen.add_argument("--wast2json", type=Path, required=True)
    modes.add_parser("check")
    modes.add_parser("sync")
    args = parser.parse_args()
    if args.mode == "generate":
        generate(args)
    elif args.mode == "sync":
        sync()
    else:
        check()
        print("Verified 90 Core2 scripts and 27437 binary commands")


if __name__ == "__main__":
    main()
