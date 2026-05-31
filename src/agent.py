"""Agent orchestrator + CLI for paper-to-prototype."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Support BOTH `python -m src` (package import) and `python src/agent.py`
# (direct script execution from IntelliJ's green "Run" button).
if __package__ in (None, ""):
    _REPO_ROOT = Path(__file__).resolve().parent.parent
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from src.tools import pdf_reader, extractor, codegen, executor  # type: ignore
else:
    from .tools import pdf_reader, extractor, codegen, executor


DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

# ── Import-error detection ────────────────────────────────────────────────────
# Patterns that indicate a missing package rather than a logic bug.
_IMPORT_ERROR_PATTERNS = [
    re.compile(r"ModuleNotFoundError: No module named '([^']+)'"),
    re.compile(r"ImportError: cannot import name .+ from '([^']+)'"),
    re.compile(r"ImportError: No module named '([^']+)'"),
]

def _extract_missing_package(error_value: str) -> Optional[str]:
    """Return the pip-installable package name from an import traceback, or None."""
    for pat in _IMPORT_ERROR_PATTERNS:
        m = pat.search(error_value or "")
        if m:
            # e.g. "sklearn.linear_model" → "scikit-learn" needs special casing;
            # for most packages the top-level name is the pip name.
            raw = m.group(1).split(".")[0]
            return _PIP_NAME_MAP.get(raw, raw)
    return None

# Common cases where the import name differs from the pip package name.
_PIP_NAME_MAP = {
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "attr": "attrs",
    "dateutil": "python-dateutil",
    "magic": "python-magic",
}

def _pip_install(package: str) -> tuple[bool, str]:
    """Run `pip install <package>` and return (success, output)."""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", package],
        capture_output=True, text=True,
    )
    return result.returncode == 0, result.stdout + result.stderr


# ── Client + token accounting ────────────────────────────────────────────────

def _make_client():
    try:
        from anthropic import Anthropic
    except ImportError as e:
        raise SystemExit("anthropic SDK not installed. `pip install anthropic`.") from e
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set. Put it in your env or .env file.")
    return Anthropic()


class TokenCounter:
    """Accumulates input/output tokens across all Claude calls in a run."""

    def __init__(self):
        self.input_tokens: int = 0
        self.output_tokens: int = 0

    def record(self, response) -> None:
        """Accept an Anthropic Message response object and add its token counts."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self.input_tokens += getattr(usage, "input_tokens", 0)
        self.output_tokens += getattr(usage, "output_tokens", 0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


# ── Agent ────────────────────────────────────────────────────────────────────

class PaperAgent:
    def __init__(self, client=None, model: str = DEFAULT_MODEL,
                 max_iters: int = 5, timeout: int = 300):
        self.client = client or _make_client()
        self.model = model
        self.max_iters = max_iters
        self.timeout = timeout
        self._t0: Optional[float] = None
        self._tokens = TokenCounter()

    def _log(self, log_path: Path, event: dict) -> None:
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        event = {"ts": ts, **event}
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, default=str) + "\n")
        stage = event.get("stage", "?")
        extras = {k: v for k, v in event.items() if k not in ("ts", "stage")}
        extra_str = " ".join(f"{k}={v}" for k, v in extras.items())
        elapsed = ""
        if self._t0 is not None:
            elapsed = f" [+{time.monotonic() - self._t0:6.1f}s]"
        print(f"[agent]{elapsed} {stage}" + (f"  {extra_str}" if extra_str else ""),
              file=sys.stderr, flush=True)

    def _call_extractor(self, paper, focus):
        """Wrap extractor so we can intercept the raw response for token counting."""
        # extractor.extract_spec returns the parsed spec dict; to count tokens we
        # need the raw response.  We patch this by relying on extractor exposing
        # an optional `_last_response` module-level variable, or fall back to
        # calling the SDK directly if the module doesn't support it yet.
        spec = extractor.extract_spec(paper, self.client, focus=focus, model=self.model)
        _maybe_count(self._tokens, extractor)
        return spec

    def _call_codegen(self, spec):
        cells = codegen.generate_cells(spec, self.client, model=self.model)
        _maybe_count(self._tokens, codegen)
        return cells

    def _call_fixer(self, cells, exec_result_dict, spec):
        cells = codegen.fix_cells(cells, exec_result_dict, spec, self.client, model=self.model)
        _maybe_count(self._tokens, codegen)
        return cells

    def run(self, pdf_path: Path, focus: Optional[str], output_dir: Path,
            no_execute: bool = False, overwrite: bool = False) -> dict:
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)

        if not overwrite:
            run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            output_dir = output_dir / run_id
        output_dir.mkdir(parents=True, exist_ok=True)

        if not overwrite:
            try:
                (output_dir.parent / "latest.txt").write_text(
                    output_dir.name, encoding="utf-8"
                )
            except OSError:
                pass

        log_path = output_dir / "agent_log.jsonl"
        self._t0 = time.monotonic()
        self._tokens = TokenCounter()  # reset for each run
        wall_start = time.monotonic()

        print(f"[agent] starting  pdf={pdf_path}  output_dir={output_dir}  model={self.model}",
              file=sys.stderr, flush=True)

        # 1) PDF → text + figures
        self._log(log_path, {"stage": "pdf_read", "pdf": str(pdf_path)})
        paper = pdf_reader.extract_paper(
            pdf_path, focus=focus, figures_dir=output_dir / "paper_figures"
        )

        # 2) Extract structured spec
        self._log(log_path, {"stage": "extract_spec", "focus": focus})
        spec = self._call_extractor(paper, focus)
        (output_dir / "spec.json").write_text(
            json.dumps(spec, indent=2), encoding="utf-8"
        )

        # 3) First codegen
        self._log(log_path, {"stage": "codegen_initial"})
        cells = self._call_codegen(spec)
        nb_path = output_dir / "prototype.ipynb"
        codegen.build_notebook(cells, nb_path)

        if no_execute:
            self._log(log_path, {"stage": "skip_execute"})
            return {
                "status": "generated",
                "spec": spec,
                "notebook": str(nb_path),
                "iterations": 0,
                "tokens": self._tokens.to_dict(),
                "wall_seconds": round(time.monotonic() - wall_start, 1),
            }

        # 4) Execute / fix loop
        result = None
        iteration = 0
        success_iteration: Optional[int] = None  # which iter produced a passing run
        auto_installs: list[str] = []           # packages we pip-installed mid-loop

        for i in range(self.max_iters):
            iteration = i + 1
            self._log(log_path, {"stage": "execute", "iter": iteration})
            result = executor.execute_notebook(nb_path, timeout=self.timeout)

            if result.success:
                success_iteration = iteration
                self._log(log_path, {"stage": "execute_ok", "iter": iteration})
                break

            error_name = result.error_name or ""
            error_value = result.error_value or ""

            self._log(log_path, {
                "stage": "execute_error",
                "iter": iteration,
                "error_name": error_name,
                "error_value": error_value,
            })

            if i == self.max_iters - 1:
                break  # no fixer pass on the last iteration

            # ── Auto-install missing packages before burning a fix iteration ──
            if "ImportError" in error_name or "ModuleNotFoundError" in error_name:
                package = _extract_missing_package(error_value)
                if package and package not in auto_installs:
                    self._log(log_path, {"stage": "auto_install", "package": package,
                                         "iter": iteration})
                    ok, pip_out = _pip_install(package)
                    if ok:
                        auto_installs.append(package)
                        self._log(log_path, {"stage": "auto_install_ok",
                                             "package": package})
                        # Re-run the same notebook without consuming a fix iteration.
                        continue
                    else:
                        self._log(log_path, {"stage": "auto_install_failed",
                                             "package": package,
                                             "pip_output": pip_out[:400]})

            # ── Normal fixer pass ─────────────────────────────────────────────
            try:
                cells = self._call_fixer(cells, result.to_dict(), spec)
                codegen.build_notebook(cells, nb_path)
            except Exception as e:
                self._log(log_path, {"stage": "fixer_failed", "error": str(e)})
                break

        # 5) Extract figures + write report
        self._log(log_path, {"stage": "extract_figures"})
        figs = executor.extract_figure_outputs(nb_path, output_dir / "figures")

        wall_seconds = round(time.monotonic() - wall_start, 1)
        self._log(log_path, {"stage": "write_report", "figures": len(figs)})
        write_reproduction_md(
            spec=spec,
            exec_result=result,
            figure_paths=figs,
            iterations=iteration,
            success_iteration=success_iteration,
            model=self.model,
            tokens=self._tokens.to_dict(),
            wall_seconds=wall_seconds,
            auto_installs=auto_installs,
            out_path=output_dir / "REPRODUCTION.md",
        )

        final_status = "ok" if (result and result.success) else "failed"
        self._log(log_path, {
            "stage": "done",
            "status": final_status,
            "iterations": iteration,
            "success_iteration": success_iteration,
            "wall_seconds": wall_seconds,
            **self._tokens.to_dict(),
        })

        return {
            "status": final_status,
            "iterations": iteration,
            "success_iteration": success_iteration,
            "notebook": str(nb_path),
            "figures": [str(p) for p in figs],
            "spec": spec,
            "tokens": self._tokens.to_dict(),
            "wall_seconds": wall_seconds,
            "auto_installs": auto_installs,
            "error": None if (result and result.success) else (
                result.to_dict() if result else None
            ),
        }


