# paper-to-prototype

> Drop in an ML paper PDF → get back a runnable Jupyter notebook with a minimal PyTorch implementation, a toy dataset, and the key figure reproduced.

`paper-to-prototype` is a small **agent loop** built on Anthropic's Claude. It reads a paper, writes a notebook, runs it, reads the traceback when it explodes, fixes the code, and repeats — up to 5 times — until the notebook executes end-to-end and produces a figure.

**Scope (v1):** classical ML / small DL papers where the math fits on a page and the code fits in ~200 lines. Think word2vec, a small VAE, LoRA, the original Transformer attention, dropout, batch norm.

---

## Architecture

```
                         ┌──────────────────────────────────────────────┐
                         │                  PaperAgent                  │
                         │                                              │
  PDF ──► pdf_reader ──► extractor ──► codegen ──► executor ──► figures │
  (+focus)   (text +     (Claude →    (Claude →   (nbclient)   (PNG)    │
              figures)   spec.json)   cells.json)     ▲                 │
                                          │           │ traceback       │
                                          └── fixer ──┘  (max 5 iters)  │
                         └──────────────────────────────────────────────┘
                                          │
                                          ▼
                              prototype.ipynb + REPRODUCTION.md
```

| Stage | Module | What it does |
|------|--------|-------------|
| 1 | `src/tools/pdf_reader.py` | Per-page text + best-effort figure crops via `pdfplumber`. |
| 2 | `src/tools/extractor.py` | Claude → structured `AlgorithmSpec` JSON (inputs, outputs, hyperparams, pseudocode, key equations, toy dataset, key figure). |
| 3 | `src/tools/codegen.py` | Claude → JSON list of notebook cells (markdown + PyTorch code). Built into `.ipynb` via `nbformat`. |
| 4 | `src/tools/executor.py` | Runs the notebook with `nbclient`; on error, captures cell index + traceback. |
| 5 | `src/agent.py` | Orchestrates the loop, writes `spec.json`, `prototype.ipynb`, `REPRODUCTION.md`, `agent_log.jsonl`. |


