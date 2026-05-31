"""Code generator: convert an AlgorithmSpec into notebook cells, and patch on errors."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import nbformat

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Set by generate_cells() and fix_cells() after every Claude call so that
# agent.py can read token usage via _maybe_count() without touching return values.
_last_response = None


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    if not text.startswith("["):
        i = text.find("[")
        j = text.rfind("]")
        if i != -1 and j != -1 and j > i:
            return text[i:j + 1]
    return text


def _to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, (Path,)):
        return str(obj)
    return obj


def generate_cells(spec: dict, client, model: str = "claude-sonnet-4-5") -> list[dict]:
    """Ask Claude to produce a JSON array of {type, source} notebook cells."""
    prompt_template = (PROMPTS_DIR / "codegen.md").read_text(encoding="utf-8")
    user_msg = prompt_template.format(spec_json=json.dumps(spec, indent=2, default=_to_jsonable))
    global _last_response
    resp = client.messages.create(
        model=model,
        max_tokens=8000,
        system="You generate self-contained, CPU-friendly PyTorch Jupyter notebooks. Output ONLY valid JSON.",
        messages=[{"role": "user", "content": user_msg}],
    )
    _last_response = resp
    raw = "".join(getattr(b, "text", "") for b in resp.content)
    cells = json.loads(_strip_code_fences(raw))
    if not isinstance(cells, list):
        raise ValueError("codegen: expected a JSON list of cells")
    return cells


def fix_cells(cells: list[dict], error: dict, spec: dict, client,
              model: str = "claude-sonnet-4-5") -> list[dict]:
    """Ask Claude to revise the full cell list to fix the reported error."""
    prompt_template = (PROMPTS_DIR / "fixer.md").read_text(encoding="utf-8")
    user_msg = prompt_template.format(
        spec_json=json.dumps(spec, indent=2, default=_to_jsonable),
        cells_json=json.dumps(cells, indent=2),
        error_json=json.dumps(error, indent=2, default=_to_jsonable),
    )
    global _last_response
    resp = client.messages.create(
        model=model,
        max_tokens=8000,
        system="You fix Python errors in Jupyter notebooks. Output ONLY valid JSON: the FULL revised cell list.",
        messages=[{"role": "user", "content": user_msg}],
    )
    _last_response = resp
    raw = "".join(getattr(b, "text", "") for b in resp.content)
    new_cells = json.loads(_strip_code_fences(raw))
    if not isinstance(new_cells, list):
        raise ValueError("fixer: expected a JSON list of cells")
    return new_cells


def build_notebook(cells: list[dict], out_path: Path) -> Path:
    """Write a Jupyter notebook to ``out_path`` from {type, source} dicts."""
    nb = nbformat.v4.new_notebook()
    nb_cells = []
    for c in cells:
        ctype = c.get("type", "code")
        src = c.get("source", "")
        if isinstance(src, list):
            src = "".join(src)
        if ctype == "markdown":
            nb_cells.append(nbformat.v4.new_markdown_cell(src))
        else:
            nb_cells.append(nbformat.v4.new_code_cell(src))
    nb.cells = nb_cells
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, str(out_path))
    return out_path