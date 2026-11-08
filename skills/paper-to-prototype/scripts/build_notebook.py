#!/usr/bin/env python3
"""Build a .ipynb from a simple JSON list of cells.

Usage:
    python build_notebook.py cells.json prototype.ipynb

cells.json is a list of objects:
    [
      {"type": "markdown", "source": "# Title\\nWhat this notebook shows."},
      {"type": "code",     "source": "import numpy as np\\nnp.random.seed(0)"}
    ]

"type" is "markdown" or "code". "source" is a string or a list of lines.
Writing cells as JSON avoids hand-authoring raw notebook JSON, which is
easy to get subtly wrong. Requires: nbformat.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    try:
        import nbformat
    except ImportError:
        sys.exit("Install nbformat:  pip install nbformat")

    cells_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    cells = json.loads(cells_path.read_text(encoding="utf-8"))
    if not isinstance(cells, list) or not cells:
        sys.exit("cells.json must be a non-empty list")

    nb = nbformat.v4.new_notebook()
    for i, c in enumerate(cells):
        kind = c.get("type")
        src = c.get("source", "")
        if isinstance(src, list):
            src = "".join(src)
        if kind == "markdown":
            nb.cells.append(nbformat.v4.new_markdown_cell(src))
        elif kind == "code":
            nb.cells.append(nbformat.v4.new_code_cell(src))
        else:
            sys.exit(f"cell {i}: type must be 'markdown' or 'code', got {kind!r}")

    nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nbformat.validate(nb)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, str(out_path))
    print(f"Wrote {out_path} ({len(nb.cells)} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
