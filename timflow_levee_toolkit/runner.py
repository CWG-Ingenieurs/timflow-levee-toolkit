"""Run the workflow notebooks for a project, with the settings of that project filled in.

The notebooks of the toolkit are not changed: a copy is filled in (project folder, transect,
model period, calibration set, ...) and executed, and the executed copy is saved in the project.
`run_transects` runs notebooks 51 and 52 for each transect and then notebook 60;
`run_notebooks` runs other notebooks (e.g. the set-up and download notebooks 00-15).
A project keeps its own settings in a short script, `run.py` (see `create_project`).
"""

import time
from datetime import datetime
from pathlib import Path

#: Folder with the workflow notebooks of the toolkit (the repository, as with an editable install)
NOTEBOOKS_DIR = Path(__file__).resolve().parents[1] / "notebooks"

#: Text inserted in the cells that are filled in
NOTE = "filled in by timflow_levee_toolkit.runner"


def _cell(nb, text, code=True):
    """The one cell whose source contains `text`."""
    cells = [c for c in nb.cells if text in c.source and (c.cell_type == "code") == code]
    if len(cells) != 1:
        raise ValueError(f"{len(cells)} cells with {text!r}; has the notebook changed?")
    return cells[0]


def _replace_line(cell, start, new_line):
    """Replace the one line of `cell` that starts with `start`."""
    lines = cell.source.split("\n")
    hits = [i for i, line in enumerate(lines) if line.startswith(start)]
    if len(hits) != 1:
        raise ValueError(f"{len(hits)} lines starting with {start!r}; has the notebook changed?")
    lines[hits[0]] = new_line
    cell.source = "\n".join(lines)


def _date(value):
    """`dt(year, month, day[, hour, minute])` for a line of a notebook."""
    t = datetime.fromisoformat(str(value)) if not isinstance(value, datetime) else value
    args = [t.year, t.month, t.day] + ([t.hour, t.minute] if (t.hour, t.minute) != (0, 0) else [])
    return f"dt({', '.join(str(a) for a in args)})"


def prepare_notebook(name, project_dir, transect=None, lines=None, cells=None, insert_after=None,
                     notebooks_dir=None):
    """Read a workflow notebook and fill in the settings of a project.

    Parameters
    ----------
    name : str
        Notebook name without '.ipynb', e.g. '51 Prepare model inputs'.
    project_dir : str or pathlib.Path or None
        Project folder: replaces the line `project_dir = ...`. None: not changed
        (the example project).
    transect : str, optional
        Transect: replaces the cell tagged 'parameters' (`transect_name = ...`).
    lines : dict, optional
        {start: new line}: the one line that starts with `start` (in the one code
        cell that contains `start`) is replaced, e.g.
        {"xlim = [dt(": "xlim = [dt(2026, 1, 30), dt(2026, 2, 6)]"}.
    cells : dict, optional
        {text: new source}: the one code cell that contains `text` gets the new source.
    insert_after : dict, optional
        {text: source}: a new code cell with `source` is inserted after the one code
        cell that contains `text`.
    notebooks_dir : str or pathlib.Path, optional
        Folder with the notebooks. Default: `NOTEBOOKS_DIR`.

    Returns
    -------
    nbformat.NotebookNode

    Raises
    ------
    ValueError
        If a cell or line to fill in is not found exactly once, e.g. because the
        notebook has changed.
    """
    import nbformat

    nb = nbformat.read(Path(notebooks_dir or NOTEBOOKS_DIR) / f"{name}.ipynb", as_version=4)
    if project_dir is not None:
        _replace_line(_cell(nb, "project_dir = "), "project_dir = ",
                      f'project_dir = Path(r"{Path(project_dir).resolve()}")  # {NOTE}')
    if transect is not None:
        params = [c for c in nb.cells if "parameters" in c.metadata.get("tags", [])]
        if len(params) != 1:
            raise ValueError(f"{name}: {len(params)} cells tagged 'parameters'")
        params[0].source = f'## {NOTE} ({datetime.now():%Y-%m-%d %H:%M})\ntransect_name = "{transect}"'
    for start, new_line in (lines or {}).items():
        _replace_line(_cell(nb, start), start, new_line)
    for text, source in (cells or {}).items():
        _cell(nb, text).source = source
    for text, source in (insert_after or {}).items():
        i = nb.cells.index(_cell(nb, text))
        nb.cells.insert(i + 1, nbformat.v4.new_code_cell(source))
    return nb


