#!/usr/bin/env python3
"""Regenerate and run the pinned WebAssembly Core 1.0 binary conformance corpus.

Generation requires an extracted spec checkout and WABT wast2json. Running and
checking use retained fixtures only, with no network or external Wasm engine.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "examples/conformance/tests/data/spec"
SPEC_COMMIT = "f750d21dcc4903280b4db80ca81795968c5557f4"
SPEC_ARCHIVE_SHA256 = "303372fc8002304495053646732373c38982e4b4b4af6ec16d7cab7556aa3425"
WABT_VERSION = "1.0.42"
WABT_LINUX_X64_SHA256 = "84895407a6bbb80e918f33b16b2fb2206021c150b6bc9ff6f761263a745ab131"
FLAGS = [
    "--no-check", "--disable-mutable-globals", "--disable-saturating-float-to-int",
    "--disable-sign-extension", "--disable-simd", "--disable-multi-value",
    "--disable-tail-call", "--disable-bulk-memory", "--disable-reference-types",
    "--disable-memory64", "--disable-multi-memory", "--disable-extended-const",
    "--disable-relaxed-simd",
]
EXPECTED_SCRIPT_FILES = frozenset("""
address.json align.json binary-leb128.json binary.json block.json br.json
br_if.json br_table.json break-drop.json call.json call_indirect.json comments.json
const.json conversions.json custom.json data.json elem.json endianness.json
exports.json f32.json f32_bitwise.json f32_cmp.json f64.json f64_bitwise.json
f64_cmp.json fac.json float_exprs.json float_literals.json float_memory.json float_misc.json
forward.json func.json func_ptrs.json global.json i32.json i64.json
if.json imports.json inline-module.json int_exprs.json int_literals.json labels.json
left-to-right.json linking.json load.json local_get.json local_set.json local_tee.json
loop.json memory.json memory_grow.json memory_redundancy.json memory_size.json memory_trap.json
names.json nop.json return.json select.json skip-stack-guard-page.json stack.json
start.json store.json switch.json table.json token.json traps.json
type.json unreachable.json unreached-invalid.json unwind.json utf8-custom-section-id.json utf8-import-field.json
utf8-import-module.json utf8-invalid-encoding.json
""".split())
EXPECTED_COMMAND_COUNTS = {'action': 42, 'assert_exhaustion': 15, 'assert_invalid': 989, 'assert_malformed': 662, 'assert_return': 15793, 'assert_trap': 461, 'assert_uninstantiable': 2, 'assert_unlinkable': 95, 'module': 833, 'register': 10}
EXPECTED_SOURCE_SET_SHA256 = "de65c003e5051c9d92b9e3135f734568a2bb85fb7b721b68e76ef83481e02dad"
EXPECTED_LICENSE_SHA256 = "c6596eb7be8581c18be736c846fb9173b69eccf6ef94c5135893ec56bd92ba08"
EXPECTED_EXECUTED = 18902
EXPECTED_OMITTED = 492

COMMANDS = {
    "module", "register", "action", "assert_return", "assert_trap",
    "assert_exhaustion", "assert_malformed", "assert_invalid",
    "assert_unlinkable", "assert_uninstantiable",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(args: argparse.Namespace) -> None:
    retained = check()
    spec = args.spec_root.resolve()
    # Authenticate every source before any retained output can be overwritten.
    sources = sorted((spec / "test/core").glob("*.wast"))
    expected_sources = {Path(record["file"]).with_suffix(".wast").name: record["source_sha256"] for record in retained["scripts"]}
    if {source.name for source in sources} != set(expected_sources):
        raise SystemExit("source script set differs from the pinned Core 1.0 corpus")
    for source in sources:
        if digest(source) != expected_sources[source.name]:
            raise SystemExit(f"source checksum mismatch: {source.name}; retained fixtures unchanged")
    if digest(spec / "test/LICENSE") != EXPECTED_LICENSE_SHA256:
        raise SystemExit("source license checksum mismatch; retained fixtures unchanged")
    version = subprocess.check_output([args.wast2json, "--version"], text=True).strip()
    if version != WABT_VERSION:
        raise SystemExit(f"expected WABT {WABT_VERSION}, got {version}")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    records = []
    omitted = []
    counts: Counter[str] = Counter()
    outputs = {}
    with tempfile.TemporaryDirectory(prefix="gomlang-wasm-spec-") as raw:
        temp = Path(raw)
        for source in sources:
            generated = temp / f"{source.stem}.json"
            subprocess.run([args.wast2json, str(source), "-o", str(generated), *FLAGS], check=True)
            script = json.loads(generated.read_text())
            commands = []
            for command in script["commands"]:
                kind = command["type"]
                if kind not in COMMANDS:
                    raise SystemExit(f"unhandled command {source.name}:{command['line']}: {kind}")
                if kind == "assert_malformed" and command.get("module_type") == "text":
                    omitted.append({"source": source.name, "line": command["line"], "text": command["text"], "reason": "WAT syntax; library accepts Wasm binary only"})
                    continue
                if "filename" in command:
                    binary = temp / command.pop("filename")
                    if binary.suffix != ".wasm":
                        raise SystemExit(f"unexpected non-binary fixture {binary}")
                    command["wasm"] = base64.b64encode(binary.read_bytes()).decode("ascii")
                counts[kind] += 1
                commands.append(command)
            output = FIXTURES / f"{source.stem}.json"
            encoded = (json.dumps({"source": source.name, "commands": commands}, ensure_ascii=True, separators=(",", ":")) + "\n").encode()
            outputs[output] = encoded
            records.append({"file": output.name, "sha256": hashlib.sha256(encoded).hexdigest(), "source_sha256": digest(source), "commands": len(commands)})
    # Regeneration with pinned sources and tool version must be byte-for-byte.
    if records != retained["scripts"] or omitted != retained["omitted_commands"] or dict(sorted(counts.items())) != EXPECTED_COMMAND_COUNTS:
        raise SystemExit("generated corpus differs from the retained baseline; fixtures unchanged")
    for output, encoded in outputs.items():
        output.write_bytes(encoded)
    shutil.copyfile(spec / "test/LICENSE", FIXTURES / "LICENSE")
    manifest = {
        "spec_commit": SPEC_COMMIT,
        "spec_archive_sha256": SPEC_ARCHIVE_SHA256,
        "spec_url": f"https://github.com/WebAssembly/spec/tree/{SPEC_COMMIT}/test/core",
        "wabt_version": WABT_VERSION,
        "wabt_linux_x64_archive_sha256": WABT_LINUX_X64_SHA256,
        "wast2json_flags": FLAGS,
        "command_counts": dict(sorted(counts.items())),
        "executed_commands": sum(counts.values()),
        "omitted_commands": omitted,
        "scripts": records,
        "license_sha256": digest(FIXTURES / "LICENSE"),
    }
    (FIXTURES / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n")
    test_source = ["package tests;", "", "use ecosystem::wasm::examples::conformance as runner;", "use std::testing;", ""]
    for record in records:
        name = Path(record["file"]).stem.replace("-", "_")
        test_source.extend(["#[test]", f"fn spec_{name}() -> () {{", f'    testing::expect_ok(runner::run_fixture("{record["file"]}"), "{record["file"]}");', "}", ""])
    (ROOT / "examples/conformance/tests/conformance_test.goml").write_text("\n".join(test_source))
    check()
    print(f"Generated {len(records)} scripts, {sum(counts.values())} binary commands; {len(omitted)} WAT syntax assertions outside library scope")


def check() -> dict:
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    if (manifest["spec_commit"] != SPEC_COMMIT
            or manifest["spec_archive_sha256"] != SPEC_ARCHIVE_SHA256
            or manifest["spec_url"] != f"https://github.com/WebAssembly/spec/tree/{SPEC_COMMIT}/test/core"
            or manifest["wabt_version"] != WABT_VERSION
            or manifest["wabt_linux_x64_archive_sha256"] != WABT_LINUX_X64_SHA256
            or manifest["wast2json_flags"] != FLAGS):
        raise SystemExit("unexpected fixture provenance")
    names = [record["file"] for record in manifest["scripts"]]
    if len(names) != 74 or len(set(names)) != 74 or set(names) != EXPECTED_SCRIPT_FILES:
        raise SystemExit("expected the exact 74 unique Core 1.0 scripts")
    if {path.name for path in FIXTURES.glob("*.json")} != EXPECTED_SCRIPT_FILES | {"manifest.json"}:
        raise SystemExit("unexpected fixture JSON file set")
    source_set = json.dumps(sorted((record["file"], record["source_sha256"]) for record in manifest["scripts"]), separators=(",", ":"))
    if hashlib.sha256(source_set.encode()).hexdigest() != EXPECTED_SOURCE_SET_SHA256:
        raise SystemExit("source manifest does not match the pinned commit")
    if (manifest["executed_commands"] != EXPECTED_EXECUTED
            or len(manifest["omitted_commands"]) != EXPECTED_OMITTED
            or manifest["command_counts"] != EXPECTED_COMMAND_COUNTS):
        raise SystemExit("expected exactly 18902 binary commands and 492 WAT syntax omissions")
    counts: Counter[str] = Counter()
    for record in manifest["scripts"]:
        path = FIXTURES / record["file"]
        if digest(path) != record["sha256"]:
            raise SystemExit(f"fixture checksum mismatch: {path.name}")
        document = json.loads(path.read_text())
        if document["source"] != path.with_suffix(".wast").name:
            raise SystemExit(f"fixture source name mismatch: {path.name}")
        commands = document["commands"]
        if len(commands) != record["commands"]:
            raise SystemExit(f"fixture command count mismatch: {path.name}")
        counts.update(c["type"] for c in commands)
    if dict(sorted(counts.items())) != manifest["command_counts"] or sum(counts.values()) != manifest["executed_commands"]:
        raise SystemExit("fixture totals mismatch")
    if digest(FIXTURES / "LICENSE") != EXPECTED_LICENSE_SHA256 or manifest["license_sha256"] != EXPECTED_LICENSE_SHA256:
        raise SystemExit("fixture license checksum mismatch")
    return manifest


def run(args: argparse.Namespace) -> None:
    manifest = check()
    runner = args.runner
    if runner is None:
        subprocess.run([os.environ.get("GOML", "goml"), "build", "--example", "conformance"], cwd=ROOT, check=True)
        runner = ROOT / "_artifact/bin/examples/conformance/conformance"
    runner = runner.resolve()
    failed = []
    completed = 0
    commands = 0
    for script in manifest["scripts"]:
        if args.filter and args.filter not in script["file"]:
            continue
        try:
            result = subprocess.run([str(runner), str(FIXTURES / script["file"])], cwd=ROOT, capture_output=True, text=True, timeout=args.timeout)
            if result.returncode:
                failed.append(script["file"])
                print(f"FAIL {script['file']}\n{result.stdout}{result.stderr}", flush=True)
            else:
                completed += 1
                commands += script["commands"]
                print(result.stdout.strip(), flush=True)
        except subprocess.TimeoutExpired:
            failed.append(script["file"])
            print(f"FAIL {script['file']}: timeout after {args.timeout}s", flush=True)
    if completed == 0 and not failed:
        raise SystemExit("no scripts selected")
    print(f"Conformance: {completed} scripts and {commands} commands passed; {len(failed)} scripts failed.")
    if args.report:
        args.report.write_text(json.dumps({"spec_commit": SPEC_COMMIT, "passed_scripts": completed, "passed_commands": commands, "failed_scripts": failed, "wat_syntax_omissions": len(manifest["omitted_commands"])}, indent=2) + "\n")
    if failed:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    gen = modes.add_parser("generate")
    gen.add_argument("--spec-root", type=Path, required=True)
    gen.add_argument("--wast2json", required=True)
    modes.add_parser("check")
    execute = modes.add_parser("run")
    execute.add_argument("--runner", type=Path)
    execute.add_argument("--filter", default="")
    execute.add_argument("--timeout", type=float, default=120)
    execute.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.mode == "generate":
        generate(args)
    elif args.mode == "check":
        manifest = check()
        print(f"Verified {len(manifest['scripts'])} scripts and {manifest['executed_commands']} commands")
    else:
        run(args)


if __name__ == "__main__":
    main()
