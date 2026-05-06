You generate a self-contained PyTorch Jupyter notebook that implements a toy
version of the algorithm described in the spec below.

## AlgorithmSpec
```json
{spec_json}
```

## Output format
Return ONLY a JSON array of cell objects. Each cell:
```
{{ "type": "markdown" | "code", "source": "<string with \\n line breaks>" }}
```

## Required cell structure (in order)
1. Markdown title + 2-4 sentence summary of what the notebook does.
2. Code: imports + `torch.manual_seed(0)`, `numpy.random.seed(0)`.
3. Markdown: dataset description.
4. Code: load / build the TOY dataset (use `torchvision.datasets`, `sklearn.datasets`, or synthetic tensors).
5. Markdown: model / algorithm description with the key equation(s).
6. Code: model definition (PyTorch `nn.Module` or plain functions).
7. Code: training loop (small: <= a few hundred steps, batch size <= 128).
8. Code: evaluation — print at least ONE numeric metric using `print(...)`.
9. Code: produce the key figure with `matplotlib.pyplot`. Call `plt.show()` so the
   image is captured as a cell output.
10. Markdown: brief "what to look for in the figure" note.

## Hard constraints
- CPU-only must work; do NOT require CUDA.
- Total runtime under ~2 minutes on a modern laptop CPU.
- No network downloads other than `torchvision.datasets` (which caches to `./data`).
- Do not use `!pip install` — assume torch, torchvision, sklearn, matplotlib, numpy are installed.
- Use only standard libs + torch, torchvision, numpy, sklearn, matplotlib.
- Every code cell must be runnable top-to-bottom in order.
- Output ONLY the JSON array. No prose, no code fences around the JSON.

