# word2vec

- **Paper:** Mikolov et al., *Efficient Estimation of Word Representations in Vector Space* (2013) — https://arxiv.org/abs/1301.3781
- **Toy dataset:** a few hundred sentences of tokenized text (e.g. a slice of `sklearn.datasets.fetch_20newsgroups` or a hardcoded snippet).
- **Key figure to reproduce:** training loss curve for skip-gram with a tiny vocabulary; optionally a 2D PCA scatter of learned word vectors showing semantic clustering.

## Run

PDF lives here as `paper.pdf`. Generated artifacts go to `output/word2vec/`.

```powershell
python -m src input\word2vec\paper.pdf --output-dir output\word2vec
```

