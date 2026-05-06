# Shared style guardrails (referenced indirectly by other prompts)

- Be precise. Do not invent results that are not in the source material.
- Prefer the simplest faithful implementation over a "complete" one.
- Target a laptop CPU: total notebook runtime should be under ~2 minutes.
- Never download arbitrary URLs. Allowed data sources:
  - `torchvision.datasets` (MNIST, FashionMNIST, CIFAR10 small subsets)
  - `sklearn.datasets` (make_classification, make_blobs, fetch_20newsgroups subset)
  - Synthetic tensors generated in-process
- Use `torch.manual_seed(0)` and `numpy.random.seed(0)` for reproducibility.
- Output is JSON. No prose, no markdown fences around the JSON.