def execute_notebook(nb, save_as=None, timeout=3600, raise_errors=False, notebooks_dir=None, label=None,
                     **client_kwargs):
    """Execute a notebook in the notebook folder of the toolkit, and save the executed copy.

    Parameters
    ----------
    nb : nbformat.NotebookNode
        E.g. from `prepare_notebook`.
    save_as : str or pathlib.Path, optional
        Where to save the executed notebook (also when a cell fails). Default: not saved.
    timeout : int, optional
        Largest time per cell [s]. Default is 3600.
    raise_errors : bool, optional
        True: an error in a cell is raised. False (default): it is printed and
        the function returns False.
    notebooks_dir : str or pathlib.Path, optional
        Working folder of the notebook (relative paths in the notebook). Default: `NOTEBOOKS_DIR`.
    label : str, optional
        Name to print with the time it took. Default: `save_as`.
    **client_kwargs
        Passed to `nbclient.NotebookClient`, e.g. `allow_errors` or `on_cell_start`.

    Returns
    -------
    bool
        True if all cells ran without error.
    """
    import nbformat
    from nbclient import NotebookClient
    from nbclient.exceptions import CellExecutionError

    start = time.perf_counter()
    ok = True
    client = NotebookClient(nb, timeout=timeout, kernel_name="python3",
                            resources={"metadata": {"path": str(notebooks_dir or NOTEBOOKS_DIR)}}, **client_kwargs)
    try:
        client.execute()
    except CellExecutionError as e:
        if raise_errors:
            raise
        ok = False
        print(f"  ERROR: {str(e).strip().splitlines()[-1]}")
    finally:
        if save_as is not None:
            Path(save_as).parent.mkdir(parents=True, exist_ok=True)
            nbformat.write(nb, save_as)
    print(f"  {label or save_as} ({time.perf_counter() - start:.0f} s){'' if ok else ' - with error'}", flush=True)
    return ok


def run_notebooks(project_dir, names, save_dir=None, download_period=None, timeout=3600):
    """Run project-wide workflow notebooks, e.g. the set-up and download notebooks.

    Parameters
    ----------
    project_dir : str or pathlib.Path
        Project folder.
    names : list of str
        Notebook names without '.ipynb', e.g. ['00 Set up project', '13 Piezometer locations'].
    save_dir : str or pathlib.Path, optional
        Folder for the executed notebooks. Default: `<project>/notebooks`.
    download_period : tuple, optional
        (tmin, tmax) for the download notebooks 11 and 12, as dates or strings;
        None for no limit, e.g. ('2024-10-01', None). Default: the period of the notebook.
    timeout : int, optional
        Largest time per cell [s]. Default is 3600.

    Returns
    -------
    list of str
        The notebooks that failed.
    """
    project_dir = Path(project_dir).resolve()
    save_dir = Path(save_dir) if save_dir is not None else project_dir / "notebooks"
    failed = []
    for name in names:
        lines = {}
        if download_period is not None and name.startswith(("11", "12")):
            tmin, tmax = (f'pd.Timestamp("{t}")' if t is not None else "None" for t in download_period)
            lines = {"tmin = ": f"tmin = {tmin}  # {NOTE}", "tmax = ": f"tmax = {tmax}  # {NOTE}"}
        print(f"=== {name}", flush=True)
        nb = prepare_notebook(name, project_dir, lines=lines)
        if not execute_notebook(nb, save_dir / f"{name}.ipynb", timeout=timeout,
                                label=_relative(save_dir / f"{name}.ipynb", project_dir)):
            failed.append(name)
    print("failed: " + (", ".join(failed) if failed else "none"))
    return failed


def _relative(path, root):
    try:
        return Path(path).relative_to(root)
    except ValueError:
        return Path(path)


