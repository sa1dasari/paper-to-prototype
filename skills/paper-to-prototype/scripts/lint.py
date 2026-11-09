#!/usr/bin/env python3
"""Static checks for a generated notebook and its spec. Run this BEFORE executing.

Usage:
    python lint.py --notebook prototype.ipynb [--spec spec.json]
    python lint.py --spec spec.json

Prints JSON: {"blocking": [...], "warnings": [...]} and exits 1 if anything is blocking.

Blocking = things a notebook made from an untrusted paper must not do: shell escapes,
network or process libraries, reading the environment, touching files, eval/exec.
A reproduction notebook only needs math and plotting, so none of these are legitimate.

Warnings = the notebook contract (seeds, a printed metric, labelled axes, plt.show()).

This is a static check, not a sandbox. It catches the obvious and the lazy, not a
determined attacker. Read the generated code yourself too.
Requires: nothing beyond the standard library (nbformat is used if installed).
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

BANNED_MODULES = {
    "subprocess", "socket", "requests", "urllib", "urllib3", "http", "httpx", "aiohttp",
    "ftplib", "smtplib", "telnetlib", "ctypes", "shutil", "webbrowser", "pty", "paramiko",
    "importlib", "pathlib", "glob", "tempfile", "pickle", "marshal", "getpass", "keyring",
}
BANNED_OS_ATTRS = {
    "system", "popen", "environ", "getenv", "putenv", "remove", "unlink", "rmdir", "removedirs",
    "listdir", "scandir", "walk", "chmod", "chown", "kill", "fork", "execv", "execl", "spawnl",
    "startfile", "rename", "replace", "symlink",
}
BANNED_CALLS = {"eval", "exec", "compile", "__import__", "open", "input"}
SAFE_MAGICS = ("%matplotlib",)
SPEC_KEYS = ["title", "inputs", "outputs", "hyperparameters", "pseudocode",
             "key_equations", "evaluation_dataset", "toy_dataset_suggestion",
             "key_figure_description", "notes"]


def load_cells(path: Path) -> list[tuple[int, str]]:
    nb = json.loads(path.read_text(encoding="utf-8-sig"))
    out = []
    for i, c in enumerate(nb.get("cells", [])):
        if c.get("cell_type") == "code":
            src = c.get("source", "")
            out.append((i, "".join(src) if isinstance(src, list) else src))
    return out


def check_security(cells: list[tuple[int, str]]) -> list[str]:
    found: list[str] = []
    for idx, src in cells:
        clean_lines = []
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("!") or s.startswith("%%"):
                found.append(f"cell {idx}: shell or cell magic: {s[:60]!r}")
                clean_lines.append("pass")
            elif s.startswith("%"):
                if not s.startswith(SAFE_MAGICS):
                    found.append(f"cell {idx}: magic command: {s[:60]!r}")
                clean_lines.append("pass")
            else:
                clean_lines.append(line)
        code = "\n".join(clean_lines)
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            found.append(f"cell {idx}: syntax error line {e.lineno}: {e.msg}")
            continue
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module.split(".")[0]]
            for m in mods:
                if m in BANNED_MODULES:
                    found.append(f"cell {idx}: imports {m!r}")
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                    and node.value.id == "os" and node.attr in BANNED_OS_ATTRS:
                found.append(f"cell {idx}: uses os.{node.attr}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in BANNED_CALLS:
                found.append(f"cell {idx}: calls {node.func.id}()")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if re.search(r"https?://|ftp://", node.value):
                    found.append(f"cell {idx}: contains a URL string")
    return found


def check_contract(cells: list[tuple[int, str]]) -> list[str]:
    allsrc = "\n".join(s for _, s in cells)
    w: list[str] = []
    if not re.search(r"seed\s*\(", allsrc) and "default_rng" not in allsrc and "RandomState" not in allsrc:
        w.append("no random seed found (np.random.seed(0), default_rng(0), or torch.manual_seed(0))")
    if "print(" not in allsrc:
        w.append("no print(): the evaluation must print at least one numeric metric")
    if not re.search(r"\bPASS\b|\bFAIL\b", allsrc):
        w.append("no PASS/FAIL line: print whether the spec's pass_condition held")
    if "plt.show()" not in allsrc:
        w.append("no plt.show(): end the figure cell with it")
    if "xlabel" not in allsrc or "ylabel" not in allsrc:
        w.append("figure is missing xlabel/ylabel")
    if re.search(r"pip install|conda install", allsrc):
        w.append("notebook installs packages; remove it and report the missing dependency instead")
    if re.search(r"\.cuda\(|device\(['\"]cuda['\"]\)", allsrc):
        w.append("requires CUDA; the contract is CPU only")
    n = len(allsrc.splitlines())
    if n > 300:
        w.append(f"{n} lines of code; the target is about 200, past that it is a library")
    return w


def check_spec(path: Path) -> tuple[list[str], list[str]]:
    block: list[str] = []
    warn: list[str] = []
    try:
        spec = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        return [f"spec is not valid JSON: {e}"], []
    if not isinstance(spec, dict):
        return ["spec must be a JSON object"], []
    for k in SPEC_KEYS:
        if k not in spec or spec[k] in ("", None, [], {}):
            block.append(f"spec is missing or empty: {k}")
    fig = spec.get("key_figure_description", "")
    if isinstance(fig, str) and 0 < len(fig) < 120:
        warn.append("key_figure_description is short; name the axes, the curves and which should sit above which")
    for k in ("conventions", "pass_condition"):
        if not spec.get(k):
            warn.append(f"spec has no '{k}' (recommended: symbol conventions, and a numeric pass condition)")
    return block, warn


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--notebook", type=Path)
    ap.add_argument("--spec", type=Path)
    args = ap.parse_args()
    if not args.notebook and not args.spec:
        ap.error("give --notebook and/or --spec")

    blocking: list[str] = []
    warnings: list[str] = []
    if args.notebook:
        if not args.notebook.is_file():
            sys.exit(f"File not found: {args.notebook}")
        try:
            cells = load_cells(args.notebook)
        except Exception as e:
            sys.exit(f"Could not read notebook: {e}")
        blocking += check_security(cells)
        warnings += check_contract(cells)
    if args.spec:
        if not args.spec.is_file():
            sys.exit(f"File not found: {args.spec}")
        b, w = check_spec(args.spec)
        blocking += b
        warnings += w

    print(json.dumps({"blocking": blocking, "warnings": warnings}, indent=2))
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
