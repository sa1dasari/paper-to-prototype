"""Eval harness: run the agent over each examples/*/paper.pdf and tally results."""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

# Make `src` importable when this file is run directly.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import PaperAgent  # noqa: E402


def evaluate(examples_dir: Path, max_iters: int = 5, timeout: int = 300,
             model: str | None = None) -> dict:
    examples_dir = Path(examples_dir)
    results: list[dict] = []
    agent_kwargs = {"max_iters": max_iters, "timeout": timeout}
    if model:
        agent_kwargs["model"] = model

    for sub in sorted(p for p in examples_dir.iterdir() if p.is_dir()):
        pdf = sub / "paper.pdf"
        entry = {"name": sub.name, "pdf": str(pdf)}
        if not pdf.exists():
            entry.update(status="skipped", reason="no paper.pdf")
            results.append(entry)
            continue
        try:
            agent = PaperAgent(**agent_kwargs)
            summary = agent.run(
                pdf_path=pdf, focus=None, output_dir=sub / "generated",
            )
            entry.update(
                status=summary.get("status"),
                iterations=summary.get("iterations"),
            )
        except Exception as e:
            entry.update(status="error", reason=str(e),
                         traceback=traceback.format_exc())
        results.append(entry)

    n_total = sum(1 for r in results if r["status"] not in ("skipped",))
    n_ok = sum(1 for r in results if r["status"] == "ok")
    summary = {
        "total_attempted": n_total,
        "successful": n_ok,
        "success_rate": (n_ok / n_total) if n_total else 0.0,
        "results": results,
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Evaluate paper-to-prototype on examples/.")
    p.add_argument("--examples-dir", type=Path, default=ROOT / "examples")
    p.add_argument("--max-iters", type=int, default=5)
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--model", type=str, default=None)
    p.add_argument("--out", type=Path, default=ROOT / "eval" / "results.json")
    args = p.parse_args(argv)

    summary = evaluate(args.examples_dir, args.max_iters, args.timeout, args.model)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(
        {k: v for k, v in summary.items() if k != "results"}, indent=2,
    ))
    print(f"\nWrote detailed results to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

