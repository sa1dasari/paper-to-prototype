# LoRA — example stub

- **Paper:** Hu et al., *LoRA: Low-Rank Adaptation of Large Language Models* (2021) — https://arxiv.org/abs/2106.09685
- **Toy dataset:** a small synthetic regression or a 2-layer MLP fine-tuning task on MNIST so the low-rank adapter is easy to plot.
- **Key figure to reproduce:** comparison of full fine-tuning vs. LoRA fine-tuning loss/accuracy at matched parameter budgets, or trainable-parameter-count vs. accuracy.

## Run

1. Drop the paper PDF here as `paper.pdf`.
2. From the repo root:

    ```powershell
    python -m src examples\lora\paper.pdf --output-dir examples\lora\generated
    ```

