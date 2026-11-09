#!/usr/bin/env python3
"""Execute a notebook top to bottom and report the result as JSON.

Usage:
    python run_notebook.py prototype.ipynb --figures-dir figures
    python run_notebook.py prototype.ipynb --timeout 120 --total-timeout 180
    python run_notebook.py --check-env

What it does, and why:
  * Runs the notebook with THIS interpreter (sys.executable), so the packages you
    checked with --check-env are the packages the notebook sees.
  * Refuses to run notebooks that fail the security checks in lint.py (shell escapes,
    network or process libraries, env access, file access, imports outside the allow-list).
    --allow-module NAME permits one extra module you have read. --allow-unsafe skips the
    check and is for code you wrote yourself, never for code derived from a paper.
  * Gives the kernel only a short allow-list of environment variables (PATH, HOME, locale,
    temp dirs, thread settings, matplotlib and Python settings). Everything else, including
    anything that looks like a key, token or credential, is dropped.
  * None of this is a sandbox. For papers you do not trust, run inside a container or VM.
  * Enforces a per-cell timeout AND a total budget (default 180s).
  * Always prints one JSON object and saves the notebook with whatever outputs it got.
    Exit code is 0 on success, 1 on failure.

JSON fields: success, notebook, runtime_seconds, error_cell_index, error_name,
error_value, traceback, figures, warnings.
Requires: nbformat, nbclient, ipykernel.
"""
from __future__ import annotations

import argparse
import atexit
import base64
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_KEEP = {
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LANGUAGE", "TERM", "TZ", "TMPDIR", "TEMP", "TMP",
    "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV", "PYTHONPATH", "PYTHONHASHSEED", "PYTHONIOENCODING",
    "PYTHONUTF8", "MPLBACKEND", "MPLCONFIGDIR", "JUPYTER_PATH", "JUPYTER_CONFIG_DIR", "JUPYTER_DATA_DIR",
    "JUPYTER_RUNTIME_DIR", "IPYTHONDIR", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT",
    "USERPROFILE", "APPDATA", "LOCALAPPDATA", "OS", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS",
    "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_RUNTIME_DIR", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH",
}
ENV_KEEP_PREFIXES = ("LC_", "OMP_", "MKL_", "OPENBLAS_", "NUMEXPR_", "VECLIB_", "KMP_")


class BudgetExhausted(Exception):
    pass


