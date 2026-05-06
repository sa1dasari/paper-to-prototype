"""Algorithm extractor: turn paper text into a structured AlgorithmSpec via Claude."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional, TypedDict

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
MAX_PAPER_CHARS = 80_000


class AlgorithmSpec(TypedDict, total=False):
    title: str
    inputs: str
    outputs: str
    hyperparameters: dict
    pseudocode: str
    key_equations: list[str]
    evaluation_dataset: str
    toy_dataset_suggestion: str
    key_figure_description: str
    notes: str


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Try to locate first '{' to last '}' for robustness.
    if not text.startswith("{"):
        i = text.find("{")
        j = text.rfind("}")
        if i != -1 and j != -1 and j > i:
            return text[i:j + 1]
    return text


def _truncate(text: str, limit: int = MAX_PAPER_CHARS) -> str:
    if len(text) <= limit:
        return text
    head = text[: int(limit * 0.7)]
    tail = text[-int(limit * 0.3):]
    return head + "\n\n[...TRUNCATED...]\n\n" + tail


def extract_spec(paper: dict, client, focus: Optional[str] = None,
                 model: str = "claude-sonnet-4-5") -> AlgorithmSpec:
    """Call Claude to produce an AlgorithmSpec dict from extracted paper content."""
    prompt_template = (PROMPTS_DIR / "extractor.md").read_text(encoding="utf-8")
    paper_text = paper.get("focus_excerpt") or paper.get("full_text", "")
    paper_text = _truncate(paper_text)

    user_msg = prompt_template.format(
        focus=focus or "(none)",
        paper_text=paper_text,
    )

    resp = client.messages.create(
        model=model,
        max_tokens=4096,
        system="You are a careful ML paper analyst. Output ONLY valid JSON.",
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = "".join(getattr(b, "text", "") for b in resp.content)
    data = json.loads(_strip_code_fences(raw))
    return data  # type: ignore[return-value]

