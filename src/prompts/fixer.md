A previously-generated Jupyter notebook failed to execute. Revise the FULL cell
list to fix the error while preserving the original intent of the spec.

## Original AlgorithmSpec
```json
{spec_json}
```

## Current cells (JSON array)
```json
{cells_json}
```

## Execution error
```json
{error_json}
```

## Instructions
- Address the ROOT CAUSE of the error, not just the symptom.
- Make the smallest set of changes needed to make the notebook run end-to-end.
- Preserve the cell ordering and overall structure.
- Keep the toy dataset, the numeric metric print, and the matplotlib key figure.
- Keep CPU-only and ~2-minute runtime constraints.
- Do not add `!pip install` commands.

## Output format
Return ONLY a JSON array of `{{ "type", "source" }}` cells representing the
COMPLETE revised notebook. No prose, no code fences.

