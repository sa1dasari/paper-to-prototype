"""PDF reader: extracts per-page text and embedded figures from a paper PDF."""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Optional

import pdfplumber
from PIL import Image


_SECTION_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)*)\s+([A-Z][A-Za-z0-9 \-:,/&]{2,80})\s*$",
    re.MULTILINE,
)


def extract_text(pdf_path: Path) -> list[str]:
    """Return a list of page strings."""
    pages: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return pages


_CAPTION_RE = re.compile(r"\b(Figure|Table)\s+\d+[:.\s]", re.IGNORECASE)


def extract_figures(pdf_path: Path, out_dir: Path,
                    page_fallback: bool = True,
                    resolution: int = 120) -> list[Path]:
    """Save figure-like images from a PDF to ``out_dir``.

    Strategy:
    1. Crop every embedded raster image (XObject) — works for scanned papers.
    2. If no raster images on a page **and** ``page_fallback`` is true and the
       page text contains a "Figure N" or "Table N" caption, render the whole
       page as PNG. This catches arXiv-style PDFs where figures are vector
       graphics (e.g. word2vec, LoRA).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for pi, page in enumerate(pdf.pages):
            page_no = pi + 1
            page_had_raster = False
            for ii, img in enumerate(page.images):
                try:
                    bbox = (img["x0"], img["top"], img["x1"], img["bottom"])
                    cropped = page.crop(bbox).to_image(resolution=resolution)
                    fp = out_dir / f"page{page_no:02d}_img{ii + 1:02d}.png"
                    cropped.save(str(fp), format="PNG")
                    saved.append(fp)
                    page_had_raster = True
                except Exception:
                    continue
            if page_had_raster or not page_fallback:
                continue
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            if _CAPTION_RE.search(text):
                try:
                    fp = out_dir / f"page{page_no:02d}_full.png"
                    page.to_image(resolution=resolution).save(str(fp), format="PNG")
                    saved.append(fp)
                except Exception:
                    continue
    return saved


def _slice_focus(full_text: str, focus: str) -> Optional[str]:
    """Return text near a focus heading (±1 surrounding section), or None."""
    matches = list(_SECTION_RE.finditer(full_text))
    if not matches:
        # Fall back to substring search.
        idx = full_text.lower().find(focus.lower())
        if idx == -1:
            return None
        return full_text[max(0, idx - 500): idx + 4000]

    focus_l = focus.lower()
    target_idx = None
    for i, m in enumerate(matches):
        title = m.group(2).strip().lower()
        num = m.group(1)
        if focus_l in title or focus_l == num or focus_l in m.group(0).lower():
            target_idx = i
            break
    if target_idx is None:
        return None
    start = matches[max(0, target_idx - 1)].start()
    end_i = min(len(matches) - 1, target_idx + 2)
    end = matches[end_i].start() if end_i > target_idx else len(full_text)
    return full_text[start:end]


def extract_paper(pdf_path: Path, focus: Optional[str] = None,
                  figures_dir: Optional[Path] = None) -> dict:
    """Return a bundle of extracted paper content.

    Keys: ``full_text``, ``pages``, ``focus_excerpt``, ``figure_paths``.
    """
    pdf_path = Path(pdf_path)
    pages = extract_text(pdf_path)
    full_text = "\n\n".join(pages)
    focus_excerpt = _slice_focus(full_text, focus) if focus else None
    figure_paths: list[Path] = []
    if figures_dir is not None:
        try:
            figure_paths = extract_figures(pdf_path, figures_dir)
        except Exception:
            figure_paths = []
    return {
        "full_text": full_text,
        "pages": pages,
        "focus_excerpt": focus_excerpt,
        "figure_paths": [str(p) for p in figure_paths],
    }

