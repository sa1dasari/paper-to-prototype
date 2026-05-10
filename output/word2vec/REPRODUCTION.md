# Reproduction Report — Efficient Estimation of Word Representations in Vector Space (Word2Vec)

✅ Notebook executed successfully.

## Paper
- **Title:** Efficient Estimation of Word Representations in Vector Space (Word2Vec)
- **Original evaluation dataset:** Google News corpus (6B tokens, 1M vocabulary), also tested on Semantic-Syntactic Word Relationship test set (8869 semantic + 10675 syntactic questions)
- **Original claim / what we're reproducing:**
Table showing word analogy task accuracy (semantic and syntactic) vs. vector dimensionality and training data size. X-axis: training corpus size (e.g., 24M, 49M, 98M words). Y-axis: accuracy percentage on analogy task (e.g., 'king - man + woman ≈ queen'). Multiple curves for different embedding dimensions (50, 100, 300, 600). Shows that both dimension and data size improve accuracy with diminishing returns.

## Toy reproduction setup
- **Toy dataset:** text8 dataset (100MB of cleaned Wikipedia text, ~17M tokens) or a small subset (first 1-10MB). Alternatively, the Brown corpus or a subset of WikiText-2 for quick laptop training.
- **Hyperparameters used (toy):**
- `vector_dimension` = `50`
- `window_size` = `5`
- `learning_rate` = `0.025`
- `min_count` = `5`
- `negative_samples` = `5`
- `epochs` = `1`

## Result
![figure 1](figures/figure_01.png)

See `prototype.ipynb` for the printed numeric metric and full output.

## Gap analysis
This is a **toy** reproduction. Expected gaps vs. the original paper:
- Smaller dataset and fewer training steps; absolute metrics will not match.
- Model is scaled down for laptop CPU runtime (~2 min budget).
- Goal: reproduce the qualitative *trend* shown in the key figure, not SOTA numbers.
- Notes from the spec: For toy implementation: (1) Use Skip-gram with negative sampling (simpler than hierarchical softmax). (2) Train on small corpus (1-10MB text) for 1-3 epochs. (3) Evaluate on a subset of word analogy questions (e.g., 100-500 pairs). (4) Skip distributed training and AdaGrad; use simple SGD with linear learning rate decay. (5) Focus on demonstrating that learned vectors capture semantic relationships (king-man+woman≈queen) rather than achieving SOTA accuracy. (6) Use vocabulary of most frequent 5k-30k words instead of 1M. (7) Verify embeddings via cosine similarity and simple analogy tests rather than full benchmark.

## Agent run metadata
- **Iterations used:** 1
- **Final status:** success
- **Model:** `claude-sonnet-4-5`
