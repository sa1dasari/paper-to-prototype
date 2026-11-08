#!/usr/bin/env python3
"""Extract text (and optionally figure pages) from a paper PDF.

Usage:
    python read_pdf.py paper.pdf                    # all pages, text to stdout
    python read_pdf.py paper.pdf --pages 3-6        # page range (1-based)
    python read_pdf.py paper.pdf --figures-dir figs # also save figure images

Text is printed with "=== Page N ===" markers so you can cite pages in the spec.
Uses pdfplumber when installed, otherwise falls back to pypdf.
Figure extraction needs pdfplumber and Pillow.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def parse_pages(spec: str | None, total: int) -> list[int]:
    """'3-6' -> [3,4,5,6]; '2,5-6' -> [2,5,6]. None -> every page. 1-based."""
    if not spec:
        return list(range(1, total + 1))
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a), int(b) + 1))
        elif part:
            pages.append(int(part))
    return [p for p in pages if 1 <= p <= total]


def read_text(pdf_path: Path, pages_spec: str | None) -> list[tuple[int, str]]:
    try:
        import pdfplumber
    except ImportError:
        pdfplumber = None

    if pdfplumber is not None:
        with pdfplumber.open(str(pdf_path)) as pdf:
            wanted = parse_pages(pages_spec, len(pdf.pages))
            # x_tolerance=2 keeps word spacing in PDFs where the default (3) glues words together
            return [(n, pdf.pages[n - 1].extract_text(x_tolerance=2) or "") for n in wanted]

    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("Install pdfplumber or pypdf:  pip install pdfplumber")
    reader = PdfReader(str(pdf_path))
    wanted = parse_pages(pages_spec, len(reader.pages))
    return [(n, reader.pages[n - 1].extract_text() or "") for n in wanted]


_CAPTION = re.compile(r"\b(Figure|Fig\.|Table)\s+\d+", re.IGNORECASE)


def save_figures(pdf_path: Path, out_dir: Path, pages_spec: str | None,
                 resolution: int = 120) -> list[Path]:
    """Save embedded images; for vector-only pages that carry a caption, render the page."""
    import pdfplumber

    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for n in parse_pages(pages_spec, len(pdf.pages)):
            page = pdf.pages[n - 1]
            got_raster = False
            for i, img in enumerate(page.images, start=1):
                try:
                    box = (img["x0"], img["top"], img["x1"], img["bottom"])
                    fp = out_dir / f"page{n:02d}_img{i:02d}.png"
                    page.crop(box).to_image(resolution=resolution).save(str(fp), format="PNG")
                    saved.append(fp)
                    got_raster = True
                except Exception:
                    continue
            if got_raster:
                continue
            if _CAPTION.search(page.extract_text() or ""):
                try:
                    fp = out_dir / f"page{n:02d}_full.png"
                    page.to_image(resolution=resolution).save(str(fp), format="PNG")
                    saved.append(fp)
                except Exception:
                    continue
    return saved


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--pages", help="1-based pages, e.g. '3-6' or '1,4-5'")
    ap.add_argument("--figures-dir", type=Path, help="save figure images here")
    args = ap.parse_args()

    if not args.pdf.is_file():
        sys.exit(f"File not found: {args.pdf}")

    pages = read_text(args.pdf, args.pages)
    for n, text in pages:
        print(f"=== Page {n} ===")
        print(text.strip())
        print()

    if sum(len(t.strip()) for _, t in pages) < 200:
        print("WARNING: almost no text extracted. This may be a scanned PDF; "
              "OCR it first or ask for a text version.", file=sys.stderr)

    if args.figures_dir:
        try:
            saved = save_figures(args.pdf, args.figures_dir, args.pages)
        except ImportError:
            sys.exit("Figure extraction needs pdfplumber and Pillow.")
        print(f"Saved {len(saved)} figure image(s) to {args.figures_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
