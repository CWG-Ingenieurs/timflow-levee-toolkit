"""Project settings, transects metadata and piezometer tables.

A project consists of several transects (cross-sections through a levee). Per
project there is one settings file (`project_settings.toml`, optional) with the
folder and file names, and one metadata table (`transects_metadata.xlsx`) with
one row per transect. This module reads those, creates the folder structure and
reads and writes the piezometer locations.
"""

import copy
import tomllib
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from .output import set_figure_format


# -----------------------------------------------------------------------------
# Project settings
# -----------------------------------------------------------------------------
# Default folder and file names. A project overrides any of them in
# `project_settings.toml` in the project folder; paths are relative to the
# project folder. `{transect}` and `{loc_storm_event}` are filled in per
# transect.
DEFAULT_SETTINGS = {
    "project": {"name": "", "crs": "EPSG:28992"},
    "paths": {
        "general": "data/general",
        "transects": "data/transects",
        "transects_metadata": "transects_metadata.xlsx",  # in `general`
        "piezometers": "piezometers.xlsx",  # in `general`
        "timeseries": "timeseries.xlsx",  # in `general`
        "project_data": "project_data.gpkg",  # in `general`
        "piezometer_layer": "piezometers",  # layer in `project_data`
        "river_gauge_layer": "river_gauges",  # layer in `project_data` (written by notebook 12)
        "parameters": "model_parameters_{transect}.xlsx",  # in the transect folder
        "storm_event": "storm_events/storm_event_{loc_storm_event}.xlsx",  # in `general`
        "results": "results",  # project-wide results (summary over transects)
    },
    "transect_folders": {
        "pastastore": "pastastore",
        "timeseries": "timeseries",
        "subsurface": "subsurface",
        "intermediate": "results_intermediate",
        "final": "results_final",
    },
    "units": {"head": "m NAP", "head_rel": "m", "time": "days", "x": "m"},
    "figures": {"format": "png", "dpi": 200},  # figures saved by `finalize_and_save`
}

# Columns of the transects metadata table
METADATA_REQUIRED = [
    "transect", "polder_level", "undisturbed_head", "loc_river",
    "width_river", "width_foreland", "width_hinterland",
]
METADATA_OPTIONAL = [
    "location", "loc_storm_event", "farfield",
    "x1_xsec", "y1_xsec", "x2_xsec", "y2_xsec",
]
FARFIELD_OPTIONS = ("polder_level", "undisturbed_head")


