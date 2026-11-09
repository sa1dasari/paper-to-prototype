# paper-to-prototype

> Drop in an ML paper PDF → get back a runnable Jupyter notebook with a minimal implementation (PyTorch or plain numpy), a toy dataset, and the key figure reproduced.

`paper-to-prototype` reads a paper, writes a notebook, runs it, reads the traceback when it explodes, fixes the code, and repeats (up to 5 times) until the notebook executes end to end and produces a figure. It ships two ways: as a **skill** for any agent that supports `SKILL.md`, and as a standalone **agent loop** built on the Claude API.

**Scope (v1):** classical ML / small DL papers where the math fits on a page and the code fits in ~200 lines. Think word2vec, a small VAE, LoRA, the original Transformer attention, dropout, batch norm.

There are two ways to use it:

| | Skill (`skills/paper-to-prototype/`) | Standalone agent (`src/`) |
|---|---|---|
| Runs inside | Claude Code, Cursor, Codex CLI, Claude.ai, any agent that supports `SKILL.md` | Your terminal |
| Needs an API key | No, it uses the agent you already run | Yes, `ANTHROPIC_API_KEY` |
| Good for | Interactive use: you can steer the spec and see the notebook as it is built | Batch runs and the eval in `eval/` |

---

## Use it as a skill

The skill is the folder [`skills/paper-to-prototype/`](skills/paper-to-prototype). It holds
`SKILL.md`, three reference docs, a report template and three helper scripts.

**Install**

```bash
# Any agent supported by the skills CLI
npx skills add sa1dasari/paper-to-prototype --skill paper-to-prototype

# Claude Code, by hand: copy the folder into your skills directory
git clone https://github.com/sa1dasari/paper-to-prototype
cp -r paper-to-prototype/skills/paper-to-prototype ~/.claude/skills/          # all projects
cp -r paper-to-prototype/skills/paper-to-prototype  .claude/skills/           # one project
```

Other agents use the same folder in their own skills directory. For Claude.ai, zip the
`paper-to-prototype` folder (the zip should contain that folder at its top level) and
upload it where you manage skills.

**Python packages** the skill relies on (it checks and tells you what is missing; run `python3 skills/paper-to-prototype/scripts/run_notebook.py --check-env`):

```bash
pip install nbformat nbclient ipykernel numpy matplotlib scikit-learn pdfplumber
# torch is optional: the skill falls back to numpy and scikit-learn without it
```

**Use**

Open your agent in a folder with a paper PDF and say something like:

> Implement this paper as a toy notebook: `paper.pdf`
> Can you reproduce Figure 3 from the dropout paper?
> Focus on Section 4 only.

You get `spec.json`, `prototype.ipynb`, `REPRODUCTION.md` and `figures/`. The skill is
strict about three things: it tells you when a paper is a poor fit, it reports a failed
reproduction instead of tuning until the effect appears, and it treats the paper as
untrusted input. A static check blocks generated notebooks that start processes, open
sockets, read files or read environment variables, only known math and plotting modules can
be imported, and the notebook's kernel gets a short allow-list of environment variables.

**This is a guardrail, not a sandbox.** It catches accidents and the common injected snippet.
It does not stop a determined attacker, and a notebook runs as you, so it can read your files
and the environment of your other processes. If you run papers from sources you do not trust,
do it inside a container or VM that holds no real secrets.

The helper scripts are `read_pdf.py`, `build_notebook.py`, `lint.py` and `run_notebook.py`.
They use only the packages above and never call an API. Regression tests for them,
including a list of known bypass attempts, run with `python3 tests/test_skill_scripts.py`.

---

## Use it as a standalone agent

### Architecture

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

### Quickstart

```bash
pip install -r requirements.txt
cp .env.example .env   # then set ANTHROPIC_API_KEY
```

Drop a paper PDF into `input/<name>/paper.pdf` and run:

```bash
python -m src input/word2vec/paper.pdf --output-dir output/word2vec
```

With a focus hint and a tighter loop:

```bash
python -m src input/word2vec/paper.pdf --output-dir output/word2vec --focus "Section 4" --max-iters 3
```

Repo layout for inputs/outputs:

```
input/
└── word2vec/paper.pdf                 # you put PDFs here (one folder per paper)

output/
└── word2vec/
    ├── latest.txt                     # name of the most recent run subfolder
    ├── 2026-05-10_18-01-49/           # one timestamped folder per run
    │   ├── spec.json                  # structured AlgorithmSpec
    │   ├── prototype.ipynb            # the generated, executed notebook
    │   ├── REPRODUCTION.md            # claim + result + gap analysis
    │   ├── figures/                   # PNGs captured from the executed notebook
    │   ├── paper_figures/             # raster/page images cropped from the source PDF
    │   └── agent_log.jsonl            # one line per stage: extract, codegen, execute, fix
    └── 2026-05-10_19-22-03/           # next run; previous one is preserved
        └── ...
```

Each invocation writes to a fresh timestamped subfolder so re-runs don't clobber prior results. Pass `--overwrite` to write directly into `--output-dir` instead (the old behavior). The sibling `latest.txt` always names the newest run.

> Every artifact under `output/<name>/<timestamp>/` (notebook, REPRODUCTION.md, spec.json, figures, paper_figures, `agent_log.jsonl`) is **committed to git**, so past runs can be inspected. Only `__pycache__/`, the venv, `.env`, `eval/results.json` and downloaded datasets (`output/**/data/`) are ignored.

CLI flags:

```
pdf_path                positional, required
--focus TEXT            section heading or keyword to bias the spec extraction
--output-dir DIR        default: ./output/<pdf-stem>/
--max-iters N           default: 5
--model NAME            default: $ANTHROPIC_MODEL or claude-sonnet-4-5
--timeout SECONDS       per-notebook execution timeout, default 300
--no-execute            generate spec + notebook only (debug); skip the agent loop
--overwrite             write into --output-dir directly (no timestamped subfolder)
```

#### Live progress logs

Both `agent.py` and `eval/success_rate.py` print per-stage progress to stderr in real time. A successful word2vec run looks like:

```
[agent] starting  pdf=input\word2vec\paper.pdf  output_dir=output\word2vec\2026-05-10_18-01-49  model=claude-sonnet-4-5
[agent] [+  0.0s] pdf_read       pdf=input\word2vec\paper.pdf
[agent] [+  3.1s] extract_spec   focus=None
[agent] [+ 28.4s] codegen_initial
[agent] [+ 91.7s] execute        iter=1
[agent] [+106.5s] execute_ok     iter=1
[agent] [+106.7s] done           status=ok  iterations=1
```

Long pauses between lines are normal - Claude calls take 20–60s and notebook execution can take a minute or two. The same stages are also persisted as JSON in `agent_log.jsonl` for later analysis.

---

### Scope & non-goals

- **In scope:** ≤ ~200 LOC implementations, single-laptop CPU, runtime budget ≈ 2 minutes per notebook, qualitative reproduction of the *trend* in one key figure.
- **Out of scope:** large-scale pretraining, multi-GPU, exact-number SOTA reproduction, papers whose method depends on a proprietary dataset.

### Known failure modes

- Papers that are mostly empirical tables (no algorithm to extract) confuse the extractor.
- Heavy LaTeX math layouts can corrupt `pdfplumber` text extraction; try `--focus` to point at a cleaner section.
- The fixer has a hard cap at 5 iterations. Pathological errors (missing native deps, kernel crashes) won't recover.

---

## License

MIT. See [LICENSE](LICENSE). The papers in `input/` are the property of their authors and publishers and are included only as sample inputs.
