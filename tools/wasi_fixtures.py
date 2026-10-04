#!/usr/bin/env python3
"""Authenticate and rebuild the retained wasi-sdk C integration fixtures.

Only generation needs the SDK archive. Checks and GoML tests run offline.
Pinned source, notice and binary hashes deliberately require explicit review
when changing the C programs or their compiler.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "examples/wasi/tests/data"
SDK_VERSION = "24.0"
SDK_DIRECTORY = "wasi-sdk-24.0-x86_64-linux"
SDK_URL = "https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-24/wasi-sdk-24.0-x86_64-linux.tar.gz"
SDK_SHA256 = "c6c38aab56e5de88adf6c1ebc9c3ae8da72f88ec2b656fb024eda8d4167a0bc5"
LLVM_COMMIT = "26a1d6601d727a96f4301d0d8647b5a42760ae0c"
LIBC_COMMIT = "b9ef79d7dbd47c6c5bafdae760823467c2f60b70"
CLANG_VERSION = f"clang version 18.1.2-wasi-sdk (https://github.com/llvm/llvm-project {LLVM_COMMIT})"
FLAGS = [
    "--target=wasm32-wasip1", "-O1", "-fno-builtin", "-mno-simd128",
    "-mno-relaxed-simd", "-Wl,--strip-all", "-Wl,--max-memory=16777216",
    "-Wl,-z,stack-size=65536",
]
PROGRAMS = {
    "command": {
        "source_sha256": "060c4da366eee804ed4a7e6e1123a3aca85940bb37aeec876a2f92a4f42a82ca",
        "wasm_sha256": "d3695a965c193c0a1bca75cce27e467cb3e781d294df7dcd24d355ccf27570f8",
        "extra_flags": [],
    },
    "abi_probe": {
        "source_sha256": "3dc9c2b680c55190cdc0d0865d6d43ef2fa229f81cb0eb387a53c9a6495c9266",
        "wasm_sha256": "ca5ad08ce2d36e5058d73052de6c33a1a4837c059f7009093a9e8e2678ea3b9a",
        "extra_flags": ["-mexec-model=reactor"],
    },
}
NOTICE_SHA256 = {
    "WASI-LIBC-LICENSE": "673f577e363e80e0058bd78214683f045d1d0c63930969a87f01a1d87d7cf1d6",
    "WASI-LIBC-LICENSE-APACHE": "a60eea817514531668d7e00765731449fe14d059d3249e0bc93b36de45f759f2",
    "WASI-LIBC-LICENSE-APACHE-LLVM": "268872b9816f90fd8e85db5a28d33f8150ebb8dd016653fb39ef1f94f2686bc5",
    "WASI-LIBC-LICENSE-MIT": "23f18e03dc49df91622fe2a76176497404e46ced8a715d9d2b67a7446571cca3",
    "WASI-LIBC-dlmalloc-NOTICE": "da52583f07b5f00a5ffcce044ad858528e2e1ab1eeffeee954269e49873ef60c",
    "WASI-LIBC-libc-bottom-half-cloudlibc-LICENSE": "c8b789cf5a746611e6300a0cc7750dbf92b61912a709d04e639245f7290656d0",
    "WASI-LIBC-libc-top-half-musl-COPYRIGHT": "f9bc4423732350eb0b3f7ed7e91d530298476f8fec0c6c427a1c04ade22655af",
    "WASI-SDK-LICENSE": "268872b9816f90fd8e85db5a28d33f8150ebb8dd016653fb39ef1f94f2686bc5",
}
NOTICE_PATHS = {
    "WASI-LIBC-LICENSE": "LICENSE",
    "WASI-LIBC-LICENSE-APACHE": "LICENSE-APACHE",
    "WASI-LIBC-LICENSE-APACHE-LLVM": "LICENSE-APACHE-LLVM",
    "WASI-LIBC-LICENSE-MIT": "LICENSE-MIT",
    "WASI-LIBC-dlmalloc-NOTICE": "dlmalloc/src/malloc.c",
    "WASI-LIBC-libc-bottom-half-cloudlibc-LICENSE": "libc-bottom-half/cloudlibc/LICENSE",
    "WASI-LIBC-libc-top-half-musl-COPYRIGHT": "libc-top-half/musl/COPYRIGHT",
}
WASI_COMMIT = "41c4383548ba7a06df5df7232b68a6f0bbb93e2d"
WITX_SOURCES = {
    "wasi_snapshot_preview1.witx": ("legacy/preview1/witx/wasi_snapshot_preview1.witx", "8bb1fb59ee64cefed64d9ad0376d93ddec416becaf9b1265c923af03c261260a"),
    "typenames.witx": ("legacy/preview1/witx/typenames.witx", "e06e9545a1797120b48a666a4ee78c0760ecbc60789690e22d735f0467cb92ed"),
    "witx-docs.md": ("legacy/tools/witx-docs.md", "51e7637cc05befc3c0e3bca71f9eac2093de1bea0dd5d220a5f4f8dff7dcdf7a"),
    "LICENSE.md": ("LICENSE.md", "0416590f3f47381bb5b9b467c27824d1228fac58b8031d693130865273ffefcb"),
}


def digest(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def witx_expressions(path: Path) -> list:
    # This deliberately parses only the syntax in the hash-pinned sources.
    source = path.read_text()
    if "(;" in source:
        raise SystemExit("unsupported WITX block comment")
    source = re.sub(r";;[^\n]*", "", source)
    tokens = re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', source)
    stack = [[]]
    for token in tokens:
        if token == "(":
            child = []
            stack[-1].append(child)
            stack.append(child)
        elif token == ")":
            if len(stack) == 1:
                raise SystemExit("unbalanced WITX expression")
            stack.pop()
        else:
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    if len(stack) != 1:
        raise SystemExit("unbalanced WITX expression")
    return stack[0]


def abi_artifacts() -> dict[str, bytes]:
    for name, (_, checksum) in WITX_SOURCES.items():
        if digest(DATA / "abi" / name) != checksum:
            raise SystemExit(f"WITX source checksum mismatch: {name}")
    types = {}
    for expression in witx_expressions(DATA / "abi/typenames.witx"):
        if len(expression) != 3 or expression[0] != "typename" or expression[1] in types:
            raise SystemExit("unexpected WITX type declaration")
        types[expression[1]] = expression[2]

    def lower(typ: str | list) -> list[str]:
        if isinstance(typ, str):
            if typ.startswith("$"):
                return lower(types[typ])
            if typ == "string":
                return ["i32", "i32"]
            if typ in {"u8", "u16", "u32", "s8", "s16", "s32"}:
                return ["i32"]
            if typ in {"u64", "s64"}:
                return ["i64"]
        elif typ[0] == "@witx" and typ[1] in {"pointer", "const_pointer"}:
            return ["i32"]
        elif typ[0] == "handle":
            return ["i32"]
        elif typ[0] == "list":
            return ["i32", "i32"]
        elif typ[0] in {"enum", "flags"} and typ[1][:2] in (["@witx", "tag"], ["@witx", "repr"]):
            return lower(typ[1][2])
        raise SystemExit(f"unsupported WITX parameter type: {typ}")

    expressions = witx_expressions(DATA / "abi/wasi_snapshot_preview1.witx")
    if len(expressions) != 2 or expressions[0] != ["use", "typenames.witx"]:
        raise SystemExit("unexpected WITX module inputs")
    module = expressions[1]
    if module[:2] != ["module", "$wasi_snapshot_preview1"] or module[2] != ["import", "memory", ["memory"]]:
        raise SystemExit("unexpected WITX module")
    signatures = []
    for declaration in module[3:]:
        if declaration[:2] != ["@interface", "func"] or declaration[2][0] != "export":
            raise SystemExit("unexpected WITX interface declaration")
        name = declaration[2][1]
        params, results = [], []
        for field in declaration[3:]:
            if field[0] == "param":
                params.extend(lower(field[2]))
            elif field[0] == "result":
                expected = field[2]
                if expected[0] != "expected" or expected[-1] != ["error", "$errno"]:
                    raise SystemExit("unexpected WITX result lowering")
                results.extend(lower("$errno"))
                if len(expected) == 3:
                    value = expected[1]
                    # expected success values are indirect; tuples have one
                    # result pointer per field, as defined by the Preview1 ABI.
                    count = len(value) - 1 if isinstance(value, list) and value[0] == "tuple" else 1
                    params.extend(["i32"] * count)
                elif len(expected) != 2:
                    raise SystemExit("unexpected WITX expected arity")
            elif field != ["@witx", "noreturn"]:
                raise SystemExit("unexpected WITX function field")
        signatures.append({"name": name, "params": params, "results": results})
    if len(signatures) != 46 or len({item["name"] for item in signatures}) != 46:
        raise SystemExit("expected all 46 unique Preview1 imports")

    def leb(value: int) -> bytes:
        result = bytearray()
        while value >= 128:
            result.append((value & 127) | 128)
            value >>= 7
        result.append(value)
        return bytes(result)

    def vector(items: list[bytes]) -> bytes:
        return leb(len(items)) + b"".join(items)

    def string(value: str) -> bytes:
        data = value.encode()
        return leb(len(data)) + data

    def section(number: int, payload: bytes) -> bytes:
        return bytes([number]) + leb(len(payload)) + payload

    codes = {"i32": b"\x7f", "i64": b"\x7e"}
    type_section = vector([b"\x60" + vector([codes[t] for t in item["params"]])
                           + vector([codes[t] for t in item["results"]]) for item in signatures])
    import_section = vector([string("wasi_snapshot_preview1") + string(item["name"]) + b"\x00" + leb(index)
                             for index, item in enumerate(signatures)])
    wasm = b"\x00asm\x01\x00\x00\x00" + section(1, type_section) + section(2, import_section)
    return {
        "abi/signatures.json": (json.dumps(signatures, indent=2) + "\n").encode(),
        "bin/abi_signatures.wasm": wasm,
    }


def manifest() -> dict:
    return {
        "format": 1,
        "sdk": {"version": SDK_VERSION, "archive_url": SDK_URL,
                "archive_sha256": SDK_SHA256, "clang_version": CLANG_VERSION,
                "llvm_commit": LLVM_COMMIT, "wasi_libc_commit": LIBC_COMMIT},
        "common_flags": FLAGS,
        "programs": PROGRAMS,
        "preview1_abi": {
            "repository": "https://github.com/WebAssembly/WASI",
            "commit": WASI_COMMIT,
            "signature_count": 46,
            "sources": {name: {"path": path, "sha256": checksum} for name, (path, checksum) in WITX_SOURCES.items()},
            "artifacts": {name: hashlib.sha256(data).hexdigest() for name, data in abi_artifacts().items()},
        },
        "notices": {
            name: {
                "sha256": checksum,
                "source": (f"https://raw.githubusercontent.com/WebAssembly/wasi-libc/{LIBC_COMMIT}/{NOTICE_PATHS[name]}"
                           if name in NOTICE_PATHS else
                           "https://raw.githubusercontent.com/WebAssembly/wasi-sdk/wasi-sdk-24/LICENSE"),
                "transformation": ("Initial public-domain notice before '* Version', followed by closing comment and newline"
                                   if name == "WASI-LIBC-dlmalloc-NOTICE" else "none"),
            }
            for name, checksum in NOTICE_SHA256.items()
        },
        "execution": "GoML interpreter through the public WASI Preview1 embedding API; no external runtime",
    }


def check() -> None:
    if json.loads((DATA / "manifest.json").read_text()) != manifest():
        raise SystemExit("WASI manifest differs from the reviewed compiler/source/notice baseline")
    expected = {"manifest.json"}
    for name, program in PROGRAMS.items():
        for relative, checksum in ((f"src/{name}.c", program["source_sha256"]),
                                   (f"bin/{name}.wasm", program["wasm_sha256"])):
            expected.add(relative)
            if digest(DATA / relative) != checksum:
                raise SystemExit(f"WASI fixture checksum mismatch: {relative}")
    for name, checksum in NOTICE_SHA256.items():
        relative = f"licenses/{name}"
        expected.add(relative)
        if digest(DATA / relative) != checksum:
            raise SystemExit(f"WASI notice checksum mismatch: {relative}")
    for name in WITX_SOURCES:
        expected.add(f"abi/{name}")
    for relative, content in abi_artifacts().items():
        expected.add(relative)
        if (DATA / relative).read_bytes() != content:
            raise SystemExit(f"WITX-derived ABI artifact mismatch: {relative}")
    actual = {str(path.relative_to(DATA)) for path in DATA.rglob("*") if path.is_file()}
    if actual != expected:
        raise SystemExit(f"unexpected WASI fixture file set: {actual ^ expected}")
    print("checked 2 wasi-sdk 24.0 C/wasm fixtures, 8 runtime notices and all 46 WITX ABI signatures")


def generate(archive: Path) -> None:
    # Authenticate all inputs before replacing any retained output.
    check()
    if digest(archive) != SDK_SHA256:
        raise SystemExit("expected the pinned wasi-sdk 24.0 Linux x86_64 archive")
    with tempfile.TemporaryDirectory(prefix="wasm-wasi-fixtures-") as temporary:
        work = Path(temporary)
        with tarfile.open(archive) as package:
            package.extractall(work, filter="data")
        compiler = work / SDK_DIRECTORY / "bin/clang"
        version = subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0]
        if version != CLANG_VERSION:
            raise SystemExit(f"unexpected wasi-sdk clang version: {version}")
        compiled = {}
        for name, program in PROGRAMS.items():
            output = work / f"{name}.wasm"
            subprocess.run([str(compiler), *FLAGS, *program["extra_flags"],
                            str(DATA / f"src/{name}.c"), "-o", str(output)], check=True)
            if digest(output) != program["wasm_sha256"]:
                raise SystemExit(f"rebuilt {name} differs from the reviewed compiler output")
            compiled[name] = output.read_bytes()
        # Every rebuild must match before any output is written.
        for name, data in compiled.items():
            (DATA / f"bin/{name}.wasm").write_bytes(data)
        for relative, content in abi_artifacts().items():
            (DATA / relative).write_bytes(content)
    check()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="verify retained fixtures and provenance offline")
    rebuild = commands.add_parser("generate", help="rebuild with an authenticated SDK archive")
    rebuild.add_argument("--sdk-archive", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "generate":
        generate(args.sdk_archive)
    else:
        check()


if __name__ == "__main__":
    main()
