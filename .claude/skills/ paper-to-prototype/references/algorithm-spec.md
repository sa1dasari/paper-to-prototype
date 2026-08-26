# The algorithm spec

A structured summary of the paper, written before any code. Its job is to force
every ambiguous decision into the open while it is still cheap to change, and to
give the notebook a concrete target instead of a vague intent.

Save it as `spec.json`.

## Fields

| Field | Type | What goes in it |
|---|---|---|
| `title` | string | Paper title, plus the common name of the method if it has one |
| `inputs` | string | What the algorithm consumes |
| `outputs` | string | What it produces |
| `hyperparameters` | object | The handful that matter, set to values sized for a toy run, not the paper's values |
| `pseudocode` | string | Numbered steps, roughly 10 to 30 lines |
| `key_equations` | array of strings | 1 to 5 core equations, plain text or loose LaTeX |
| `evaluation_dataset` | string | What the paper actually used |
| `toy_dataset_suggestion` | string | The laptop-sized substitute, with size and shape |
| `key_figure_description` | string | The one figure to reproduce: axes, curves, expected ordering |
| `notes` | string | Simplifications, what to skip, known caveats |

## Getting the two hard fields right

**`hyperparameters`** should hold toy values, not paper values. A paper training for
100 epochs on 60,000 images becomes 3 epochs on 2,000. Write the reduced numbers here
so the notebook inherits them and the gap analysis has something concrete to compare
against.

**`key_figure_description`** should be specific enough that someone could sketch the
figure from the description alone. Name the axes, name the curves, and state which
curve should end up above which.

Weak: "a plot showing that dropout helps"

Strong: "X axis is training epoch (0 to 30), Y axis is test error rate. Two curves:
a plain network and the same network with dropout at p=0.5. Both fall early, then the
plain network's test error rises as it overfits while the dropout curve stays flat or
keeps falling. The gap at the right edge is the result."

The second version tells the code generation step exactly what to build and gives the
verification step something to check against.

## Worked example

Extracted from *Efficient Estimation of Word Representations in Vector Space*:

```json
{
  "title": "Efficient Estimation of Word Representations in Vector Space (word2vec)",
  "inputs": "A text corpus (sequence of tokens)",
  "outputs": "Dense vector representations for each word in the vocabulary",
  "hyperparameters": {
    "embedding_dim": 50,
    "window_size": 5,
    "negative_samples": 5,
    "min_count": 5,
    "learning_rate": 0.025,
    "epochs": 1
  },
  "pseudocode": "1. Tokenize corpus, build vocabulary of words with count >= min_count\n2. Initialize embedding matrix W (vocab_size x embedding_dim) randomly\n3. For each epoch:\n4.   For each center word w_t:\n5.     Collect context words within window_size\n6.     For each context word w_c:\n7.       Sample k negative words from the unigram distribution\n8.       Update embeddings to score (w_t, w_c) high and (w_t, negatives) low\n9. Return W",
  "key_equations": [
    "Skip-gram objective: maximize (1/T) sum_t sum_{-c<=j<=c, j!=0} log p(w_{t+j} | w_t)",
    "Negative sampling: log sigma(v'_{wO} . v_{wI}) + sum_{i=1}^{k} E_{w_i ~ Pn(w)}[log sigma(-v'_{w_i} . v_{wI})]"
  ],
  "evaluation_dataset": "Google News corpus, 6B tokens, 1M vocabulary, evaluated on 19,544 analogy questions",
  "toy_dataset_suggestion": "sklearn fetch_20newsgroups, a few thousand documents, vocabulary capped at 3,000 words. Small enough to train in under a minute and still large enough for nearest-neighbour structure to appear.",
  "key_figure_description": "A 2D PCA or t-SNE scatter of the learned embeddings for 30 to 50 selected words drawn from three clear semantic groups such as sports, computing, and religion. Points from the same group should cluster together. Alongside it, print the 5 nearest neighbours of 3 query words as the numeric check.",
  "notes": "Implement skip-gram only, not CBOW. Use negative sampling rather than hierarchical softmax. Skip subsampling of frequent words and the distributed training setup entirely. Do not attempt the analogy benchmark: the toy corpus is far too small for king - man + woman to resolve, and reaching for it produces a misleading result."
}
```

Note what the `notes` field is doing. It rules out the demo everyone expects from
word2vec, and explains why. Half the value of the spec is deciding in advance what
not to build.
