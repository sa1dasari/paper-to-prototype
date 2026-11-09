# Troubleshooting

Failures cluster. These are the ones that come up most, roughly in order of frequency,
along with what actually resolves them.

## Extraction failures

**The paper has no extractable algorithm.**
Empirical studies, surveys, and benchmark papers describe experiments rather than
methods. Recognise this while reading, before writing a spec. Offer instead to
reproduce one experimental comparison from the paper's reported numbers, or to
implement whichever baseline the paper builds on.

**Text from inside figures is garbled.**
Axis labels and legends come out reversed or as `(cid:64)` codes. Do not try to decode
them. Read the caption and the prose that discusses the figure, and open the saved
figure image itself if you need the axes.

**Two-column papers come out interleaved.**
Equations in particular get split across columns. Run
`read_pdf.py paper.pdf --pages N --render pages` and read the rendered page image. Cross-check
against the paper's prose either way.

**Math is garbled in the extracted text.**
Dense LaTeX often survives PDF extraction badly, with subscripts inlined and symbols
dropped. Cross-check any equation against the rendered figure or the paper's prose
description before implementing it. If a symbol is ambiguous, prefer the reading that
makes the equation dimensionally consistent, and note the ambiguity in the spec.

**The paper has several contributions and the spec sprawls.**
Ask the user which one they want, or pick the one carrying the main figure and say
explicitly in the spec notes that the others are out of scope.

## Execution failures

**Shape mismatch in the forward pass.**
Almost always a batch dimension or a transpose. Print shapes at each layer boundary,
find the first mismatch, and fix there rather than adding reshapes downstream to
compensate.

**Loss becomes NaN.**
In order of likelihood: learning rate too high, a `log` or division reaching zero, or
exploding gradients in a recurrent loop. Try lowering the learning rate by 10x first
since it is the cheapest test. Add epsilon inside logs. Clip gradients if the method
involves recurrence.

**Dtype errors between float and long.**
Index tensors and class labels need `.long()`, everything else usually needs
`.float()`. Cast at the point the tensor is created, not at every use site.

**Notebook exceeds the runtime budget.**
Cut in this order: dataset size, then epochs, then model width. Cutting evaluation or
the figure defeats the purpose of the notebook.

**A dataset download hangs or fails.**
Fall back to a synthetic generator. `sklearn.datasets.make_classification` and
`make_blobs` cover most cases, and generating data in process is more robust than
depending on a mirror. The bundled `sklearn.datasets.load_digits` needs no network at
all. Better still, start there so the notebook never depends on a download.

**`run_notebook.py` says BlockedBySecurityCheck.**
The notebook imports a module outside the allow-list, reads or writes files, uses a
shell escape, or uses `getattr` or dunder access. Remove it. A reproduction needs none
of these. If it truly needs one more library, read what that library does and pass
`--allow-module NAME`. Do not use `--allow-unsafe` on code derived from a paper.

**The notebook ran but there is no figure.**
Something set a non-inline matplotlib backend (`Agg`, `svg`, `pdf`), so nothing was
embedded as a PNG. Remove the `matplotlib.use(...)` call and keep `%matplotlib inline`
as the first line of the imports cell.

**The run hits the total budget.**
The budget includes kernel start-up. Cut the dataset first, then the epochs, then the
number of seeds.

## When the fix loop stalls

Five attempts is the cap. Two rules make those attempts count.

**Do not make the same fix twice.** If an error recurs after a fix, the diagnosis was
wrong. Step back and re-read the failing cell rather than adjusting the same line
again.

**Do not fix by deletion.** Removing the evaluation cell to get a clean run produces
a notebook that proves nothing. If a section cannot be made to work, leave it in,
comment what fails, and say so in the report.

At the cap, stop and report: what failed, the error, what was attempted, and what you
would try next. That is a more useful artifact than a notebook that runs but has been
hollowed out.

## When the notebook runs but the figure is wrong

**The figure is empty or flat.**
Usually the toy dataset is too easy, so every variant reaches the same result and the
curves sit on top of each other. Make the task harder: fewer samples, more noise, more
model capacity relative to the data.

**Curves are in the wrong order relative to the paper.**
Check the implementation before concluding the paper is wrong. Compare the code to the
key equations line by line. A sign error or a swapped index is far more likely than a
famous result being false.

**The effect appears but is tiny.**
Often a training length issue: the curves have not separated yet. Try more epochs
within the runtime budget before touching anything else.

If the effect still does not appear after working through these, report it as a
non-reproduction with the details of what was tried. That is a legitimate outcome and
should be written up as one, not hidden.
