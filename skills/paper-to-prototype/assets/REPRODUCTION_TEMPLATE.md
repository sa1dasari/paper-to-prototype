# Reproduction Report — [Paper title]

[One line status: the notebook ran end to end and reproduced the trend / ran but did
not reproduce the trend / did not run, with the reason.]

## The paper

- **Title:** [full title, with the method's common name]
- **Link:** [arXiv or DOI if known]
- **Original evaluation:** [datasets and scale the paper used]
- **Claim being tested:** [the specific claim, in one or two sentences. Not the
  paper's overall contribution, the single thing this notebook checks.]

## What was built instead

- **Toy dataset:** [what it is, how big, why it was chosen over the paper's]
- **Hyperparameters:** [the toy values, as a short list]
- **Deliberately skipped:** [components left out and why. This list is a feature.]

## Result

![key figure](figures/figure_01.png)

**Numeric result:** [the printed metric, with the comparison that makes it meaningful.
A single number without a baseline says nothing.]

**Reading the figure:** [what the reader should see, and what it would have looked
like if the effect had not appeared.]

## Gap analysis

Where this departs from the paper, and what that costs:

- **Scale:** [concrete numbers on both sides, and the expected effect on results]
- **Simplifications:** [what was approximated, and whether it should change the
  conclusion]
- **What would close the gap:** [what a serious reproduction would need]

Be specific here. "Smaller dataset, so results differ" is not a gap analysis. Give
the sizes, and say whether the trend survived the reduction even though the absolute
numbers did not.

## Run metadata

| Field | Value |
|---|---|
| Status | [success / partial / failed] |
| Fix iterations used | [n of 5] |
| Notebook runtime | [seconds] |
| Environment | CPU only |
