---
name: paper-to-prototype
description: Turn a machine learning research paper into a runnable Jupyter notebook that implements a minimal version of its algorithm on a toy dataset and reproduces its key figure. Use this whenever someone shares an ML or stats paper (PDF, arXiv link, or pasted text) and wants to implement it, reproduce it, prototype it, understand it through code, verify whether its claim holds, or "see it actually run." Also use it when someone asks to reimplement a named method from a paper such as dropout, batch norm, LoRA, ADWIN, or word2vec, even if they do not mention a paper file. Trigger on phrasings like "implement this paper", "does this actually work", "can you reproduce Figure 3", "build a prototype of this method", or "I want to play with this algorithm."
---

# Paper to Prototype

Turn an ML paper into a small, honest, running implementation.

The goal is not a faithful reproduction of the paper's headline numbers. It is a
notebook that runs end to end on a laptop CPU in about two minutes and shows the
*qualitative trend* the paper claims. A regularized variant beating a baseline.
A loss curve dropping. A window shrinking when drift appears. Someone reading the
notebook should come away understanding the mechanism, not admiring a benchmark.

Aim for an implementation of roughly 200 lines or less. If the method cannot be
demonstrated in that budget, say so early rather than producing something bloated.

## Workflow

Work through these five stages in order. Do not skip straight to writing code from
the paper text: the spec stage is what keeps the notebook honest and scoped.

### 1. Read the paper

Read the PDF directly. If given an arXiv link, fetch it. If the user names a method
without supplying a paper, ask for the paper or link rather than working from memory,
since implementing a half-remembered method is how subtle errors get in.

If the user gave a focus hint (a section number, a figure, a specific claim), let it
narrow everything downstream. Papers often contain several contributions and the user
usually wants one.

Skim for structure first, then read closely: the algorithm box or pseudocode, the
core equations, the experimental setup, and the figure that carries the main claim.
Ignore related work, most of the ablations, and the appendix unless the focus points
there.

### 2. Extract an algorithm spec

Before writing any code, write out a structured spec. This forces the ambiguity to
surface while it is still cheap to resolve.

Read `references/algorithm-spec.md` for the field list and a worked example. Save the
spec as `spec.json` alongside the notebook so the user can see what was extracted and
correct it.

The two fields that matter most and are most often done badly:

- **toy_dataset_suggestion** must be something that loads and trains in seconds. The
  paper used 6 billion tokens or ImageNet; you get synthetic blobs, MNIST, or a
  sklearn generator. Choose a substitute that still *exercises the mechanism*. A
  regularization paper needs a dataset where a model can actually overfit, otherwise
  the figure shows nothing.
- **key_figure_description** must name the axes and the shape of the expected result
  in plain English, including which curve should sit above which. This is the target
  the notebook is aiming at, and a vague description here produces an aimless figure.

Show the spec to the user before generating the notebook when the paper is ambiguous
or when the focus could reasonably be read more than one way. Otherwise proceed.

### 3. Generate the notebook

Build a notebook that follows the cell contract in `references/notebook-contract.md`.
The contract is not stylistic. Each required cell exists because a notebook missing it
fails at its job: no seed means no reproducibility, no printed metric means the reader
has only a picture, no `plt.show()` means the figure is not captured in the output.

Write clean, readable code and let it be plain. Someone reading this notebook is
trying to learn the method, so prefer an explicit loop over a clever vectorization
when the two are close in speed.

### 4. Execute and fix

Run the notebook. When a cell fails, fix the root cause rather than the symptom, then
re-run from the top so you know the whole thing still works in order.

Cap the fix loop at 5 attempts. If it still fails, stop and report honestly what broke
and what you tried, rather than deleting the failing section to force a green run. A
notebook that silently dropped the evaluation to avoid an error is worse than one that
admits it failed.

Check `references/troubleshooting.md` when a failure repeats or looks familiar. It
covers the failure modes that come up most and what actually fixes them.

Watch the runtime budget while iterating. If a fix pushes execution past a few
minutes, cut the dataset or the step count rather than accepting a slow notebook.

### 5. Write the reproduction report

Produce a `REPRODUCTION.md` next to the notebook using the template in
`assets/REPRODUCTION_TEMPLATE.md`. It states the paper's claim, what was built
instead, the result, and where the toy version departs from the original.

The gap analysis section is the part that matters and the part most likely to be
written lazily. Be specific. "Smaller dataset" is filler. "Trained on 2,000 MNIST
digits for 3 epochs versus the paper's full 60,000 for 100, so absolute accuracy is
roughly 15 points lower while the gap between the two variants persists" is the
actual finding.

## When the result contradicts the paper

Sometimes the toy version does not show the claimed effect. Do not quietly retune
hyperparameters until it does, and do not present a null result as a success.

Work through the likely causes in order, since most of the time it is your setup and
not the paper:

1. The toy dataset is too easy or too small for the effect to appear. A regularizer
   does nothing on a model that cannot overfit.
2. Training was too short for the curves to separate.
3. A hyperparameter is off by an order of magnitude, learning rate most often.
4. The method was implemented subtly wrong. Re-read the equations against the code.

If none of those explain it, say so plainly in the report. A clearly documented
failure to reproduce is a real and useful result, and it is more valuable to the
reader than a figure that was massaged into agreement.

## Scope

Good fits: classical ML and small deep learning papers where the method fits on a
page and the implementation fits in about 200 lines. Word2vec, dropout, batch norm,
LoRA, ADWIN, scaled dot-product attention, a small VAE.

Poor fits, and worth flagging to the user before starting rather than after:

- Papers that are mostly empirical tables with no algorithm to extract.
- Methods that only make sense at scale, where a toy version demonstrates nothing.
- Anything depending on a proprietary or access-controlled dataset.
- Large scale pretraining, multi-GPU work, or exact SOTA number reproduction.

For a poor fit, offer the alternative that does fit: implementing one component, a
figure-only reproduction from published numbers, or a walkthrough of the method
without the full experiment.

## Output

Write everything into a single output directory:

```
<paper-name>/
├── spec.json           # the extracted algorithm spec
├── prototype.ipynb     # the executed notebook, outputs included
├── REPRODUCTION.md     # claim, result, gap analysis
└── figures/            # PNGs from the executed notebook
```

Present the notebook first, then the report. Keep the summary message short: the
artifacts carry the detail, and restating them in chat just makes the user read
everything twice.
