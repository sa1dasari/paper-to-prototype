"""Notebook executor + error capture + figure extraction."""
from __future__ import annotations

import base64
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError, CellTimeoutError


@dataclass
class ExecutionResult:
    success: bool
    error_cell_index: Optional[int] = None
    error_name: Optional[str] = None
    error_value: Optional[str] = None
    traceback: Optional[str] = None
    executed_path: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _strip_ansi(s: str) -> str:
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def execute_notebook(nb_path: Path, timeout: int = 300,
                     kernel: str = "python3") -> ExecutionResult:
    """Execute a notebook in-place. Return success/error info."""
    nb_path = Path(nb_path)
    nb = nbformat.read(str(nb_path), as_version=4)
    client = NotebookClient(
        nb,
        timeout=timeout,
        kernel_name=kernel,
        allow_errors=False,
        resources={"metadata": {"path": str(nb_path.parent)}},
    )
    try:
        client.execute()
        nbformat.write(nb, str(nb_path))
        return ExecutionResult(success=True, executed_path=str(nb_path))
    except CellTimeoutError as e:
        # Cell execution timed out. Persist partial outputs and report timeout.
        nbformat.write(nb, str(nb_path))
        return ExecutionResult(
            success=False,
            error_name="CellTimeoutError",
            error_value=f"Cell execution timed out after {timeout} seconds. "
                        "Consider increasing --timeout or optimizing the generated code.",
            traceback=str(e),
            executed_path=str(nb_path),
        )
    except CellExecutionError:
        # Persist partial outputs for inspection.
        nbformat.write(nb, str(nb_path))
        # Find first cell with an error output.
        for idx, cell in enumerate(nb.cells):
            if cell.get("cell_type") != "code":
                continue
            for out in cell.get("outputs", []) or []:
                if out.get("output_type") == "error":
                    tb = "\n".join(out.get("traceback", []) or [])
                    return ExecutionResult(
                        success=False,
                        error_cell_index=idx,
                        error_name=out.get("ename"),
                        error_value=out.get("evalue"),
                        traceback=_strip_ansi(tb),
                        executed_path=str(nb_path),
                    )
        return ExecutionResult(
            success=False,
            error_name="UnknownExecutionError",
            error_value="Execution failed but no error output was captured.",
            traceback=None,
            executed_path=str(nb_path),
        )


def extract_figure_outputs(nb_path: Path, out_dir: Path) -> list[Path]:
    """Save base64 PNG outputs from an executed notebook into ``out_dir``."""
    nb_path = Path(nb_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    nb = nbformat.read(str(nb_path), as_version=4)
    saved: list[Path] = []
    n = 0
    for cell in nb.cells:
        if cell.get("cell_type") != "code":
            continue
        for out in cell.get("outputs", []) or []:
            data = out.get("data") or {}
            png = data.get("image/png")
            if png:
                n += 1
                fp = out_dir / f"figure_{n:02d}.png"
                fp.write_bytes(base64.b64decode(png))
                saved.append(fp)
    return saved