def run_transects(project_dir, transects=None, period=None, calibration=None, fix_loading_efficiency=False,
                  insert_after_51=None, summary=True, timeout=3600):
    """Run notebooks 51 and 52 for each transect, and then notebook 60.

    The executed notebooks are saved in the project: 51 and 52 in
    `<transect>/results_final/notebooks/`, 60 in the results folder of the project.

    Parameters
    ----------
    project_dir : str or pathlib.Path
        Project folder.
    transects : list of str, optional
        Default: all transects of the project.
    period : tuple
        (start, end) of the model period, as datetimes or ISO strings ('2026-01-30').
    calibration : dict, optional
        {transect: code}: the code of the calibration cell of notebook 52 for that
        transect (the calls of `cal.set_aquifer_parameter`, ...). A transect that is
        not listed uses the calibration cell of the notebook (the set of the example).
    fix_loading_efficiency : bool, optional
        For the transects without their own calibration set: True comments out the
        calibration of the loading efficiency (`leffaq`) in the cell of the notebook,
        so it keeps the value of the parameter file. Default is False.
    insert_after_51 : dict, optional
        {transect: code}: an extra code cell for notebook 51 of that transect,
        inserted after the cell that saves the figure 'heads_model_period.png'.
    summary : bool, optional
        Run notebook 60 (summary over the transects) at the end. Default is True.
    timeout : int, optional
        Largest time per cell [s]. Default is 3600.

    Returns
    -------
    list of str
        The notebooks that failed, as '<transect>: <notebook>'.
    """
    from . import __version__
    from .project import load_project

    if period is None:
        raise ValueError("Give the model period: period=(start, end)")
    project = load_project(project_dir)
    transects = list(transects or project.transects())
    unknown = [t for t in transects if t not in project.transects()]
    if unknown:
        raise ValueError(f"Unknown transects (not in the transects metadata): {unknown}")
    calibration = calibration or {}
    insert_after_51 = insert_after_51 or {}
    start, end = period
    print(f"toolkit {__version__} ({NOTEBOOKS_DIR.parent}), project {project.root}")
    print(f"model period {_date(start)} - {_date(end)}", flush=True)

    failed = []
    for transect in transects:
        print(f"=== {transect}", flush=True)
        folder = project.transect_dir(transect, "final") / "notebooks"
        nb51 = prepare_notebook(
            "51 Prepare model inputs", project.root, transect,
            lines={"xlim = [dt(": f"xlim = [{_date(start)}, {_date(end)}]  # model period ({NOTE})"},
            insert_after={'"heads_model_period.png"': insert_after_51[transect]} if transect in insert_after_51
            else None,
        )
        cells = {}
        if transect in calibration:
            cells = {"cal.set_aquifer_parameter(": f"# Calibration set of {transect} ({NOTE})\n{calibration[transect]}"}
        nb52 = prepare_notebook("52 Timflow model", project.root, transect, cells=cells)
        if transect not in calibration and fix_loading_efficiency:
            cell = _cell(nb52, "cal.set_aquifer_parameter(")
            source = cell.source.split("\n")
            hits = [i for i, line in enumerate(source) if "leffaq" in line and not line.lstrip().startswith("#")]
            if not hits:
                raise ValueError("No active leffaq lines in the calibration cell; has notebook 52 changed?")
            for i in hits:
                source[i] = f"# {source[i]}  # loading efficiency fixed ({NOTE})"
            cell.source = "\n".join(source)
        for name, nb in (("51 Prepare model inputs", nb51), ("52 Timflow model", nb52)):
            path = folder / f"{name}.ipynb"
            if not execute_notebook(nb, path, timeout=timeout, label=project.relpath(path)):
                failed.append(f"{transect}: {name}")
                break
    if summary:
        print("=== summary over the transects", flush=True)
        name = "60 Summary over transects"
        path = project.results_dir / f"{name}.ipynb"
        if not execute_notebook(prepare_notebook(name, project.root), path, timeout=timeout,
                                label=project.relpath(path)):
            failed.append(name)
    print("failed: " + (", ".join(failed) if failed else "none"))
    return failed


#: `run.py` of a new project (`create_project`); '{name}' is replaced by the project name
RUN_TEMPLATE = '''"""Run the workflow of timflow-levee-toolkit for the project '{name}'.

Fill in the settings below, then run from this folder, in the Python environment with the toolkit:

    python run.py setup                 # notebooks 00, 11, 12, 13 and 15 (set-up, downloads, piezometers)
    python run.py                       # notebooks 51 and 52 for all TRANSECTS, then 60
    python run.py <transect> ...        # notebooks 51 and 52 for these transects, then 60

The notebooks of the toolkit are not changed: the executed copies are saved in this project
(see `tlt.run_notebooks` and `tlt.run_transects`).
"""

import sys
from pathlib import Path

import timflow_levee_toolkit as tlt

PROJECT_DIR = Path(__file__).resolve().parent

# Download period for notebooks 11 and 12: (tmin, tmax), None for no limit
DOWNLOAD_PERIOD = (None, None)

# Model period (start, end), e.g. ("2026-01-30", "2026-02-06"); notebook 15 shows candidate periods
PERIOD = None

# Transects to run; empty: all transects of the transects metadata
TRANSECTS = []

# Calibration set per transect: the code of the calibration cell of notebook 52. A transect that is not
# listed uses the set of the notebook (the Papendrecht example: two aquifers). Example for one aquifer:
#
# CALIBRATION["<transect>"] = """
# cal.set_aquifer_parameter("c", layers=0, pmin=2, pmax=500, log_scale=True, inhoms=["river"])
# cal.set_aquifer_parameter("c", layers=0, pmin=500, pmax=7000, log_scale=True, inhoms=["foreland", "hinterland"])
# cal.set_aquifer_parameter(
#     "Saq", layers=0, pmin=1e-6, pmax=1e-2, log_scale=True, inhoms=["river", "foreland", "hinterland"],
#     model="transient",
# )
# """
CALIBRATION = dict()

# Transects without their own set: keep the loading efficiency of the parameter file (True) or calibrate it
FIX_LOADING_EFFICIENCY = True

SETUP = ["00 Set up project", "11 Download BRO groundwater levels", "12 Download river levels (Rijkswaterstaat)",
         "13 Piezometer locations", "15 Overview of measurements"]

if __name__ == "__main__":
    if sys.argv[1:] == ["setup"]:
        tlt.run_notebooks(PROJECT_DIR, SETUP, download_period=DOWNLOAD_PERIOD)
    else:
        tlt.run_transects(PROJECT_DIR, sys.argv[1:] or TRANSECTS, PERIOD, calibration=CALIBRATION,
                          fix_loading_efficiency=FIX_LOADING_EFFICIENCY)
'''
