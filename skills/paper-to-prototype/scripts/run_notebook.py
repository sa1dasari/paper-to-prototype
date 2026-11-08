#!/usr/bin/env python3
"""Execute a notebook top to bottom and report the result as JSON.

Usage:
    python run_notebook.py prototype.ipynb                       # run in place
    python run_notebook.py prototype.ipynb --timeout 300 --figures-dir figures
    python run_notebook.py --check-env                           # list missing packages

On success the notebook is saved with outputs and the JSON has "success": true.
On failure it names the first failing cell (0-based index among all cells) with its
traceback, so you can fix the root cause and re-run from the top. Partial outputs
are still saved. Exit code is 0 on success and 1 on failure.
Requires: nbformat, nbclient, ipykernel.
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import re
import sys
import time
from pathlib import Path

REQUIRED = ["nbformat", "nbclient", "ipykernel", "numpy", "matplotlib"]
EXPECTED_BY_NOTEBOOK = ["torch", "sklearn", "torchvision"]


def check_env() -> int:
    def missing(names):
        return [n for n in names if importlib.util.find_spec(n) is None]

    need = missing(REQUIRED)
    soft = missing(EXPECTED_BY_NOTEBOOK)
    pip_name = {"sklearn": "scikit-learn"}
    report = {
        "python": sys.version.split()[0],
        "missing_required": need,
        "missing_expected_by_generated_notebooks": soft,
        "install": "pip install " + " ".join(pip_name.get(n, n) for n in need + soft)
        if need or soft else None,
    }
    print(json.dumps(report, indent=2))
    return 1 if need else 0


def strip_ansi(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def extract_figures(nb, out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    n = 0
    for cell in nb.cells:
        if cell.get("cell_type") != "code":
            continue
        for out in cell.get("outputs", []) or []:
            png = (out.get("data") or {}).get("image/png")
            if png:
                n += 1
                fp = out_dir / f"figure_{n:02d}.png"
                fp.write_bytes(base64.b64decode(png))
                saved.append(str(fp))
    return saved


def run(nb_path: Path, timeout: int, figures_dir: Path | None) -> dict:
    import nbformat
    from nbclient import NotebookClient
    from nbclient.exceptions import CellExecutionError, CellTimeoutError

    nb = nbformat.read(str(nb_path), as_version=4)
    client = NotebookClient(
        nb, timeout=timeout, kernel_name="python3", allow_errors=False,
        resources={"metadata": {"path": str(nb_path.parent.resolve())}},
    )
    result: dict = {"success": False, "notebook": str(nb_path)}
    start = time.time()
    try:
        client.execute()
        result["success"] = True
    except CellTimeoutError as e:
        result.update(error_name="CellTimeoutError",
                      error_value=f"A cell exceeded {timeout}s. Cut the dataset, epochs or model size.",
                      traceback=strip_ansi(str(e)))
    except CellExecutionError:
        for idx, cell in enumerate(nb.cells):
            if cell.get("cell_type") != "code":
                continue
            err = next((o for o in cell.get("outputs", []) or []
                        if o.get("output_type") == "error"), None)
            if err:
                result.update(error_cell_index=idx, error_name=err.get("ename"),
                              error_value=err.get("evalue"),
                              traceback=strip_ansi("\n".join(err.get("traceback", []) or [])))
                break
        else:
            result.update(error_name="UnknownExecutionError",
                          error_value="Execution failed but no error output was captured.")
    result["runtime_seconds"] = round(time.time() - start, 1)

    nbformat.write(nb, str(nb_path))  # keep outputs, including partial ones on failure
    if figures_dir is not None:
        result["figures"] = extract_figures(nb, figures_dir)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("notebook", nargs="?", type=Path)
    ap.add_argument("--timeout", type=int, default=300, help="per-cell timeout in seconds (default 300)")
    ap.add_argument("--figures-dir", type=Path, help="save PNG outputs here")
    ap.add_argument("--check-env", action="store_true", help="report missing packages and exit")
    args = ap.parse_args()

    if args.check_env:
        return check_env()
    if args.notebook is None or not args.notebook.is_file():
        sys.exit("Give the path to an existing .ipynb (or use --check-env)")
    if any(importlib.util.find_spec(n) is None for n in ("nbformat", "nbclient", "ipykernel")):
        sys.exit("Install the runner:  pip install nbformat nbclient ipykernel")

    result = run(args.notebook, args.timeout, args.figures_dir)
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