def have(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def check_env() -> int:
    required = ["nbformat", "nbclient", "ipykernel", "numpy", "matplotlib"]
    missing = [n for n in required if not have(n)]
    pdf_reader = [n for n in ("pdfplumber", "pypdf") if have(n)]
    has_torch, has_sklearn = have("torch"), have("sklearn")
    report = {
        "python": sys.version.split()[0],
        "interpreter": sys.executable,
        "missing_required": missing,
        "pdf_reader": pdf_reader or "NONE: pip install pdfplumber",
        "torch": has_torch,
        "scikit_learn": has_sklearn,
        "backend_for_notebooks": ("torch" if has_torch else
                                  "numpy/scikit-learn (torch not installed; this is fine)"
                                  if has_sklearn else
                                  "numpy only: also install scikit-learn"),
        "install": ("pip install " + " ".join(
            missing + (["scikit-learn"] if not has_sklearn and not has_torch else [])
            + ([] if pdf_reader else ["pdfplumber"]))) if (missing or not pdf_reader
                                                           or (not has_sklearn and not has_torch)) else None,
        "note": "torch is optional. Install it only if the paper needs it.",
    }
    print(json.dumps(report, indent=2))
    return 1 if missing else 0


def strip_ansi(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def restrict_environment() -> int:
    """Keep only allow-listed variables. Returns how many were dropped."""
    keep = {k: v for k, v in os.environ.items()
            if k.upper() in ENV_KEEP or k.upper().startswith(ENV_KEEP_PREFIXES)}
    dropped = len(os.environ) - len(keep)
    os.environ.clear()
    os.environ.update(keep)
    return dropped


def register_kernel_for_this_python() -> str:
    """Point a throwaway kernelspec at sys.executable and make Jupyter find it."""
    tmp = Path(tempfile.mkdtemp(prefix="p2p_kernel_"))
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    kdir = tmp / "kernels" / "p2p_runner"
    kdir.mkdir(parents=True)
    (kdir / "kernel.json").write_text(json.dumps({
        "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": "p2p_runner", "language": "python",
    }))
    prior = os.environ.get("JUPYTER_PATH", "")
    os.environ["JUPYTER_PATH"] = str(tmp) + (os.pathsep + prior if prior else "")
    return "p2p_runner"


def extract_figures(nb, out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("figure_*.png"):  # no stale figures from a previous run
        old.unlink()
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


def stdout_lines(nb) -> int:
    n = 0
    for cell in nb.cells:
        for out in cell.get("outputs", []) or []:
            if out.get("output_type") == "stream" and out.get("name") == "stdout":
                n += len("".join(out.get("text", "")).splitlines())
    return n


def run(nb, nb_path: Path, timeout: int, total_timeout: int, figures_dir: Path | None,
        kernel_name: str) -> dict:
    import nbformat
    from nbclient import NotebookClient
    from nbclient.exceptions import CellExecutionError, CellTimeoutError, DeadKernelError

    result: dict = {"success": False, "notebook": str(nb_path), "warnings": []}
    client = NotebookClient(
        nb, timeout=timeout, kernel_name=kernel_name, allow_errors=False,
        resources={"metadata": {"path": str(nb_path.parent.resolve())}},
    )
    start = time.time()
    current = None
    budget_limited = False
    try:
        client.reset_execution_trackers()
        with client.setup_kernel():
            for idx, cell in enumerate(nb.cells):
                if cell.get("cell_type") != "code":
                    continue
                remaining = total_timeout - (time.time() - start)
                if remaining <= 0:
                    raise BudgetExhausted(f"used up before cell {idx}")
                client.timeout = max(1, int(min(timeout, remaining)))
                budget_limited = remaining < timeout
                current = idx
                client.execute_cell(cell, idx)
        result["success"] = True
    except (CellTimeoutError, BudgetExhausted) as e:
        why = (f"the total budget of {total_timeout}s ran out (includes kernel start-up)"
               if budget_limited or isinstance(e, BudgetExhausted)
               else f"a cell exceeded the {timeout}s per-cell timeout")
        result.update(error_cell_index=current, error_name="Timeout",
                      error_value=f"{why}. Cut the dataset, epochs or model size.",
                      traceback=strip_ansi(str(e)))
    except CellExecutionError:
        err = next((o for o in nb.cells[current].get("outputs", []) or []
                    if o.get("output_type") == "error"), None) if current is not None else None
        result.update(error_cell_index=current,
                      error_name=(err or {}).get("ename", "CellExecutionError"),
                      error_value=(err or {}).get("evalue", ""),
                      traceback=strip_ansi("\n".join((err or {}).get("traceback", []) or [])))
    except DeadKernelError:
        result.update(error_cell_index=current, error_name="DeadKernelError",
                      error_value="The kernel died (crash, os._exit, or out of memory).")
    except Exception as e:  # keep the JSON contract no matter what
        result.update(error_cell_index=current, error_name=type(e).__name__,
                      error_value=strip_ansi(str(e))[:2000])
    finally:
        result["runtime_seconds"] = round(time.time() - start, 1)
        nbformat.write(nb, str(nb_path))  # keep outputs, including partial ones
        if figures_dir is not None:
            result["figures"] = extract_figures(nb, figures_dir)

    if result["success"]:
        if figures_dir is not None and not result.get("figures"):
            result["warnings"].append("ran cleanly but produced no figure")
        if stdout_lines(nb) == 0:
            result["warnings"].append("ran cleanly but printed nothing: no numeric metric")
        if len(result.get("figures", [])) > 1:
            result["warnings"].append("more than one figure; state which one is the key figure in the report")
    size_mb = nb_path.stat().st_size / 1e6
    if size_mb > 20:
        result["warnings"].append(f"notebook is {size_mb:.0f} MB; cap printed output at about 50 lines")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("notebook", nargs="?", type=Path)
    ap.add_argument("--timeout", type=int, default=120, help="per-cell timeout in seconds (default 120)")
    ap.add_argument("--total-timeout", type=int, default=180, help="whole-notebook budget in seconds (default 180)")
    ap.add_argument("--figures-dir", type=Path, help="save PNG outputs here (old figure_*.png are removed)")
    ap.add_argument("--check-env", action="store_true", help="report the environment and exit")
    ap.add_argument("--allow-module", action="append", default=[],
                    help="permit one extra top-level module in the security check (repeatable)")
    ap.add_argument("--allow-unsafe", action="store_true",
                    help="skip the security check. For code you wrote yourself, never for code from a paper")
    args = ap.parse_args()

    if args.check_env:
        return check_env()
    if args.notebook is None or not args.notebook.is_file():
        sys.exit("Give the path to an existing .ipynb (or use --check-env)")
    missing = [n for n in ("nbformat", "nbclient", "ipykernel") if not have(n)]
    if missing:
        sys.exit("Install the runner:  pip install " + " ".join(missing))

    import nbformat
    try:
        nb = nbformat.read(str(args.notebook), as_version=4)  # parsed once: what is checked is what runs
    except Exception as e:
        sys.exit(f"Could not read notebook: {e}")

    if not args.allow_unsafe:
        sys.path.insert(0, str(HERE))
        import lint
        problems = lint.check_security(lint.cells_from_nb(nb), set(args.allow_module))
        if problems:
            print(json.dumps({
                "success": False, "notebook": str(args.notebook),
                "error_name": "BlockedBySecurityCheck",
                "error_value": "Not executed. Rewrite the notebook without these. Do not bypass the check "
                               "for code that came from a paper.",
                "blocking": problems}, indent=2))
            return 1

    dropped = restrict_environment()
    kernel = register_kernel_for_this_python()
    result = run(nb, args.notebook, args.timeout, args.total_timeout, args.figures_dir, kernel)
    result["env_vars_dropped_for_kernel"] = dropped
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