def _merge(defaults, overrides):
    """Recursively merge `overrides` into a copy of `defaults`."""
    merged = copy.deepcopy(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class Project:
    """Folder structure and project-wide data of a project with several transects.

    Create it with `load_project`. All paths are derived from the project
    folder and the settings, so the notebooks don't contain any paths.
    """

    def __init__(self, root, settings):
        self.root = Path(root).resolve()
        self.settings = settings

    def __repr__(self):
        return f"Project({self.name!r}, root={str(self.root)!r})"

    @property
    def name(self):
        return self.settings["project"]["name"] or self.root.name

    @property
    def crs(self):
        return self.settings["project"]["crs"]

    @property
    def units(self):
        """Units for axis labels, see `DEFAULT_UNITS`."""
        return dict(self.settings["units"])

    # --- paths
    def relpath(self, path):
        """`path` relative to the project folder if it is inside it, else unchanged (for printing)."""
        try:
            return Path(path).resolve().relative_to(self.root)
        except ValueError:
            return Path(path)

    @property
    def general_dir(self):
        return self.root / self.settings["paths"]["general"]

    @property
    def results_dir(self):
        """Folder for project-wide results, e.g. the summary over all transects."""
        return self.root / self.settings["paths"]["results"]

    def general_file(self, key):
        """Path of a project-wide file: 'transects_metadata', 'piezometers',
        'timeseries' or 'project_data'."""
        return self.general_dir / self.settings["paths"][key]

    def transect_dir(self, transect, folder=None):
        """Folder of a transect, or one of its subfolders ('pastastore',
        'timeseries', 'subsurface', 'intermediate', 'final')."""
        path = self.root / self.settings["paths"]["transects"] / transect
        if folder is not None:
            path = path / self.settings["transect_folders"][folder]
        return path

    def parameters_file(self, transect):
        """Excel file with the geohydrological parameters of a transect."""
        name = self.settings["paths"]["parameters"].format(transect=transect)
        return self.transect_dir(transect) / name

    def storm_event_file(self, loc_storm_event):
        """Excel file with the storm event ('waterstandsverloop') of a location."""
        name = self.settings["paths"]["storm_event"].format(loc_storm_event=loc_storm_event)
        return self.general_dir / name

    # --- data
    def metadata(self):
        """The transects metadata table (one row per transect)."""
        return read_transects_table(self.general_file("transects_metadata"))

    def transects(self):
        """Names of all transects in the metadata table."""
        return self.metadata()["transect"].tolist()

    def transect_metadata(self, transect):
        """Metadata of one transect, see `read_transect_metadata`."""
        return read_transect_metadata(self.general_file("transects_metadata"), transect)

    def crosssection(self, transect):
        """Cross-section line `[(x1, y1), (x2, y2)]` of a transect (river side first), or None.

        From the columns 'x1_xsec', 'y1_xsec', 'x2_xsec' and 'y2_xsec' of the metadata.
        """
        row = self.metadata().set_index("transect").loc[transect]
        columns = ("x1_xsec", "y1_xsec", "x2_xsec", "y2_xsec")
        if not all(c in row.index and pd.notna(row[c]) for c in columns):
            return None
        x1, y1, x2, y2 = (float(row[c]) for c in columns)
        return [(x1, y1), (x2, y2)]

    def piezometer_table(self, transect=None):
        """Piezometers from the piezometer table (`piezometers.xlsx`), checked with `read_piezometer_table`.

        Parameters
        ----------
        transect : str, optional
            Only the piezometers of this transect. Default: all piezometers.

        Returns
        -------
        pandas.DataFrame
        """
        table = read_piezometer_table(self.general_file("piezometers"))
        if transect is not None:
            table = table[table["transect"] == transect].copy()
        return table

    def piezometers(self, transect):
        """Piezometers of one transect from the project geopackage (written by notebook 13)."""
        return read_piezometers(
            self.general_file("project_data"), transect, layer=self.settings["paths"]["piezometer_layer"]
        )

    def open_pastastore(self, transect):
        """Open (or create) the pastastore of a transect.

        Wraps `pastastore.PastaStore(pastastore.PasConnector(name, path))`, with
        the folder 'pastastore' of the transect (`transect_folders` in the
        project settings). The returned `pastastore.PastaStore` has all methods
        of pastastore, e.g. `pstore.oseries`, `pstore.get_oseries(name)` and
        `pstore.plots`; see https://pastastore.readthedocs.io.
        """
        import pastastore as pst

        # verbose=False: no info message per library ("already exists"); warnings and errors are still shown
        conn = pst.PasConnector(
            self.settings["transect_folders"]["pastastore"], self.transect_dir(transect), verbose=False
        )
        return pst.PastaStore(conn)

    def model_period_series(self, transects=None):
        """Hourly river levels and heads of the transects, to choose a model period.

        Only the piezometers that are used in the calibration (with
        `modellayer` and `x_crosssection`, and `use_calibration` not 0, from the
        project geopackage) and the river gauge of each transect.

        Parameters
        ----------
        transects : list of str, optional
            Default: all transects.

        Returns
        -------
        rivers, heads : pandas.DataFrame
            Hourly means on one time axis (NaN for hours without data); the
            columns of `heads` are named '<transect>: <piezometer>'.
        """
        rivers, heads = {}, {}
        for transect in transects or self.transects():
            loc_river = self.transect_metadata(transect)["loc_river"]
            piezometers = self.piezometers(transect)
            use = piezometers["modellayer"].notna() & piezometers["x_crosssection"].notna()
            if "use_calibration" in piezometers.columns:
                use &= piezometers["use_calibration"] != 0
            names = set(piezometers.loc[use, "name"])
            pstore = self.open_pastastore(transect)
            for name in pstore.oseries_names:
                if name != loc_river and name not in names:
                    continue
                s = pstore.get_oseries(name)
                s = (s.iloc[:, 0] if isinstance(s, pd.DataFrame) else s).dropna().resample("1h").mean()
                if name == loc_river:
                    rivers[name] = s
                else:
                    heads[f"{transect}: {name}"] = s
        series = {**rivers, **heads}
        if not series:
            raise ValueError("No river levels or piezometers used in the calibration found")
        hours = pd.date_range(min(s.index.min() for s in series.values()).ceil("D"),
                              max(s.index.max() for s in series.values()).floor("D"), freq="1h")
        return pd.DataFrame(rivers).reindex(hours), pd.DataFrame(heads).reindex(hours)

    # --- set up and overview
    def create_folders(self, transects=None):
        """Create the general folder and the folders of all (or the given) transects."""
        self.general_dir.mkdir(parents=True, exist_ok=True)
        for transect in transects or self.transects():
            for folder in [None, *self.settings["transect_folders"]]:
                if folder == "pastastore":
                    continue  # created by pastastore itself
                self.transect_dir(transect, folder).mkdir(parents=True, exist_ok=True)

    def status(self):
        """Overview per transect of which inputs are available.

        Returns
        -------
        pandas.DataFrame
            One row per transect with the number of piezometers, the number
            of series in the pastastore and whether the parameter file and
            the storm event file exist.
        """
        metadata = self.metadata()
        gpkg = self.general_file("project_data")
        rows = []
        for _, row in metadata.iterrows():
            transect = row["transect"]
            n_piezometers = np.nan
            if gpkg.exists():
                try:
                    n_piezometers = len(self.piezometers(transect))
                except (KeyError, ValueError):
                    pass
            pstore_dir = self.transect_dir(transect, "pastastore")
            n_series = len(list((pstore_dir / "oseries").glob("*.pas"))) if pstore_dir.exists() else 0
            loc_storm = row.get("loc_storm_event")
            rows.append({
                "transect": transect,
                "folder": self.transect_dir(transect).exists(),
                "piezometers": n_piezometers,
                "series_in_pastastore": n_series,
                "parameter_file": self.parameters_file(transect).exists(),
                "storm_event_file": bool(pd.notna(loc_storm) and self.storm_event_file(loc_storm).exists()),
            })
        return pd.DataFrame(rows).set_index("transect")


#: Example project of the repository: its input files are the templates for `create_project`
EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples" / "papendrecht"


def create_project(project_dir, name=None):
    """Create an empty project: the input files of the example project without their data.

    Creates in `project_dir` (an empty or new folder):

    - `project_settings.toml`: the settings of the example, with the project name;
    - `data/general/transects_metadata.xlsx`, `piezometers.xlsx` and
      `timeseries.xlsx`: only the column headers, with the sheet
      'explanation' of each file;
    - `data/general/model_parameters_TEMPLATE.xlsx`: template of the
      geohydrological scheme (`create_parameter_template`), to copy to
      `data/transects/<transect>/model_parameters_<transect>.xlsx`;
    - the folders `data/general/storm_events` and `data/transects`;
    - `run.py`: the settings to run notebooks 51, 52 and 60 for all
      transects with `run_transects` (model period, transects, calibration).

    Needs the repository of the toolkit (the example project), as with an
    editable install.

    Parameters
    ----------
    project_dir : str or pathlib.Path
        Folder of the new project; it must be empty or not exist.
    name : str, optional
        Name of the project. Default: the name of the folder.

    Returns
    -------
    Project
    """
    from openpyxl import load_workbook

    from .model import create_parameter_template
    from .runner import RUN_TEMPLATE

    project_dir = Path(project_dir)
    if project_dir.exists() and any(project_dir.iterdir()):
        raise FileExistsError(f"'{project_dir}' is not empty")
    if not EXAMPLE_DIR.exists():
        raise FileNotFoundError(f"Example project not found ({EXAMPLE_DIR}): install the toolkit from its repository")
    name = name or project_dir.resolve().name
    general = project_dir / "data" / "general"
    (general / "storm_events").mkdir(parents=True)
    (project_dir / "data" / "transects").mkdir(parents=True)

    def empty_copy(src, dst, sheets, keep_columns=None):
        wb = load_workbook(src)
        for sheet in sheets:
            ws = wb[sheet]
            if ws.max_row > 1:
                ws.delete_rows(2, ws.max_row - 1)
            if keep_columns and ws.max_column > keep_columns:
                ws.delete_cols(keep_columns + 1, ws.max_column - keep_columns)
        wb.save(dst)

    example_general = EXAMPLE_DIR / "data" / "general"
    empty_copy(example_general / "transects_metadata.xlsx", general / "transects_metadata.xlsx", ["transects"])
    empty_copy(example_general / "piezometers.xlsx", general / "piezometers.xlsx", ["piezometers"])
    # timeseries: only the column 'datetime' (the other columns are the series of the example)
    empty_copy(example_general / "timeseries.xlsx", general / "timeseries.xlsx", ["timeseries"], keep_columns=1)
    empty_copy(general / "timeseries.xlsx", general / "timeseries.xlsx", ["series_info"])
    create_parameter_template(general / "model_parameters_TEMPLATE.xlsx")

    settings = (EXAMPLE_DIR / "project_settings.toml").read_text(encoding="utf-8")
    example_name = load_project(EXAMPLE_DIR).name
    settings = settings.replace("the example project 'Papendrecht'", f"the project '{name}'")
    settings = settings.replace(f'name = "{example_name}"', f'name = "{name}"')
    (project_dir / "project_settings.toml").write_text(settings, encoding="utf-8")
    (project_dir / "run.py").write_text(RUN_TEMPLATE.replace("{name}", name), encoding="utf-8")
    return load_project(project_dir)


def load_project(project_dir, settings_file="project_settings.toml"):
    """Load a project: its folder and settings.

    Parameters
    ----------
    project_dir : str or pathlib.Path
        Project folder.
    settings_file : str, optional
        Name of the settings file in the project folder. Optional: without
        it the defaults in `DEFAULT_SETTINGS` are used.

    Also sets the file format of the saved figures from the section
    [figures] (PNG by default), see `set_figure_format`.

    Returns
    -------
    Project
    """
    project_dir = Path(project_dir)
    path = project_dir / settings_file
    overrides = {}
    if path.exists():
        with open(path, "rb") as fh:
            overrides = tomllib.load(fh)
    settings = _merge(DEFAULT_SETTINGS, overrides)
    # File format of the saved figures (finalize_and_save) for this project
    set_figure_format(settings["figures"]["format"], settings["figures"]["dpi"])
    return Project(project_dir, settings)


# -----------------------------------------------------------------------------
# Transects metadata
# -----------------------------------------------------------------------------
def read_transects_table(metadata_file):
    """Read the transects metadata table (one row per transect)."""
    return pd.read_excel(metadata_file, dtype={"loc_storm_event": str, "transect": str})


def validate_transects_metadata(metadata, raise_errors=False):
    """Check the transects metadata table.

    Parameters
    ----------
    metadata : pandas.DataFrame
        Table from `read_transects_table` / `Project.metadata`.
    raise_errors : bool, optional
        Raise one error listing all problems. Default is False: the problems
        are returned, so one incomplete transect doesn't block the others.

    Returns
    -------
    list of str
        The problems found (empty if none).
    """
    problems = []
    missing = [c for c in METADATA_REQUIRED if c not in metadata.columns]
    if missing:
        problems.append(f"missing required columns: {missing}")
    if "transect" in metadata.columns:
        duplicated = metadata["transect"][metadata["transect"].duplicated()].tolist()
        if duplicated:
            problems.append(f"transect names occur more than once: {duplicated}")
        if metadata["transect"].isna().any():
            problems.append("empty transect name in one or more rows")
    for col in METADATA_REQUIRED[1:]:
        if col in metadata.columns and metadata[col].isna().any():
            empty = metadata.loc[metadata[col].isna(), "transect"].tolist()
            problems.append(f"column '{col}' is empty for: {empty}")
    for col in ("polder_level", "undisturbed_head", "width_river", "width_foreland", "width_hinterland"):
        if col in metadata.columns and not pd.api.types.is_numeric_dtype(metadata[col]):
            problems.append(f"column '{col}' must be numeric")
    if "farfield" in metadata.columns:
        wrong = metadata.loc[
            metadata["farfield"].notna() & ~metadata["farfield"].isin(FARFIELD_OPTIONS), "transect"
        ].tolist()
        if wrong:
            problems.append(f"column 'farfield' must be one of {FARFIELD_OPTIONS}; wrong for: {wrong}")
    xsec = ["x1_xsec", "y1_xsec", "x2_xsec", "y2_xsec"]
    if any(c in metadata.columns for c in xsec) and not all(c in metadata.columns for c in xsec):
        problems.append(f"cross-section line needs all of the columns {xsec}")
    if problems and raise_errors:
        raise ValueError("Problems in the transects metadata:\n- " + "\n- ".join(problems))
    return problems


def read_transect_metadata(metadata_file, transect_name):
    """Read the metadata of one transect from the metadata Excel file.

    Parameters
    ----------
    metadata_file : str or pathlib.Path
        Path to `transects_metadata.xlsx`.
    transect_name : str
        Name of the transect (value in column 'transect').

    Returns
    -------
    dict
        With keys:
          polder_level        : polder water level (e.g. m NAP)
          undisturbed_head    : undisturbed head in the aquifer below the polder (e.g. m NAP)
          loc_river           : name of the river level series
          loc_storm_event     : location id of the storm event ('waterstandsverloop') file
          L_river             : width of the river [m]
          L_foreland          : width of the foreland [m]
          L_hinterland        : width of the hinterland [m] (plotting only)
          farfield            : far-field reference, 'polder_level' (default) or 'undisturbed_head'

        The model period is not part of the metadata: it is chosen in notebook 51,
        from the figures of the complete series.
    """
    metadata = read_transects_table(metadata_file)
    rows = metadata[metadata["transect"] == transect_name]
    if rows.empty:
        raise ValueError(f"No metadata found for transect '{transect_name}' in '{metadata_file}'")
    row = rows.iloc[0]
    empty = [c for c in METADATA_REQUIRED if c not in row.index or pd.isna(row[c])]
    if empty:
        raise ValueError(f"Transect '{transect_name}': required metadata missing or empty: {empty}")

    def optional(col):
        return row[col] if col in row.index and pd.notna(row[col]) else None

    return {
        "polder_level": row["polder_level"],
        "undisturbed_head": row["undisturbed_head"],
        "loc_river": row["loc_river"],
        "loc_storm_event": optional("loc_storm_event"),
        "L_river": row["width_river"],
        "L_foreland": row["width_foreland"],
        "L_hinterland": row["width_hinterland"],
        "farfield": optional("farfield") or "polder_level",
    }


# -----------------------------------------------------------------------------
# Piezometers
# -----------------------------------------------------------------------------
PIEZOMETERS_REQUIRED = ["name", "transect", "x", "y", "screen_top", "screen_bottom", "modellayer", "x_crosssection"]
PIEZOMETERS_OPTIONAL = ["ground_level", "use_calibration", "source", "remark"]


def read_piezometer_table(path, sheet_name="piezometers"):
    """Read the piezometer locations from the Excel template and check them.

    Parameters
    ----------
    path : str or pathlib.Path
        Excel file (template `piezometers.xlsx`).
    sheet_name : str, optional
        Sheet with one row per piezometer (filter). Default is 'piezometers'.

    Returns
    -------
    pandas.DataFrame
    """
    df = pd.read_excel(path, sheet_name=sheet_name, dtype={"name": str, "transect": str})
    missing = [c for c in PIEZOMETERS_REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in '{path}': {missing}")
    duplicated = df["name"][df["name"].duplicated()].tolist()
    if duplicated:
        raise ValueError(f"Piezometer names occur more than once in '{path}': {duplicated}")
    for col in ("modellayer", "x_crosssection"):
        empty = df.loc[df[col].isna(), "name"].tolist()
        if empty:
            print(f"WARNING: no {col} for {len(empty)} piezometers (not usable in the model): {empty}")
    if "use_calibration" not in df.columns:
        df["use_calibration"] = 1
    df["use_calibration"] = df["use_calibration"].fillna(1).astype(int)
    return df


def check_piezometer_table(piezometers):
    """Piezometers whose columns for the model are not (correctly) filled in.

    Checks per filter:

    - `x_crosssection`: filled in (a number);
    - `modellayer`: filled in, a whole number of 0 or more;
    - `use_calibration`: 0 or 1 (an empty cell counts as 1).

    A filter without `x_crosssection` or `modellayer` can't be used in the
    model (notebooks 51 and 52). Filters with `use_calibration` = 0 still need
    both, because they are shown in the figures.

    Parameters
    ----------
    piezometers : pandas.DataFrame
        Piezometer table, e.g. from `read_piezometer_table`.

    Returns
    -------
    pandas.DataFrame
        One row per filter with a problem: name, transect, filter screen and
        a description of the problem in the column 'problem'. Empty if all
        filters are complete.
    """
    rows = []
    for _, row in piezometers.iterrows():
        problems = []
        if pd.isna(row.get("x_crosssection")):
            problems.append("x_crosssection is empty")
        layer = row.get("modellayer")
        if pd.isna(layer):
            problems.append("modellayer is empty")
        elif not (float(layer).is_integer() and float(layer) >= 0):
            problems.append(f"modellayer {layer} is not a whole number of 0 or more")
        use = row.get("use_calibration", 1)
        if pd.notna(use) and use not in (0, 1):
            problems.append(f"use_calibration {use} is not 0 or 1")
        if problems:
            rows.append({
                "name": row["name"],
                "transect": row["transect"],
                "screen_top": row.get("screen_top"),
                "screen_bottom": row.get("screen_bottom"),
                "problem": "; ".join(problems),
            })
    columns = ["name", "transect", "screen_top", "screen_bottom", "problem"]
    return pd.DataFrame(rows, columns=columns)


PIEZOMETERS_COLUMNS = [
    "name", "transect", "x", "y", "ground_level", "screen_top", "screen_bottom",
    "modellayer", "x_crosssection", "use_calibration", "source", "remark",
]


def add_piezometers(path, piezometers, sheet_name="piezometers"):
    """Add new piezometers to the piezometer table, without changing the rows that are there.

    Only piezometers whose `name` is not yet in the table are added, at the
    end of the sheet. Rows that are already there, with the values filled in
    by hand (`modellayer`, `x_crosssection`, `use_calibration`, `remark`),
    stay as they are, and so do the other sheets (e.g. 'explanation') and the
    layout. Columns of `piezometers` that the table doesn't have (e.g.
    `tube_nr`) are left out. If the file doesn't exist, it is created with the
    columns of the template (without the sheet 'explanation'). The file is
    only written if there are piezometers to add.

    Parameters
    ----------
    path : str or pathlib.Path
        Excel file with the piezometer table (`piezometers.xlsx`).
    piezometers : pandas.DataFrame
        Piezometers to add, with at least the column 'name', e.g. from
        `piezometer_table_from_obs`.
    sheet_name : str, optional
        Sheet with the piezometer table. Default is 'piezometers'.

    Returns
    -------
    pandas.DataFrame
        The rows that were added, with the columns of the table.
    """
    from openpyxl import Workbook, load_workbook

    path = Path(path)
    if path.exists():
        wb = load_workbook(path)
        ws = wb[sheet_name]
        header = [c.value for c in ws[1]]
        if "name" not in header:
            raise ValueError(f"No column 'name' in sheet '{sheet_name}' of '{path}'")
        i_name = header.index("name")
        existing = {
            str(row[i_name]) for row in ws.iter_rows(min_row=2, values_only=True) if row[i_name] is not None
        }
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = sheet_name
        header = list(PIEZOMETERS_COLUMNS)
        ws.append(header)
        existing = set()

    new = piezometers.copy()
    new["name"] = new["name"].astype(str)
    new = new[~new["name"].isin(existing)].drop_duplicates("name")
    new = new.reindex(columns=[c for c in header if c is not None])
    if new.empty:
        return new

    def value(v):
        if v is None or (not isinstance(v, str) and pd.isna(v)):
            return None
        return v.item() if isinstance(v, np.generic) else v

    for _, row in new.iterrows():
        ws.append([value(row[c]) if c is not None else None for c in header])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return new.reset_index(drop=True)


def write_piezometers(piezometers, gpkg_file, layer="piezometers", crs="EPSG:28992"):
    """Write the piezometers as point layer to the project geopackage.

    Parameters
    ----------
    piezometers : pandas.DataFrame
        With columns 'x' and 'y', e.g. from `read_piezometer_table`.
    gpkg_file : str or pathlib.Path
        Project geopackage; created if it doesn't exist. An existing layer
        with the same name is replaced.
    layer : str, optional
        Layer name. Default is 'piezometers'.
    crs : str, optional
        Coordinate reference system of x and y. Default is 'EPSG:28992'.

    The layer gets a default QGIS style: blue circles with the name as label
    (`set_layer_style`).

    Returns
    -------
    geopandas.GeoDataFrame
    """
    gdf = gpd.GeoDataFrame(
        piezometers, geometry=gpd.points_from_xy(piezometers["x"], piezometers["y"]), crs=crs
    )
    Path(gpkg_file).parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(gpkg_file, layer=layer, driver="GPKG")
    set_layer_style(gpkg_file, layer, point_style_qml("circle", "31,120,180", 2.5))
    return gdf


def write_river_gauges(gauges, gpkg_file, layer="river_gauges", crs="EPSG:28992"):
    """Write the river gauges as a separate point layer to the project geopackage.

    Parameters
    ----------
    gauges : pandas.DataFrame
        One row per gauge with columns 'name', 'x' and 'y', and e.g.
        'transects' (the transects that use the gauge) and 'source'.
    gpkg_file : str or pathlib.Path
        Project geopackage; created if it doesn't exist. Gauges that are
        already in the layer are replaced by the new rows with the same
        name; the other gauges are kept.
    layer : str, optional
        Layer name. Default is 'river_gauges'.
    crs : str, optional
        Coordinate reference system of x and y. Default is 'EPSG:28992'.

    The layer gets a default QGIS style that differs from the piezometers:
    dark red triangles with the name as label (`set_layer_style`).

    Returns
    -------
    geopandas.GeoDataFrame
        All gauges in the layer.
    """
    import pyogrio

    gdf = gpd.GeoDataFrame(gauges, geometry=gpd.points_from_xy(gauges["x"], gauges["y"]), crs=crs)
    if Path(gpkg_file).exists() and layer in pyogrio.list_layers(gpkg_file)[:, 0]:
        existing = gpd.read_file(gpkg_file, layer=layer).to_crs(crs)
        existing = existing[~existing["name"].isin(gdf["name"])]
        gdf = gpd.GeoDataFrame(pd.concat([existing, gdf], ignore_index=True), crs=crs)
    Path(gpkg_file).parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(gpkg_file, layer=layer, driver="GPKG")
    set_layer_style(gpkg_file, layer, point_style_qml("triangle", "180,30,30", 4.0))
    return gdf


def point_style_qml(shape="circle", color="31,120,180", size=2.5, label_field="name"):
    """QGIS style (QML) for a point layer: one marker for all points, with a label.

    Parameters
    ----------
    shape : str, optional
        QGIS marker shape, e.g. 'circle', 'triangle', 'square', 'diamond'.
    color : str, optional
        Fill colour as 'R,G,B'.
    size : float, optional
        Marker size [mm].
    label_field : str or None, optional
        Field shown as label; None: no label.

    Returns
    -------
    str
    """
    labeling = ""
    if label_field:
        labeling = (
            '  <labeling type="simple">\n'
            '    <settings calloutType="simple">\n'
            f'      <text-style fieldName="{label_field}" isExpression="0" fontSize="8" fontSizeUnit="Point" '
            'textColor="0,0,0,255" textOpacity="1">\n'
            '        <text-buffer bufferDraw="1" bufferSize="0.8" bufferSizeUnits="MM" '
            'bufferColor="255,255,255,255" bufferOpacity="1"/>\n'
            '      </text-style>\n'
            '      <placement placement="6" dist="1" distUnits="MM" quadOffset="2"/>\n'
            '      <rendering scaleVisibility="0" obstacle="1"/>\n'
            '    </settings>\n'
            '  </labeling>\n'
        )
    return (
        "<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n"
        f'<qgis version="3.34" styleCategories="Symbology|Labeling" labelsEnabled="{int(bool(label_field))}">\n'
        '  <renderer-v2 type="singleSymbol" symbollevels="0" forceraster="0" enableorderby="0" '
        'referencescale="-1">\n'
        "    <symbols>\n"
        '      <symbol type="marker" name="0" alpha="1" clip_to_extent="1" force_rhr="0">\n'
        '        <layer class="SimpleMarker" pass="0" enabled="1" locked="0">\n'
        '          <Option type="Map">\n'
        f'            <Option type="QString" name="name" value="{shape}"/>\n'
        f'            <Option type="QString" name="color" value="{color},255"/>\n'
        '            <Option type="QString" name="outline_color" value="0,0,0,255"/>\n'
        '            <Option type="QString" name="outline_style" value="solid"/>\n'
        '            <Option type="QString" name="outline_width" value="0.3"/>\n'
        '            <Option type="QString" name="outline_width_unit" value="MM"/>\n'
        f'            <Option type="QString" name="size" value="{size}"/>\n'
        '            <Option type="QString" name="size_unit" value="MM"/>\n'
        '            <Option type="QString" name="scale_method" value="diameter"/>\n'
        "          </Option>\n"
        "        </layer>\n"
        "      </symbol>\n"
        "    </symbols>\n"
        "  </renderer-v2>\n"
        f"{labeling}"
        "</qgis>\n"
    )


def set_layer_style(gpkg_file, layer, qml, name=None):
    """Store a QGIS style (QML) as the default style of a layer in a geopackage.

    QGIS reads the default style from the table `layer_styles` when the layer
    is added to a map. An existing default style of the layer is replaced.

    Parameters
    ----------
    gpkg_file : str or pathlib.Path
        Geopackage with the layer.
    layer : str
        Layer name.
    qml : str
        Style, e.g. from `point_style_qml`.
    name : str, optional
        Name of the style. Default: the layer name.
    """
    import sqlite3

    with sqlite3.connect(str(gpkg_file)) as conn:
        row = conn.execute(
            "SELECT column_name FROM gpkg_geometry_columns WHERE table_name = ?", (layer,)
        ).fetchone()
        geometry_column = row[0] if row else "geom"
        conn.execute(
            "CREATE TABLE IF NOT EXISTS layer_styles ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, f_table_catalog TEXT, f_table_schema TEXT, "
            "f_table_name TEXT, f_geometry_column TEXT, styleName TEXT, styleQML TEXT, styleSLD TEXT, "
            "useAsDefault INTEGER, description TEXT, owner TEXT, ui TEXT, "
            "update_time DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))"
        )
        conn.execute("DELETE FROM layer_styles WHERE f_table_name = ? AND useAsDefault = 1", (layer,))
        conn.execute(
            "INSERT INTO layer_styles (f_table_catalog, f_table_schema, f_table_name, f_geometry_column, "
            "styleName, styleQML, styleSLD, useAsDefault, description) VALUES ('', '', ?, ?, ?, ?, '', 1, ?)",
            (layer, geometry_column, name or layer, qml, "default style of timflow-levee-toolkit"),
        )
        conn.commit()


def read_piezometers(gpkg_file, transect_name, layer="piezometers"):
    """Read the piezometers of one transect from the project geopackage.

    Parameters
    ----------
    gpkg_file : str or pathlib.Path
        Path to `project_data.gpkg`.
    transect_name : str
        Name of the transect (value in column 'transect', or in the older
        column names 'aanduiding' or 'raai').
    layer : str, optional
        Layer with the piezometers. Default is 'piezometers'.

    Returns
    -------
    geopandas.GeoDataFrame
        All columns of the piezometers that belong to the transect.
    """
    piezometers = gpd.read_file(gpkg_file, layer=layer)
    for col in ("transect", "aanduiding", "raai"):
        if col in piezometers.columns:
            return piezometers[piezometers[col] == transect_name].copy()
    raise KeyError(
        f"No 'transect', 'aanduiding' or 'raai' column in layer '{layer}'. "
        f"Available columns: {piezometers.columns.tolist()}"
    )


def piezometer_table_from_obs(oc, transect):
    """Draft rows for the piezometer table from downloaded observations.

    Converts a hydropandas ObsCollection (e.g. from `hydropandas.read_bro`)
    to rows in the format of the piezometer template. The model layer and,
    if the transect has no cross-section origin, `x_crosssection` still have
    to be filled in.

    Parameters
    ----------
    oc : hydropandas.ObsCollection
        Downloaded observations with x, y and filter screen.
    transect : str
        Transect the piezometers belong to.

    Returns
    -------
    pandas.DataFrame
    """
    def column(name):
        return oc[name].values if name in oc.columns else None

    table = pd.DataFrame({
        "name": oc.index,
        "transect": transect,
        "x": column("x"),
        "y": column("y"),
        "ground_level": column("ground_level"),
        "tube_top": column("tube_top"),
        "tube_nr": column("tube_nr"),
        "screen_top": column("screen_top"),
        "screen_bottom": column("screen_bottom"),
        "modellayer": None,
        "x_crosssection": None,
        "use_calibration": 1,
        "source": column("source"),
    })
    return table
