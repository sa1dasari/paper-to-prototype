"""Eval harness: run the agent over each input/*/paper.pdf and tally results.

Reads PDFs from ``input/<name>/paper.pdf`` and writes generated artifacts to
``output/<name>/``. A summary is written to ``eval/results.json``.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

# Make `src` importable when this file is run directly.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import PaperAgent  # noqa: E402


def _log(msg: str) -> None:
    print(f"[eval] {msg}", file=sys.stderr, flush=True)


def evaluate(input_dir: Path, output_dir: Path,
             max_iters: int = 5, timeout: int = 300,
             model: str | None = None) -> dict:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    agent_kwargs = {"max_iters": max_iters, "timeout": timeout}
    if model:
        agent_kwargs["model"] = model

    subs = sorted(p for p in input_dir.iterdir() if p.is_dir())
    _log(f"discovered {len(subs)} candidate folder(s) under {input_dir}")
    t_total = time.monotonic()

    for idx, sub in enumerate(subs, start=1):
        pdf = sub / "paper.pdf"
        out_sub = output_dir / sub.name
        entry = {"name": sub.name, "pdf": str(pdf), "output": str(out_sub)}
        prefix = f"[{idx}/{len(subs)}] {sub.name}"

        if not pdf.exists():
            _log(f"{prefix}  SKIP  (no paper.pdf)")
            entry.update(status="skipped", reason="no paper.pdf")
            results.append(entry)
            continue

        _log(f"{prefix}  START  pdf={pdf}  output={out_sub}")
        t0 = time.monotonic()
        try:
            agent = PaperAgent(**agent_kwargs)
            summary = agent.run(
                pdf_path=pdf, focus=None, output_dir=out_sub,
            )
            entry.update(
                status=summary.get("status"),
                iterations=summary.get("iterations"),
            )
            dur = time.monotonic() - t0
            _log(f"{prefix}  DONE   status={entry['status']}  "
                 f"iters={entry.get('iterations')}  elapsed={dur:.1f}s")
        except Exception as e:
            dur = time.monotonic() - t0
            entry.update(status="error", reason=str(e),
                         traceback=traceback.format_exc())
            _log(f"{prefix}  ERROR  {type(e).__name__}: {e}  elapsed={dur:.1f}s")
        results.append(entry)

    n_total = sum(1 for r in results if r["status"] not in ("skipped",))
    n_ok = sum(1 for r in results if r["status"] == "ok")
    summary = {
        "total_attempted": n_total,
        "successful": n_ok,
        "success_rate": (n_ok / n_total) if n_total else 0.0,
        "results": results,
    }
    _log(f"FINISHED  attempted={n_total}  ok={n_ok}  "
         f"rate={summary['success_rate']:.0%}  total_elapsed={time.monotonic() - t_total:.1f}s")
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Evaluate paper-to-prototype on input/.")
    p.add_argument("--input-dir", type=Path, default=ROOT / "input",
                   help="Directory containing <name>/paper.pdf folders.")
    p.add_argument("--output-dir", type=Path, default=ROOT / "output",
                   help="Where per-paper generated artifacts are written.")
    p.add_argument("--max-iters", type=int, default=5)
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--model", type=str, default=None)
    p.add_argument("--out", type=Path, default=ROOT / "eval" / "results.json",
                   help="Path for the aggregated JSON summary.")
    args = p.parse_args(argv)

    summary = evaluate(
        args.input_dir, args.output_dir,
        args.max_iters, args.timeout, args.model,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(
        {k: v for k, v in summary.items() if k != "results"}, indent=2,
    ))
    print(f"\nWrote detailed results to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

