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

---

## Install

```powershell
git clone <this-repo>
cd paper-to-prototype
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m ipykernel install --user --name python3
```

Set your Anthropic key (or copy `.env.example` → `.env`):

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

---

## Quickstart

```powershell
python -m src path\to\paper.pdf --output-dir out\my_paper
```

With a focus hint and a tighter loop:

```powershell
python -m src examples\dropout\paper.pdf --focus "Section 4" --max-iters 3
```

Output dir contents:

```
out/my_paper/
├── spec.json            # structured AlgorithmSpec
├── prototype.ipynb      # the generated, executed notebook
├── REPRODUCTION.md      # claim + result + gap analysis
├── figures/             # PNGs captured from the executed notebook
├── paper_figures/       # raster figures cropped from the source PDF
└── agent_log.jsonl      # one line per stage: extract, codegen, execute, fix
```

CLI flags:

```
pdf_path                positional, required
--focus TEXT            section heading or keyword to bias the spec extraction
--output-dir DIR        default: ./out/<pdf-stem>/
--max-iters N           default: 5
--model NAME            default: $ANTHROPIC_MODEL or claude-sonnet-4-5
--timeout SECONDS       per-notebook execution timeout, default 300
--no-execute            generate spec + notebook only (debug); skip the agent loop
```

---

## Examples

Drop a real PDF as `examples/<name>/paper.pdf` and run the agent. The repo ships with stub folders:

| Example | Paper | Toy dataset (suggested) |
|--------|-------|-------------------------|
| `examples/word2vec/` | Mikolov et al., *Efficient Estimation of Word Representations* | tiny tokenized text snippet |
| `examples/lora/` | Hu et al., *LoRA: Low-Rank Adaptation* | tiny linear regression / small MLP |
| `examples/dropout/` | Srivastava et al., *Dropout* | MNIST subset (≤ 5k samples) |

Run the full eval over every example with a `paper.pdf`:

```powershell
python eval\success_rate.py
```

This writes `eval/results.json` with per-paper status and an overall success rate.

---

## Scope & non-goals

- **In scope:** ≤ ~200 LOC implementations, single-laptop CPU, runtime budget ≈ 2 minutes per notebook, qualitative reproduction of the *trend* in one key figure.
- **Out of scope:** large-scale pretraining, multi-GPU, exact-number SOTA reproduction, papers whose method depends on a proprietary dataset.

## Known failure modes

- Papers that are mostly empirical tables (no algorithm to extract) confuse the extractor.
- Heavy LaTeX math layouts can corrupt `pdfplumber` text extraction; try `--focus` to point at a cleaner section.
- The fixer has a hard cap at 5 iterations. Pathological errors (missing native deps, kernel crashes) won't recover.

## License

MIT.

