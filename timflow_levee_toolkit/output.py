"""Saving figures and tables: `finalize_and_save` (PDF with title and timestamp) and `export_to_excel`.
"""

from datetime import datetime as dt
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from openpyxl.styles import Alignment


_MAX_PATH = 259  # Windows path limit without long path support (MAX_PATH = 260 incl. terminator)


def _fit_filename(folder, name_parts, ext):
    """Join `name_parts` with "_" into a filename that fits the Windows path limit.

    `name_parts` is `["timflow", file_label, timestamp, tag, modelrun]`
    (empty parts are skipped). If `folder / filename` is too long, the
    filename is shortened step by step: first the "timflow" prefix is
    dropped, then the model run, and finally the end of the name is cut
    off. A warning is printed when the name is shortened.
    """
    available = _MAX_PATH - len(str(Path(folder).resolve())) - 1  # 1 for the separator
    candidates = [name_parts, name_parts[1:], name_parts[1:-1]]
    for parts in candidates:
        name = "_".join(p for p in parts if p) + ext
        if len(name) <= available:
            break
    else:
        stem = "_".join(p for p in candidates[-1] if p)
        if available - len(ext) < 20:
            raise OSError(f"Folder path too long to save a file in: '{folder}'")
        name = stem[: available - len(ext)] + ext

    original = "_".join(p for p in name_parts if p) + ext
    if name != original:
        print(f"Path too long for Windows; filename shortened to '{name}'")
    return name


def finalize_and_save(
    f: plt.Figure,
    savefolder: str | Path,
    project_name: str = "",
    modelrun: str = "",
    tag: str = "plot",
    show: bool = True,
    close: bool = True,
    file_label: str | None = None,
) -> None:
    """Add a suptitle and timestamp to a figure, save it, then show/close it.

    Project-specific convenience for finishing off a figure returned by
    `plot_transient_results`, `plot_steady_results`, or any other
    `(fig, axes)`-returning plot call: adds the standard suptitle and
    "Created with Timflow on ..." timestamp, saves a PDF named after
    `file_label` (or `project_name`), `tag` and `modelrun`, then optionally
    shows and closes the figure.

    Parameters
    ----------
    f : matplotlib.figure.Figure
        Figure to finalize.
    savefolder : str or pathlib.Path
        Folder to save the figure to.
    project_name : str, optional
        Project name, used in the suptitle and filename. Omitted from
        both if left as `""`. Default is `""`.
    modelrun : str, optional
        Model run label, used in the suptitle and filename. Omitted from
        both if left as `""`. Default is `""`.
    tag : str, optional
        Short tag identifying the plot type, used in the filename
        (e.g. `"headT"`, `"headX"`). Default is `"plot"`.
    show : bool, optional
        Whether to call `plt.show()`. Default is `True`.
    close : bool, optional
        Whether to call `plt.close(f)` after saving/showing. Default is
        `True`.
    file_label : str, optional
        Label in the filename instead of `project_name`, e.g. only the
        transect name when the folder already identifies the project, to
        keep paths short. Default is None (use `project_name`).

    Notes
    -----
    If the full path would exceed the Windows path limit (259 characters
    without long path support), the filename is shortened, see
    `_fit_filename`.
    """
    timestamp = dt.now()
    title_parts = [p for p in (project_name, modelrun.lower()) if p]
    f.suptitle(" - ".join(title_parts), fontweight="bold")
    f.text(
        0.9, 0.01, f"Created with Timflow on {timestamp:%Y-%m-%d %H:%M:%S}",
        ha="right", fontsize=7,
    )
    label = project_name if file_label is None else file_label
    name_parts = ["timflow", label, f"{timestamp:%Y%m%d_%H%M%S}", tag, modelrun.lower()]
    Path(savefolder).mkdir(parents=True, exist_ok=True)
    fn_out = _fit_filename(savefolder, name_parts, ".pdf")
    f.savefig(Path(savefolder) / fn_out)
    if show:
        plt.show()
    if close:
        plt.close(f)


def export_to_excel(
    df: pd.DataFrame,
    filepath,
    number_formats: dict | None = None,
    sort_by=None,
    sheet_name: str = "Sheet1",
    index: bool = True,
) -> pd.DataFrame:
    """Export a DataFrame to Excel with auto-fitted, centered columns.

    Generic replacement for the export blocks used for the response factor
    tables (steady, tidal, MHW), which only differ in which columns get a
    number format.

    Parameters
    ----------
    df : pandas.DataFrame
        Table to export.
    filepath : str or pathlib.Path
        Output .xlsx file. Overwritten if it exists.
    number_formats : dict, optional
        Excel number format per column name, e.g. ``{"rf_steady": "0.0%"}``.
    sort_by : str or list of str, optional
        Column(s) to sort by before export, e.g.
        ``["x_crosssection", "modellayer"]``.
    sheet_name : str, optional
        Name of the worksheet. Default is 'Sheet1'.
    index : bool, optional
        Whether to write the DataFrame index. Default is True.

    Returns
    -------
    pandas.DataFrame
        The (sorted) DataFrame as written to Excel.
    """
    number_formats = number_formats or {}
    missing = set(number_formats) - set(df.columns)
    if missing:
        raise KeyError(f"Columns in number_formats not found in df: {sorted(missing)}")

    if sort_by is not None:
        df = df.sort_values(sort_by)

    # Index columns are written left of the data columns
    offset = df.index.nlevels if index else 0
    center = Alignment(horizontal="center")

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=index)
        ws = writer.sheets[sheet_name]

        # Number formats for data rows (row 1 is the header)
        for colname, fmt in number_formats.items():
            col_idx = df.columns.get_loc(colname) + offset + 1  # openpyxl is 1-based
            for (cell,) in ws.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx):
                cell.number_format = fmt

        # Fit column widths to content and center all cells
        for col in ws.columns:
            max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
            ws.column_dimensions[col[0].column_letter].width = max_len + 2
            for cell in col:
                cell.alignment = center

    return df
