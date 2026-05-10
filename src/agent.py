"""Agent orchestrator + CLI for paper-to-prototype."""
from __future__ import annotations

import argparse
import json
import os
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
    # Running as a top-level script: add repo root to sys.path and use
    # absolute imports.
    _REPO_ROOT = Path(__file__).resolve().parent.parent
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from src.tools import pdf_reader, extractor, codegen, executor  # type: ignore
else:
    from .tools import pdf_reader, extractor, codegen, executor


DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")


def _make_client():
    try:
        from anthropic import Anthropic
    except ImportError as e:
        raise SystemExit("anthropic SDK not installed. `pip install anthropic`.") from e
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set. Put it in your env or .env file.")
    return Anthropic()


class PaperAgent:
    def __init__(self, client=None, model: str = DEFAULT_MODEL,
                 max_iters: int = 5, timeout: int = 300):
        self.client = client or _make_client()
        self.model = model
        self.max_iters = max_iters
        self.timeout = timeout
        self._t0: Optional[float] = None

    def _log(self, log_path: Path, event: dict) -> None:
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        event = {"ts": ts, **event}
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, default=str) + "\n")
        # Also print a human-friendly line to stderr so the user sees live progress.
        stage = event.get("stage", "?")
        extras = {k: v for k, v in event.items() if k not in ("ts", "stage")}
        extra_str = " ".join(f"{k}={v}" for k, v in extras.items())
        elapsed = ""
        if self._t0 is not None:
            elapsed = f" [+{time.monotonic() - self._t0:6.1f}s]"
        print(f"[agent]{elapsed} {stage}" + (f"  {extra_str}" if extra_str else ""),
              file=sys.stderr, flush=True)

    def run(self, pdf_path: Path, focus: Optional[str], output_dir: Path,
            no_execute: bool = False, overwrite: bool = False) -> dict:
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)
        # Default: write into a unique timestamped subfolder so successive runs
        # don't clobber each other. ``overwrite=True`` keeps the legacy behavior
        # of writing directly into ``output_dir``.
        if not overwrite:
            run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            output_dir = output_dir / run_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Maintain a "latest" pointer next to the timestamped runs so tooling
        # (and humans) can find the most recent artifacts without listing dirs.
        if not overwrite:
            try:
                (output_dir.parent / "latest.txt").write_text(
                    output_dir.name, encoding="utf-8"
                )
            except OSError:
                pass

        log_path = output_dir / "agent_log.jsonl"
        self._t0 = time.monotonic()
        print(f"[agent] starting  pdf={pdf_path}  output_dir={output_dir}  model={self.model}",
              file=sys.stderr, flush=True)

        # 1) PDF -> text (+ figures best-effort)
        self._log(log_path, {"stage": "pdf_read", "pdf": str(pdf_path)})
        paper = pdf_reader.extract_paper(
            pdf_path, focus=focus, figures_dir=output_dir / "paper_figures"
        )

        # 2) Extract structured spec
        self._log(log_path, {"stage": "extract_spec", "focus": focus})
        spec = extractor.extract_spec(paper, self.client, focus=focus, model=self.model)
        (output_dir / "spec.json").write_text(
            json.dumps(spec, indent=2), encoding="utf-8"
        )

        # 3) First codegen
        self._log(log_path, {"stage": "codegen_initial"})
        cells = codegen.generate_cells(spec, self.client, model=self.model)
        nb_path = output_dir / "prototype.ipynb"
        codegen.build_notebook(cells, nb_path)

        if no_execute:
            self._log(log_path, {"stage": "skip_execute"})
            return {
                "status": "generated",
                "spec": spec,
                "notebook": str(nb_path),
                "iterations": 0,
            }

        # 4) Execute / fix loop
        result = None
        iteration = 0
        for i in range(self.max_iters):
            iteration = i + 1
            self._log(log_path, {"stage": "execute", "iter": iteration})
            result = executor.execute_notebook(nb_path, timeout=self.timeout)
            if result.success:
                self._log(log_path, {"stage": "execute_ok", "iter": iteration})
                break
            self._log(log_path, {
                "stage": "execute_error",
                "iter": iteration,
                "error_name": result.error_name,
                "error_value": result.error_value,
            })
            if i == self.max_iters - 1:
                break
            try:
                cells = codegen.fix_cells(cells, result.to_dict(), spec, self.client, model=self.model)
                codegen.build_notebook(cells, nb_path)
            except Exception as e:  # codegen failure
                self._log(log_path, {"stage": "fixer_failed", "error": str(e)})
                break

        # 5) Extract figures + write reproduction report
        self._log(log_path, {"stage": "extract_figures"})
        figs = executor.extract_figure_outputs(nb_path, output_dir / "figures")
        self._log(log_path, {"stage": "write_report", "figures": len(figs)})
        write_reproduction_md(
            spec=spec,
            exec_result=result,
            figure_paths=figs,
            iterations=iteration,
            model=self.model,
            out_path=output_dir / "REPRODUCTION.md",
        )
        final_status = "ok" if (result and result.success) else "failed"
        self._log(log_path, {"stage": "done", "status": final_status, "iterations": iteration})

        return {
            "status": final_status,
            "iterations": iteration,
            "notebook": str(nb_path),
            "figures": [str(p) for p in figs],
            "spec": spec,
            "error": None if (result and result.success) else (result.to_dict() if result else None),
        }


def write_reproduction_md(spec: dict, exec_result, figure_paths, iterations: int,
                          model: str, out_path: Path) -> Path:
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

    fig_block = ""
    if figure_paths:
        fig_block = "\n".join(
            f"![figure {i + 1}]({Path(p).relative_to(out_path.parent).as_posix()})"
            for i, p in enumerate(figure_paths)
        )
    else:
        fig_block = "_No figures were captured from the executed notebook._"

    hp = spec.get("hyperparameters", {})
    hp_block = (
        "\n".join(f"- `{k}` = `{v}`" for k, v in hp.items())
        if isinstance(hp, dict) and hp else "- (none specified)"
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
- **Iterations used:** {iterations}
- **Final status:** {"success" if success else "failure"}
- **Model:** `{model}`
"""
    out_path.write_text(md, encoding="utf-8")
    return out_path


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="paper-to-prototype",
        description="Turn an ML paper PDF into a runnable PyTorch notebook.",
    )
    p.add_argument("pdf_path", type=Path, help="Path to the paper PDF.")
    p.add_argument("--focus", type=str, default=None,
                   help="Optional section heading or keyword to focus on (e.g., 'Section 3').")
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
                   help="Write directly into --output-dir instead of a unique "
                        "timestamped subfolder (default: timestamped).")
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

