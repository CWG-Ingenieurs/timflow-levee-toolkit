# Workflow notebooks

The notebooks work on a **project** with one or more **transects** (cross-sections through a levee).
The project folder is set in the second cell of each notebook (`project_dir`); by default the
example project `examples/papendrecht` is used. Notebooks that work on one transect have a cell
`transect_name` (tagged `parameters`, so they can also be run for all transects with papermill).

## Installation

The functions used by the notebooks are in the package `timflow_levee_toolkit` (folder
`timflow_levee_toolkit/` in the repository root). Install it once in your Python environment,
from the repository root:

```
pip install -e .                    # or: uv pip install -e .
pip install -e ".[download]"        # also hydropandas, for notebooks 11 and 12
pip install -e ".[subsurface]"      # also nlmod and brodata, for notebook 21
```

With `-e` (editable) changes to the package are used directly, without installing again. In the
notebooks the package is imported as `import timflow_levee_toolkit as tlt`; all functions are
available at the top level (e.g. `tlt.load_project`, `tlt.plot_xsection`). The package consists of
the modules:

| Module | Contents |
|---|---|
| `project` | project settings, transects metadata, piezometer tables, geopackage |
| `timeseries` | importing observed series into a pastastore, selecting, summarizing and plotting them |
| `model` | Timflow cross-section models: geohydrological scheme (Excel), plots of the model and results, storm events |
| `response` | response factors, flow resistance, leakage lengths |
| `subsurface` | BRO CPTs and boreholes, REGIS and GeoTOP |
| `output` | saving figures (`finalize_and_save`) and tables (`export_to_excel`) |

## Route

| Step | Notebook | Path | Input | Output |
|---|---|---|---|---|
| 0 | [`00 Set up project`](00%20Set%20up%20project.ipynb) | minimal | `transects_metadata.xlsx` | folders per transect |
| 1 | [`01 Piezometer locations`](01%20Piezometer%20locations.ipynb) | minimal | `piezometers.xlsx` | `project_data.gpkg` |
| 2 | [`10 Import time series from Excel`](10%20Import%20time%20series%20from%20Excel.ipynb) | minimal | `timeseries.xlsx` | pastastore per transect |
| 2 | [`11 Download BRO groundwater levels`](11%20Download%20BRO%20groundwater%20levels.ipynb) | optional | rectangle per transect | pastastore per transect, `piezometers_from_bro.xlsx` |
| 2 | [`12 Download river levels (Rijkswaterstaat)`](12%20Download%20river%20levels%20%28Rijkswaterstaat%29.ipynb) | optional | `loc_river` per transect | pastastore per transect |
| 2 | [`15 Overview of measurements`](15%20Overview%20of%20measurements.ipynb) | optional | pastastore | overview table and figures |
| 3 | [`20 Geohydrological scheme`](20%20Geohydrological%20scheme.ipynb) | minimal | `model_parameters_<transect>.xlsx` | checked scheme |
| 3 | [`21 Subsurface data`](21%20Subsurface%20data.ipynb) | optional | rectangle and cross-section line | BRO CPTs and boreholes, REGIS and GeoTOP |
| 4 | [`51 Prepare model inputs`](51%20Prepare%20model%20inputs.ipynb) | minimal | pastastore, metadata | `observations_model_period.xlsx` |
| 5 | [`52 Timflow model`](52%20Timflow%20model.ipynb) | minimal (storm event optional) | all of the above | calibrated parameters, figures, response factors, `model_summary.xlsx` |
| 6 | [`60 Summary over transects`](60%20Summary%20over%20transects.ipynb) | optional | results of notebook 52 | tables and figures over all transects |

Notebooks 11 and 12 are alternatives or additions to notebook 10. After notebook 11, copy the rows
you need from `piezometers_from_bro.xlsx` to `piezometers.xlsx`, fill in `modellayer` and
`x_crosssection` (by hand), and run notebook 01 again.

## Project folder

A project folder contains `project_settings.toml` (optional: folder names, file names and units;
see `examples/papendrecht/project_settings.toml` for all settings) and the input data. The
default layout:

```
<project>/
├── project_settings.toml
├── results/                           (created by notebook 60)
└── data/
    ├── general/
    │   ├── transects_metadata.xlsx
    │   ├── piezometers.xlsx
    │   ├── timeseries.xlsx
    │   ├── project_data.gpkg              (created by notebook 01)
    │   ├── piezometers_from_bro.xlsx      (created by notebook 11)
    │   └── storm_events/storm_event_<id>.xlsx
    └── transects/<transect>/
        ├── model_parameters_<transect>.xlsx
        ├── pastastore/                    (created by notebook 10, 11 or 12)
        ├── subsurface/                    (created by notebook 21)
        ├── timeseries/                    (created by notebook 51)
        ├── results_intermediate/
        └── results_final/
```

## Why is the model notebook not split further?

Notebook 52 builds the models, calibrates them and uses the calibrated models for the analysis and
the storm event. Splitting it requires saving and loading the calibrated models. Once Timflow can
do that (JSON, see [PR #171](https://github.com/timflow-org/timflow/pull/171)), notebook 52 can be
split into separate notebooks for calibration, analysis and the storm event.
