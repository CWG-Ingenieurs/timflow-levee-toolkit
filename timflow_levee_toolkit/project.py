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

    def piezometers(self, transect):
        """Piezometers of one transect from the project geopackage."""
        return read_piezometers(
            self.general_file("project_data"), transect, layer=self.settings["paths"]["piezometer_layer"]
        )

    def open_pastastore(self, transect):
        """Open (or create) the pastastore of a transect."""
        import pastastore as pst

        conn = pst.PasConnector(self.settings["transect_folders"]["pastastore"], self.transect_dir(transect))
        return pst.PastaStore(conn)

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


def load_project(project_dir, settings_file="project_settings.toml"):
    """Load a project: its folder and settings.

    Parameters
    ----------
    project_dir : str or pathlib.Path
        Project folder.
    settings_file : str, optional
        Name of the settings file in the project folder. Optional: without
        it the defaults in `DEFAULT_SETTINGS` are used.

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
    return Project(project_dir, _merge(DEFAULT_SETTINGS, overrides))


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

    Returns
    -------
    geopandas.GeoDataFrame
    """
    gdf = gpd.GeoDataFrame(
        piezometers, geometry=gpd.points_from_xy(piezometers["x"], piezometers["y"]), crs=crs
    )
    Path(gpkg_file).parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(gpkg_file, layer=layer, driver="GPKG")
    return gdf


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
