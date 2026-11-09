#!/usr/bin/env python3
"""Build a .ipynb from a simple JSON list of cells.

Usage:
    python build_notebook.py cells.json prototype.ipynb

cells.json is a list of objects:
    [
      {"type": "markdown", "source": "# Title\\nWhat this notebook shows."},
      {"type": "code",     "source": "import numpy as np\\nnp.random.seed(0)"}
    ]

"type" (or "cell_type") is "markdown" or "code", any capitalisation.
"source" is a string, or a list of lines. A list is joined with newlines unless every
item already ends in a newline. Code cells must not be empty.
Writing cells as JSON avoids hand-authoring raw notebook JSON, which is easy to get
subtly wrong. Requires: nbformat.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(2)


def to_source(i: int, raw) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        return "".join(raw) if raw and all(x.endswith("\n") for x in raw) else "\n".join(raw)
    die(f"cell {i}: 'source' must be a string or a list of strings")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    try:
        import nbformat
    except ImportError:
        die("install nbformat:  pip install nbformat")

    cells_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    if not cells_path.is_file():
        die(f"file not found: {cells_path}")
    try:
        cells = json.loads(cells_path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        die(f"{cells_path.name} is not valid UTF-8 JSON: {e}")
    if not isinstance(cells, list) or not cells:
        die("cells.json must be a non-empty list")

    nb = nbformat.v4.new_notebook()
    for i, c in enumerate(cells):
        if not isinstance(c, dict):
            die(f"cell {i}: must be an object with 'type' and 'source'")
        kind = str(c.get("type", c.get("cell_type", ""))).strip().lower()
        if "source" not in c:
            die(f"cell {i}: missing 'source'")
        src = to_source(i, c["source"])
        if kind == "markdown":
            nb.cells.append(nbformat.v4.new_markdown_cell(src))
        elif kind == "code":
            if not src.strip():
                die(f"cell {i}: code cell is empty")
            nb.cells.append(nbformat.v4.new_code_cell(src))
        else:
            die(f"cell {i}: 'type' must be 'markdown' or 'code', got {c.get('type')!r}")

    nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    try:
        nbformat.validate(nb)
    except Exception as e:
        die(f"notebook failed validation: {e}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, str(out_path))
    print(f"Wrote {out_path} ({len(nb.cells)} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
