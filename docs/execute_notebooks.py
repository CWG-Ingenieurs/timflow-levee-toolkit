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
(e.g. a service that is down) is shown in the notebook and does not stop the build. To stay within the
15 minutes of Read the Docs, the download notebooks must be done 11 minutes after the start of this
script: a cell that takes too long (a service that does not respond) leaves that notebook without outputs,
and a download notebook is not started after 9 minutes.

Progress output is useful when running a notebook, but not in the documentation: the dots of the
calibration (one per model run) and the progress bars of the downloads (tqdm) are removed from the
outputs.

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
    ("10 Import time series from Excel", None, True),
    ("13 Piezometer locations", None, True),
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


# Rows of progress dots, e.g. one per model run of the calibration
DOTS = re.compile(r"(?m)^\.{3,}\n?")
# Progress bars of tqdm, e.g. " 50%|█████     | 2/4 [00:08<00:08,  4.31s/it]" or "Get stresses: 0it [00:00, ?it/s]"
PROGRESS_BAR = re.compile(r"[^\r\n]*(?:\d+%\|[^\r\n|]*\||\d+it \[[^\]\r\n]*(?:it/s|s/it)\])[^\r\n]*[\r\n]*")


def merge_streams(outputs):
    """Merge consecutive outputs of the same stream (stdout or stderr) into one, as Jupyter shows them.

    Output that is flushed in parts, e.g. one dot per model run of the calibration
    (`print(".", end="", flush=True)`), is stored as one output per part.
    """
    merged = []
    for output in outputs:
        previous = merged[-1] if merged else None
        if (output.get("output_type") == "stream" and previous is not None
                and previous.get("output_type") == "stream" and previous["name"] == output["name"]):
            previous["text"] += output["text"]
        else:
            merged.append(output)
    return merged


def strip_progress(nb):
    """Remove progress output (dots and tqdm progress bars) from the stream outputs of a notebook."""
    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        cell.outputs = merge_streams(cell.get("outputs", []))
        for output in cell.outputs:
            if output.get("output_type") == "stream":
                output["text"] = PROGRESS_BAR.sub("", DOTS.sub("", output["text"]))
        cell.outputs = [o for o in cell.get("outputs", []) if o.get("output_type") != "stream" or o["text"].strip()]


# The download notebooks depend on external services that are sometimes very slow (a cell of notebook 21
# once hung for more than 15 minutes). Read the Docs stops a build after 15 minutes (about 1 minute of it
# for the installation and 1-2 minutes for Sphinx), so the download notebooks must be done DOWNLOAD_DEADLINE
# seconds after the start of this script: a notebook is not started after DOWNLOAD_LAST_START, a cell may
# take at most DOWNLOAD_CELL_TIMEOUT (and not beyond the deadline), and no cell starts after the deadline.
DOWNLOAD_CELL_TIMEOUT = 300  # [s]
DOWNLOAD_LAST_START = 540  # [s] since the start of this script
DOWNLOAD_DEADLINE = 660  # [s] since the start of this script


class DeadlineExceeded(RuntimeError):
    """The download notebooks ran past DOWNLOAD_DEADLINE."""


def run(name, transect, save, allow_errors=False, timeout=900, deadline=None):
    """Execute a notebook; with `deadline` (a `time.perf_counter()` value) no cell starts after it."""
    path = NOTEBOOKS / f"{name}.ipynb"
    nb = nbformat.read(path, as_version=4)
    if transect is not None:
        cells = [c for c in nb.cells if "parameters" in c.metadata.get("tags", [])]
        assert len(cells) == 1, f"{name}: no parameters cell"
        cells[0].source = f'transect_name = "{transect}"'

    def check_deadline(**kwargs):
        if deadline is not None and time.perf_counter() > deadline:
            raise DeadlineExceeded(f"{name}: past the deadline of the download notebooks")

    start = time.perf_counter()
    NotebookClient(nb, timeout=timeout, kernel_name="python3", allow_errors=allow_errors,
                   on_cell_start=check_deadline, resources={"metadata": {"path": str(NOTEBOOKS)}}).execute()
    print(f"{name} ({transect or 'project'}): {time.perf_counter() - start:.0f} s", flush=True)
    if save:
        strip_progress(nb)
        nbformat.write(nb, path)


def run_download(name, transect, save, started):
    """Run a download notebook; a time-out or other failure is reported and does not stop the build.

    Errors in a cell are shown in the notebook (`allow_errors`). A cell that does not finish in time, or
    the deadline of the download notebooks, stops the notebook: it then appears without outputs.
    """
    elapsed = time.perf_counter() - started
    if elapsed > DOWNLOAD_LAST_START:
        print(f"{name}: skipped, the build has already run for {elapsed:.0f} s", flush=True)
        return
    deadline = started + DOWNLOAD_DEADLINE
    timeout = int(max(30, min(DOWNLOAD_CELL_TIMEOUT, deadline - time.perf_counter())))
    try:
        run(name, transect, save, allow_errors=True, timeout=timeout, deadline=deadline)
    except Exception as e:  # e.g. CellTimeoutError of a service that does not respond, or DeadlineExceeded
        print(f"{name}: not executed ({type(e).__name__}), it appears without outputs", flush=True)


if __name__ == "__main__":
    started = time.perf_counter()
    for args in MINIMAL_PATH:
        run(*args)
    if run_downloads():
        for args in DOWNLOADS:
            run_download(*args, started=started)
    else:
        print("Download notebooks not executed (only for releases, or with --downloads)")