def _maybe_count(counter: TokenCounter, module) -> None:
    """If the tool module stores its last raw response, record its token usage."""
    resp = getattr(module, "_last_response", None)
    if resp is not None:
        counter.record(resp)


# ── Reproduction report ───────────────────────────────────────────────────────

def write_reproduction_md(
        spec: dict,
        exec_result,
        figure_paths,
        iterations: int,
        success_iteration: Optional[int],
        model: str,
        tokens: dict,
        wall_seconds: float,
        auto_installs: list[str],
        out_path: Path,
) -> Path:
    title = spec.get("title", "(unknown paper)")
    success = bool(exec_result and exec_result.success)
    status = "✅ Notebook executed successfully." if success else "❌ Notebook failed to execute."

    err_block = ""
    if not success and exec_result is not None:
        err_block = (
            "\n### Final error\n"
            f"- **Type:** `{exec_result.error_name}`\n"
            f"- **Message:** {exec_result.error_value}\n"
        )

    fig_block = (
        "\n".join(
            f"![figure {i + 1}]({Path(p).relative_to(out_path.parent).as_posix()})"
            for i, p in enumerate(figure_paths)
        )
        if figure_paths
        else "_No figures were captured from the executed notebook._"
    )

    hp = spec.get("hyperparameters", {})
    hp_block = (
        "\n".join(f"- `{k}` = `{v}`" for k, v in hp.items())
        if isinstance(hp, dict) and hp
        else "- (none specified)"
    )

    iter_detail = (
        f"Succeeded on iteration **{success_iteration}** of {iterations}."
        if success and success_iteration
        else f"All {iterations} iteration(s) attempted; notebook did not pass."
    )

    install_block = (
        "- Auto-installed packages: " + ", ".join(f"`{p}`" for p in auto_installs)
        if auto_installs
        else "- No packages were auto-installed during the run."
    )

    md = f"""# Reproduction Report — {title}

{status}

## Paper
- **Title:** {title}
- **Original evaluation dataset:** {spec.get("evaluation_dataset", "n/a")}
- **Original claim / what we're reproducing:**
{spec.get("key_figure_description", "n/a")}

## Toy reproduction setup
- **Toy dataset:** {spec.get("toy_dataset_suggestion", "n/a")}
- **Hyperparameters used (toy):**
{hp_block}

## Result
{fig_block}

See `prototype.ipynb` for the printed numeric metric and full output.
{err_block}
## Gap analysis
This is a **toy** reproduction. Expected gaps vs. the original paper:
- Smaller dataset and fewer training steps; absolute metrics will not match.
- Model is scaled down for laptop CPU runtime (~2 min budget).
- Goal: reproduce the qualitative *trend* shown in the key figure, not SOTA numbers.
- Notes from the spec: {spec.get("notes", "n/a")}

## Agent run metadata
| Field | Value |
|---|---|
| Status | {"success" if success else "failure"} |
| Iterations used | {iterations} |
| {iter_detail} | |
| Wall-clock time | {wall_seconds}s |
| Total tokens | {tokens.get("total_tokens", "n/a")} |
| Input tokens | {tokens.get("input_tokens", "n/a")} |
| Output tokens | {tokens.get("output_tokens", "n/a")} |
| Model | `{model}` |

### Auto-install log
{install_block}
"""
    out_path.write_text(md, encoding="utf-8")
    return out_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="paper-to-prototype",
        description="Turn an ML paper PDF into a runnable PyTorch notebook.",
    )
    p.add_argument("pdf_path", type=Path, help="Path to the paper PDF.")
    p.add_argument("--focus", type=str, default=None,
                   help="Optional section heading or keyword to focus on.")
    p.add_argument("--output-dir", type=Path, default=None,
                   help="Output directory (default: ./output/<pdf-stem>/).")
    p.add_argument("--max-iters", type=int, default=5,
                   help="Max generate→run→fix iterations (default: 5).")
    p.add_argument("--model", type=str, default=DEFAULT_MODEL,
                   help=f"Anthropic model id (default: {DEFAULT_MODEL}).")
    p.add_argument("--timeout", type=int, default=300,
                   help="Per-notebook execution timeout in seconds.")
    p.add_argument("--no-execute", action="store_true",
                   help="Generate spec + notebook but skip the execution loop.")
    p.add_argument("--overwrite", action="store_true",
                   help="Write directly into --output-dir (no timestamped subfolder).")
    args = p.parse_args(argv)

    if not args.pdf_path.exists():
        print(f"error: PDF not found: {args.pdf_path}", file=sys.stderr)
        return 2

    output_dir = args.output_dir or (Path("output") / args.pdf_path.stem)
    agent = PaperAgent(model=args.model, max_iters=args.max_iters, timeout=args.timeout)
    summary = agent.run(
        pdf_path=args.pdf_path,
        focus=args.focus,
        output_dir=output_dir,
        no_execute=args.no_execute,
        overwrite=args.overwrite,
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "spec"}, indent=2, default=str))
    return 0 if summary.get("status") in ("ok", "generated") else 1


if __name__ == "__main__":
    raise SystemExit(main())