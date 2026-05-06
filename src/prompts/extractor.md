You are extracting a structured **AlgorithmSpec** from an ML paper so a downstream
code-generation step can implement a minimal toy version on a laptop.

## Focus hint
{focus}

## Paper text (may be truncated)
<<<PAPER
{paper_text}
PAPER

## Your task
Return ONLY a JSON object with EXACTLY these keys:

```
{{
  "title": str,
  "inputs": str,                       // what the algorithm consumes
  "outputs": str,                      // what it produces
  "hyperparameters": {{ name: value }},  // small dict of the most important ones, with sensible defaults for a TOY run
  "pseudocode": str,                   // numbered or indented pseudocode, ~10-30 lines
  "key_equations": [str],              // 1-5 core equations as plain text / LaTeX-ish
  "evaluation_dataset": str,           // dataset(s) used in the original paper
  "toy_dataset_suggestion": str,       // a CPU-laptop-sized substitute (MNIST / synthetic blobs / IMDB subset / etc.)
  "key_figure_description": str,       // the single most important figure to reproduce, in plain English (axes, what curves)
  "notes": str                         // simplifications, caveats, things to skip in the toy version
}}
```

Rules:
- Pick a TOY dataset feasible on a laptop CPU in under 2 minutes, even if the paper used a much larger one.
- Prefer reproducing a *trend* (e.g., "loss decreases", "regularized variant beats baseline") rather than absolute SOTA numbers.
- Output ONLY the JSON object. No prose. No code fences.

