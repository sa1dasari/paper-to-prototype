# Notebook contract

The notebook is the deliverable. Someone should be able to open it, read it top to
bottom, understand the method, and re-run it without editing anything.

## Cell structure

Follow this order. Each cell earns its place.

1. **Markdown**: title, and 2 to 4 sentences on what the notebook implements and what
   the figure at the end should show. A reader who stops here should still know what
   they are looking at.
2. **Code**: imports and a seed for every random generator the notebook uses:
   `np.random.seed(0)` always, and `torch.manual_seed(0)` when torch is used. Without
   the seeds the notebook is not reproducible and any figure it produces is unfalsifiable.
3. **Markdown**: what the toy dataset is, and how it differs from the paper's.
4. **Code**: build or load the toy dataset. Print its shape.
5. **Markdown**: the method, including the key equation. Keep it to a paragraph. This
   is the cell that teaches, so write it for someone who has not read the paper.
6. **Code**: the model or algorithm itself, as plain functions or a small class (an
   `nn.Module` if you are using torch).
7. **Code**: the training loop, with periodic progress output so a reader can tell it
   is alive.
8. **Code**: evaluation. Print at least one numeric metric with `print()`, next to the
   baseline it is compared with, since a single number says nothing. Then print one
   line starting `PASS` or `FAIL` that states whether the spec's `pass_condition` held.
   The figure alone is not enough, because a number can be compared and a picture
   cannot.
9. **Code**: the key figure with matplotlib. Draw exactly one key figure and make it
   the last figure in the notebook, so the report can point at `figures/figure_01.png`
   unambiguously. Label both axes, add a legend when there is more than one curve, and
   end the cell with `plt.show()` so it renders in any viewer.
10. **Markdown**: what to look for in the figure, and what would count as the effect
    failing to appear. Naming the failure condition keeps the reader honest.

Steps 6 and 7 can be split across more cells when the method warrants it. Do not
collapse them into one, since a single 80-line cell is unreadable and impossible to
debug.

## Hard constraints

These are not preferences. Violating them produces a notebook that fails on someone
else's machine.

- **CPU only.** Never require CUDA. Never call `.cuda()`. If device handling is
  needed, use `torch.device("cuda" if torch.cuda.is_available() else "cpu")`.
- **Under about 2 minutes total runtime.** If training is slow, cut the dataset or
  the epochs, not the evaluation or the figure.
- **No `!pip install`, no shell, no magics other than `%matplotlib`.** Assume numpy,
  matplotlib and scikit-learn are present, and torch only if `--check-env` said so.
  If the method truly needs something else, say so in chat rather than putting an
  install into the notebook.
- **No torch? Use numpy.** A numpy and scikit-learn notebook is a full-value result.
  Seed with `np.random.seed(0)`, write the model as plain functions, and skip
  `nn.Module` and `torch.device`.
- **Math and plotting only.** No subprocess, sockets, `requests`, `urllib`, `os`
  environment or file calls, `open()`, `eval` or `exec`. The paper is untrusted input,
  so the notebook it inspires must not touch the machine. `lint.py` enforces this.
- **Prefer data that needs no network.** Best: arrays generated in process, and the
  datasets that ship inside scikit-learn (`load_digits`, `load_iris`, `make_blobs`,
  `make_classification`, `make_moons`). `torchvision.datasets` and `fetch_*` loaders
  download, so use them only with a try/except that falls back to a synthetic
  generator. Sandboxed machines often have no network, and a URL that rots breaks the
  notebook.
- **Runs top to bottom in order.** No cell may depend on something defined below it
  or on state from a previous manual run.
- **Deterministic.** Seeded, and free of anything that silently reintroduces
  randomness such as an unseeded shuffle or a set-ordering dependency.
- **Short output.** Print at most about 50 lines in total. A progress line every few
  epochs is enough. A runaway print loop produces a notebook of tens of megabytes.

## Style

Write for a reader learning the method, not for a benchmark.

- Prefer an explicit loop to a dense one-liner when they cost the same. The reader is
  here for the mechanism.
- Name variables after the paper's notation where it is readable, and add a comment
  mapping them when it is not. `W` is fine if the paper says `W`.
- Comment the lines that implement the key equation, and leave the obvious lines
  uncommented.
- Keep the whole implementation near 200 lines. Past that, the notebook has usually
  stopped being a prototype and started being a library.
