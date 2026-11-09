#!/usr/bin/env python3
"""Static checks for a generated notebook and its spec. Run this BEFORE executing.

Usage:
    python lint.py --notebook prototype.ipynb [--spec spec.json]
    python lint.py --spec spec.json
    python lint.py --notebook prototype.ipynb --allow-module seaborn

Prints JSON: {"blocking": [...], "warnings": [...]} and exits 1 if anything is blocking.

Blocking means code a notebook made from an untrusted paper must not contain. The
check is an ALLOW-LIST: the notebook may import only math, data and plotting modules,
and may not use dynamic attribute tricks (getattr, vars, dunder access), shell escapes,
file or network entry points, or IPython internals. A reproduction notebook needs none
of that.

Warnings are contract gaps (seeds, a printed metric, PASS/FAIL, labelled axes).

THIS IS NOT A SANDBOX. A static check raises the bar and catches the obvious and the
lazy. It cannot stop a determined attacker, so for papers you do not trust, run the
notebook in a container or VM, and read the generated code yourself.
Needs only the standard library; uses nbformat when installed so it sees exactly the
notebook the runner will execute.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ALLOWED_MODULES = {
    "numpy", "scipy", "matplotlib", "sklearn", "torch", "pandas", "math", "cmath", "random",
    "time", "collections", "itertools", "functools", "operator", "typing", "dataclasses",
    "statistics", "heapq", "bisect", "copy", "warnings", "enum", "abc", "numbers",
    "fractions", "decimal", "string", "textwrap", "contextlib", "re", "__future__",
}
BANNED_SUBMODULES = (
    "scipy.io", "scipy.misc", "numpy.ctypeslib", "numpy.f2py", "numpy.lib.npyio",
    "torch.hub", "torch.utils.cpp_extension", "torch.utils.model_zoo", "torch.utils.bottleneck",
    "torchvision.datasets", "torchvision.io", "pandas.io", "matplotlib.cbook",
)
BANNED_NAMES = {
    "eval", "exec", "compile", "__import__", "open", "input", "getattr", "setattr", "delattr",
    "vars", "globals", "locals", "get_ipython", "breakpoint", "help", "exit", "quit",
    "__builtins__", "__loader__", "__spec__",
}
BANNED_DUNDERS = {
    "__import__", "__builtins__", "__globals__", "__code__", "__class__", "__bases__",
    "__subclasses__", "__mro__", "__dict__", "__getattribute__", "__loader__", "__spec__",
    "__closure__", "__reduce__", "__reduce_ex__", "__self__", "__func__", "__traceback__",
}
# Attributes that are module handles or file/network entry points, whatever object they hang
# off. OS-level function names (remove, kill, walk, system...) are not listed: the modules
# that own them cannot be imported, and the handles to reach them (os, sys, io, ...) are banned.
BANNED_ATTR_EXACT = {
    "os", "sys", "io", "builtins", "posix", "nt", "subprocess", "ctypes", "ctypeslib", "f2py",
    "pty", "importlib", "npyio", "joblib", "environ", "get_ipython",
    "load", "loadtxt", "loadmat", "genfromtxt", "fromfile", "fromregex", "memmap", "tofile",
    "save", "savez", "savez_compressed", "savetxt", "savefig", "dump", "imread", "imsave",
    "get_sample_data", "download", "urlopen", "urlretrieve", "DataSource", "rc_file", "get_data_home",
}
BANNED_ATTR_PATTERN = re.compile(
    r"^(fetch_.*|read_.*|to_(csv|pickle|parquet|excel|json|hdf|sql|feather|clipboard|stata|orc)|"
    r"load_files|load_svmlight.*|dump_svmlight.*|load_npz|save_npz)$"
)
SAFE_MAGICS = ("%matplotlib",)
SPEC_KEYS = ["title", "inputs", "outputs", "hyperparameters", "pseudocode", "key_equations",
             "evaluation_dataset", "toy_dataset_suggestion", "key_figure_description",
             "conventions", "pass_condition", "notes"]


def cells_from_notebook(path: Path) -> list[tuple[int, str]]:
    """Return (index, source) for code cells, normalised the way the runner will see them."""
    raw = path.read_text(encoding="utf-8-sig")
    try:
        import nbformat
        nb = nbformat.reads(raw, as_version=4)
        return cells_from_nb(nb)
    except ImportError:
        data = json.loads(raw)
        if data.get("nbformat") != 4:
            raise ValueError("unsupported notebook format (need nbformat 4); install nbformat to convert it")
        return cells_from_nb(data)


def cells_from_nb(nb) -> list[tuple[int, str]]:
    out = []
    for i, c in enumerate(nb["cells"]):
        if c.get("cell_type") == "code":
            src = c.get("source", "")
            out.append((i, "".join(src) if isinstance(src, list) else src))
    return out


def _neutralise_magics(src: str, idx: int, found: list[str]) -> str:
    lines = []
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("!") or s.startswith("%%"):
            found.append(f"cell {idx}: shell or cell magic: {s[:60]!r}")
            lines.append("pass")
        elif s.startswith("%"):
            if not s.startswith(SAFE_MAGICS):
                found.append(f"cell {idx}: magic command: {s[:60]!r}")
            lines.append("pass")
        else:
            lines.append(line)
    return "\n".join(lines)


def check_security(cells: list[tuple[int, str]], extra_modules: set[str] | None = None) -> list[str]:
    allowed = ALLOWED_MODULES | (extra_modules or set())
    found: list[str] = []
    for idx, src in cells:
        code = _neutralise_magics(src, idx, found)
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            found.append(f"cell {idx}: syntax error line {e.lineno}: {e.msg}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    _check_module(a.name, idx, allowed, found)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    found.append(f"cell {idx}: relative import")
                    continue
                _check_module(node.module or "", idx, allowed, found)
                for a in node.names:
                    if a.name == "*":
                        found.append(f"cell {idx}: star import (name what you import)")
                    else:
                        _check_attr(a.name, idx, found, how="imports")
            elif isinstance(node, ast.Name):
                if node.id in BANNED_NAMES:
                    found.append(f"cell {idx}: uses {node.id}")
            elif isinstance(node, ast.Attribute):
                _check_attr(node.attr, idx, found, how="uses")
            elif isinstance(node, ast.keyword) and node.arg == "download":
                found.append(f"cell {idx}: passes download=")
    return sorted(set(found))


def _check_module(name: str, idx: int, allowed: set[str], found: list[str]) -> None:
    top = name.split(".")[0]
    if top not in allowed:
        found.append(f"cell {idx}: imports {name!r}, which is not on the allow-list")
        return
    for banned in BANNED_SUBMODULES:
        if name == banned or name.startswith(banned + "."):
            found.append(f"cell {idx}: imports {name!r}, which reads files or the network")


def _check_attr(attr: str, idx: int, found: list[str], how: str) -> None:
    if attr in BANNED_DUNDERS or attr in BANNED_ATTR_EXACT or BANNED_ATTR_PATTERN.match(attr):
        found.append(f"cell {idx}: {how} '{attr}' (file, network, process or dynamic-access entry point)")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def check_contract(cells: list[tuple[int, str]]) -> list[str]:
    w: list[str] = []
    seeded = printed = verdict = shown = xl = yl = False
    urls = False
    total_lines = 0
    for idx, src in cells:
        total_lines += len(src.splitlines())
        if re.search(r"pip install|conda install", src):
            w.append(f"cell {idx}: installs packages; report the missing dependency instead")
        try:
            tree = ast.parse(_neutralise_magics(src, idx, []))
        except SyntaxError:
            continue
        docs = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
                if name in ("seed", "manual_seed", "default_rng", "RandomState", "Generator"):
                    seeded = True
                if name == "print":
                    printed = True
                if name == "show":
                    shown = True
                if name in ("xlabel", "set_xlabel"):
                    xl = True
                if name in ("ylabel", "set_ylabel"):
                    yl = True
                if name == "cuda":
                    w.append(f"cell {idx}: calls .cuda(); the contract is CPU only")
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                if re.search(r"\bPASS\b|\bFAIL\b", node.value):
                    verdict = True
                if re.search(r"https?://|ftp://", node.value):
                    urls = True
    if not seeded:
        w.append("no random seed call found (np.random.seed(0), default_rng(0) or torch.manual_seed(0))")
    if not printed:
        w.append("no print(): the evaluation must print at least one numeric metric")
    if not verdict:
        w.append("no PASS/FAIL line: print whether the spec's pass_condition held")
    if not shown:
        w.append("no plt.show(): end the figure cell with it")
    if not (xl and yl):
        w.append("figure is missing xlabel/ylabel")
    if urls:
        w.append("a string constant contains a URL (fine in a comment, but a notebook must not fetch anything)")
    if total_lines > 300:
        w.append(f"{total_lines} lines of code; the target is about 200, past that it is a library")
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
    return block, warn


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--notebook", type=Path)
    ap.add_argument("--spec", type=Path)
    ap.add_argument("--allow-module", action="append", default=[],
                    help="extra top-level module to permit (repeatable). Only for modules you have read.")
    args = ap.parse_args()
    if not args.notebook and not args.spec:
        ap.error("give --notebook and/or --spec")

    blocking: list[str] = []
    warnings: list[str] = []
    if args.notebook:
        if not args.notebook.is_file():
            sys.exit(f"File not found: {args.notebook}")
        try:
            cells = cells_from_notebook(args.notebook)
        except Exception as e:
            sys.exit(f"Could not read notebook: {e}")
        blocking += check_security(cells, set(args.allow_module))
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
