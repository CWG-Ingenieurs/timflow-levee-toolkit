"""Execute the workflow notebooks on the example project, for the documentation.

The notebooks are executed in place (the outputs are saved in the notebooks), in the order of the
workflow: each notebook uses the results of the previous ones. Notebook 60 combines the results of
both transects, so notebooks 51 and 52 run for Papendrecht East first (outputs not saved) and then
for Papendrecht West (outputs saved).

The optional notebooks 11, 12, 15 and 21 download data from external services (BRO, Rijkswaterstaat,
PDOK, REGIS and GeoTOP). To keep the load on these services low, they run only for the documentation
of releases (Read the Docs version 'stable' and release tags), or with `--downloads`; otherwise (e.g.
'latest', which follows `dev`) they appear without outputs. They run after the minimal path and do not
replace series in the pastastore, so they do not change the model results. An error in one of them
(e.g. a service that is down) is shown in the notebook and does not stop the build.

The progress dots of the calibration (one per model run) are useful when running a notebook, but not
in the documentation: they are removed from the outputs.

Run from the repository root: `python docs/execute_notebooks.py [--downloads]`. This writes results
in the example project and outputs in the notebooks: use it in the documentation build, not in a
clone you work in.
"""

import os
import re
import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient

NOTEBOOKS = Path(__file__).resolve().parents[1] / "notebooks"

# (notebook, transect or None, save outputs)
MINIMAL_PATH = [
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
DOWNLOADS = [
    ("11 Download BRO groundwater levels", None, True),
    ("12 Download river levels (Rijkswaterstaat)", None, True),
    ("15 Overview of measurements", None, True),
    ("21 Subsurface data", None, True),
]


def run_downloads():
    """Whether to execute the download notebooks: with --downloads, or for releases on Read the Docs."""
    if "--downloads" in sys.argv:
        return True
    version = os.environ.get("READTHEDOCS_VERSION", "")
    version_type = os.environ.get("READTHEDOCS_VERSION_TYPE", "")
    return version == "stable" or version_type == "tag"


def strip_progress_dots(nb):
    """Remove rows of progress dots (e.g. one per model run of the calibration) from the stream outputs."""
    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        for output in cell.get("outputs", []):
            if output.get("output_type") == "stream":
                output["text"] = re.sub(r"(?m)^\.{3,}\n?", "", output["text"])
        cell.outputs = [o for o in cell.get("outputs", []) if o.get("output_type") != "stream" or o["text"].strip()]


def run(name, transect, save, allow_errors=False):
    path = NOTEBOOKS / f"{name}.ipynb"
    nb = nbformat.read(path, as_version=4)
    if transect is not None:
        cells = [c for c in nb.cells if "parameters" in c.metadata.get("tags", [])]
        assert len(cells) == 1, f"{name}: no parameters cell"
        cells[0].source = f'transect_name = "{transect}"'
    start = time.perf_counter()
    NotebookClient(nb, timeout=900, kernel_name="python3", allow_errors=allow_errors,
                   resources={"metadata": {"path": str(NOTEBOOKS)}}).execute()
    print(f"{name} ({transect or 'project'}): {time.perf_counter() - start:.0f} s", flush=True)
    if save:
        strip_progress_dots(nb)
        nbformat.write(nb, path)


if __name__ == "__main__":
    for args in MINIMAL_PATH:
        run(*args)
    if run_downloads():
        for args in DOWNLOADS:
            run(*args, allow_errors=True)
    else:
        print("Download notebooks not executed (only for releases, or with --downloads)")
