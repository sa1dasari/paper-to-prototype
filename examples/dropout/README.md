# Dropout — example stub

- **Paper:** Srivastava et al., *Dropout: A Simple Way to Prevent Neural Networks from Overfitting* (2014) — https://jmlr.org/papers/v15/srivastava14a.html
- **Toy dataset:** MNIST subset (≤ 5k train / 1k test) so a small MLP overfits quickly without dropout.
- **Key figure to reproduce:** test-error / loss curves for the same MLP **with vs. without dropout** — dropout should produce a lower or flatter test-error curve.

## Run

1. Drop the paper PDF here as `paper.pdf`.
2. From the repo root:

    ```powershell
    python -m src examples\dropout\paper.pdf --output-dir examples\dropout\generated
    ```

