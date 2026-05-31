"""Eval harness: run the agent over each input/*/paper.pdf and tally results.

Reads PDFs from ``input/<name>/paper.pdf`` and writes generated artifacts to
``output/<name>/``. A summary is written to ``eval/results.json``.

Enhanced fields per paper entry
--------------------------------
- status              : "ok" | "failed" | "error" | "skipped"
- iterations          : total fix iterations consumed
- success_iteration   : which iteration first produced a passing notebook (int | null)
- wall_seconds        : total wall-clock time for the agent run
- tokens              : {input_tokens, output_tokens, total_tokens}
- auto_installs       : list of packages pip-installed during the run
- figure_score        : SSIM-based similarity between reproduced and paper figures
                        (float 0–1, or null when comparison is not possible)
- error               : error detail dict on failure, null otherwise

Aggregate summary fields
-------------------------
- total_attempted, successful, success_rate  (unchanged)
- avg_iterations        : mean iterations across successful runs
- avg_success_iteration : mean iteration index at which success occurred
- avg_wall_seconds      : mean wall time across all attempted runs
- total_tokens          : cumulative token spend across all runs
- avg_figure_score      : mean SSIM score across runs that have figure outputs
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Optional

# ── Optional SSIM dependency (graceful degradation) ──────────────────────────
try:
    import numpy as np
    from PIL import Image
    from skimage.metrics import structural_similarity as ssim

    _SSIM_AVAILABLE = True
except ImportError:
    _SSIM_AVAILABLE = False

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import PaperAgent  # noqa: E402


def _log(msg: str) -> None:
    print(f"[eval] {msg}", file=sys.stderr, flush=True)


# ── Figure scoring ────────────────────────────────────────────────────────────

def _load_gray(path: Path, size: tuple[int, int] = (256, 256)):
    """Load an image as a normalised grayscale numpy array."""
    img = Image.open(path).convert("L").resize(size, Image.LANCZOS)
    return np.array(img, dtype=np.float32) / 255.0


def _ssim_score(paper_figures_dir: Path, reproduced_figures_dir: Path) -> Optional[float]:
    """
    Return mean SSIM between the first reproduced figure and the first paper
    figure crop.  Returns None when either directory is missing/empty or when
    the SSIM library is not installed.
    """
    if not _SSIM_AVAILABLE:
        return None

    paper_imgs = sorted(paper_figures_dir.glob("*.png")) if paper_figures_dir.exists() else []
    repro_imgs = sorted(reproduced_figures_dir.glob("*.png")) if reproduced_figures_dir.exists() else []

    if not paper_imgs or not repro_imgs:
        return None

    scores: list[float] = []
    for p_img, r_img in zip(paper_imgs, repro_imgs):
        try:
            a = _load_gray(p_img)
            b = _load_gray(r_img)
            score = float(ssim(a, b, data_range=1.0))
            scores.append(score)
        except Exception:
            continue

    return round(sum(scores) / len(scores), 4) if scores else None


# ── Per-paper evaluation ──────────────────────────────────────────────────────

def _run_one(
        sub: Path,
        out_sub: Path,
        idx: int,
        total: int,
        agent_kwargs: dict,
        overwrite: bool,
) -> dict:
    pdf = sub / "paper.pdf"
    entry: dict = {"name": sub.name, "pdf": str(pdf), "output": str(out_sub)}
    prefix = f"[{idx}/{total}] {sub.name}"

    if not pdf.exists():
        _log(f"{prefix}  SKIP  (no paper.pdf)")
        entry.update(status="skipped", reason="no paper.pdf")
        return entry

    _log(f"{prefix}  START  pdf={pdf}  output={out_sub}")
    t0 = time.monotonic()

    try:
        agent = PaperAgent(**agent_kwargs)
        summary = agent.run(
            pdf_path=pdf, focus=None,
            output_dir=out_sub, overwrite=overwrite,
        )

        # Resolve the actual run directory (timestamped subfolder or out_sub).
        run_dir = out_sub
        if not overwrite:
            latest_ptr = out_sub / "latest.txt"
            if latest_ptr.exists():
                run_dir = out_sub / latest_ptr.read_text(encoding="utf-8").strip()

        # SSIM figure comparison
        figure_score = _ssim_score(
            run_dir / "paper_figures",
            run_dir / "figures",
            )

        entry.update(
            status=summary.get("status"),
            iterations=summary.get("iterations"),
            success_iteration=summary.get("success_iteration"),
            wall_seconds=summary.get("wall_seconds", round(time.monotonic() - t0, 1)),
            tokens=summary.get("tokens", {}),
            auto_installs=summary.get("auto_installs", []),
            figure_score=figure_score,
            error=summary.get("error"),
        )

        dur = time.monotonic() - t0
        tokens_total = (summary.get("tokens") or {}).get("total_tokens", "?")
        _log(
            f"{prefix}  DONE   status={entry['status']}  "
            f"iters={entry.get('iterations')}  "
            f"success_iter={entry.get('success_iteration')}  "
            f"tokens={tokens_total}  "
            f"figure_score={figure_score}  "
            f"elapsed={dur:.1f}s"
        )

    except Exception as e:
        dur = time.monotonic() - t0
        entry.update(
            status="error",
            reason=str(e),
            traceback=traceback.format_exc(),
            wall_seconds=round(dur, 1),
        )
        _log(f"{prefix}  ERROR  {type(e).__name__}: {e}  elapsed={dur:.1f}s")

    return entry


# ── Aggregate stats ───────────────────────────────────────────────────────────

def _aggregate(results: list[dict], total_wall: float) -> dict:
    attempted = [r for r in results if r.get("status") not in ("skipped",)]
    ok = [r for r in attempted if r.get("status") == "ok"]

    def _mean(vals):
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    avg_iterations = _mean([r.get("iterations") for r in ok])
    avg_success_iteration = _mean([r.get("success_iteration") for r in ok])
    avg_wall = _mean([r.get("wall_seconds") for r in attempted])

    total_tokens = sum(
        (r.get("tokens") or {}).get("total_tokens", 0) for r in attempted
    )

    figure_scores = [r.get("figure_score") for r in attempted
                     if r.get("figure_score") is not None]
    avg_figure_score = _mean(figure_scores)

    return {
        "total_attempted": len(attempted),
        "successful": len(ok),
        "success_rate": round(len(ok) / len(attempted), 4) if attempted else 0.0,
        "avg_iterations": avg_iterations,
        "avg_success_iteration": avg_success_iteration,
        "avg_wall_seconds": avg_wall,
        "total_wall_seconds": round(total_wall, 1),
        "total_tokens": total_tokens,
        "avg_figure_score": avg_figure_score,
        "ssim_available": _SSIM_AVAILABLE,
        "results": results,
    }


# ── Main evaluate function ────────────────────────────────────────────────────

def evaluate(
        input_dir: Path,
        output_dir: Path,
        max_iters: int = 5,
        timeout: int = 300,
        model: Optional[str] = None,
        overwrite: bool = False,
) -> dict:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not _SSIM_AVAILABLE:
        _log(
            "SSIM scoring disabled — install scikit-image, Pillow, numpy to enable: "
            "pip install scikit-image Pillow numpy"
        )

    agent_kwargs: dict = {"max_iters": max_iters, "timeout": timeout}
    if model:
        agent_kwargs["model"] = model

    subs = sorted(p for p in input_dir.iterdir() if p.is_dir())
    _log(f"discovered {len(subs)} candidate folder(s) under {input_dir}")
    t_total = time.monotonic()

    results: list[dict] = []
    for idx, sub in enumerate(subs, start=1):
        entry = _run_one(
            sub=sub,
            out_sub=output_dir / sub.name,
            idx=idx,
            total=len(subs),
            agent_kwargs=agent_kwargs,
            overwrite=overwrite,
        )
        results.append(entry)

    total_wall = time.monotonic() - t_total
    summary = _aggregate(results, total_wall)

    n_ok = summary["successful"]
    n_total = summary["total_attempted"]
    _log(
        f"FINISHED  attempted={n_total}  ok={n_ok}  "
        f"rate={summary['success_rate']:.0%}  "
        f"avg_iters={summary['avg_iterations']}  "
        f"avg_success_iter={summary['avg_success_iteration']}  "
        f"total_tokens={summary['total_tokens']}  "
        f"avg_figure_score={summary['avg_figure_score']}  "
        f"total_elapsed={total_wall:.1f}s"
    )
    return summary


# ── CLI ───────────────────────────────────────────────────────────────────────

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
    p.add_argument("--overwrite", action="store_true",
                   help="Write directly into output/<name>/ (no timestamped subfolder).")
    args = p.parse_args(argv)

    summary = evaluate(
        args.input_dir, args.output_dir,
        args.max_iters, args.timeout, args.model,
        overwrite=args.overwrite,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Print aggregate without the verbose per-paper list.
    print(json.dumps(
        {k: v for k, v in summary.items() if k != "results"}, indent=2,
    ))
    print(f"\nWrote detailed results to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())