"""Execute the minimal path of the workflow notebooks on the example project, for the documentation.

The notebooks are executed in place (the outputs are saved in the notebooks), in the order of the
workflow: each notebook uses the results of the previous ones. Notebook 60 combines the results of
both transects, so notebooks 51 and 52 run for Papendrecht East first (outputs not saved) and then
for Papendrecht West (outputs saved).

The optional notebooks 11, 12, 15 and 21 download data from external services (BRO, Rijkswaterstaat,
PDOK); they are not executed and appear in the documentation without outputs.

Run from the repository root: `python docs/execute_notebooks.py`. This writes results in the
example project and outputs in the notebooks: use it in the documentation build, not in a clone you
work in.
"""

import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient

NOTEBOOKS = Path(__file__).resolve().parents[1] / "notebooks"

# (notebook, transect or None, save outputs)
RUNS = [
    ("00 Set up project", None, True),
    ("01 Piezometer locations", None, True),
    ("10 Import time series from Excel", None, True),
    ("20 Geohydrological scheme", None, True),
    ("51 Prepare model inputs", "Papendrecht East", False),
    ("52 Timflow model", "Papendrecht East", False),
    ("51 Prepare model inputs", "Papendrecht West", True),
    ("52 Timflow model", "Papendrecht West", True),
    ("60 Summary over transects", None, True),
]


def run(name, transect, save):
    path = NOTEBOOKS / f"{name}.ipynb"
    nb = nbformat.read(path, as_version=4)
    if transect is not None:
        cells = [c for c in nb.cells if "parameters" in c.metadata.get("tags", [])]
        assert len(cells) == 1, f"{name}: no parameters cell"
        cells[0].source = f'transect_name = "{transect}"'
    start = time.perf_counter()
    NotebookClient(nb, timeout=900, kernel_name="python3",
                   resources={"metadata": {"path": str(NOTEBOOKS)}}).execute()
    print(f"{name} ({transect or 'project'}): {time.perf_counter() - start:.0f} s", flush=True)
    if save:
        nbformat.write(nb, path)


if __name__ == "__main__":
    for args in RUNS:
        run(*args)
