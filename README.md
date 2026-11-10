# timflow-levee-toolkit

[![version](https://img.shields.io/badge/version-0.1.2-blue)](https://github.com/CWG-Ingenieurs/timflow-levee-toolkit/releases)
[![documentation](https://readthedocs.org/projects/timflow-levee-toolkit/badge/?version=stable)](https://timflow-levee-toolkit.readthedocs.io/en/stable/)

Piezometer analysis of levees with Timflow.

Documentation, with the notebooks executed on the example project:
[timflow-levee-toolkit.readthedocs.io](https://timflow-levee-toolkit.readthedocs.io/en/stable/)
(`stable`: the latest release; `latest`: the development branch `dev`).

Workflow and Python toolkit to derive the geohydrological properties of a levee from piezometer
measurements, with transient cross-section models in [Timflow](https://github.com/timflow-org/timflow).
The calibrated models give the response of the groundwater heads to the river level (response factors,
leakage factors, flow resistances) and the heads during a design storm event.

The toolkit was developed for the piezometer analysis of the levees in the Alblasserwaard
(Waterschap Rivierenland; CWG Ingenieurs), but the workflow is generic: one project with any number
of transects.

## Method in short

For each transect (a cross-section through the levee, perpendicular to the river):

1. Piezometer series and the river level are collected for a short period with clear tidal
   fluctuations, typically about one week.
2. A geohydrological scheme (aquifers and aquitards, for the river, foreland and hinterland) is
   set up as a Timflow cross-section model.
3. The model is calibrated on the observed heads (transmissivity, resistance, storage).
4. The calibrated model gives response factors along the cross-section: steady state, tidal
   and for the design hydrograph (MHW: the storm event, with the *maatgevende hoogwaterstand* as its peak).
   Leakage lengths of foreland and hinterland are fitted to these, following the
   *Technisch Rapport Waterspanningen bij Dijken* (TAW, 2004).
5. The heads during a storm event (river level of a given return period) are calculated.

## Getting started

Requirements: Python 3.11 or newer. Timflow is installed from its `main` branch on GitHub
(`timflow-org/timflow`), because the toolkit uses recent features of the transient cross-section models.

```
git clone https://github.com/CWG-Ingenieurs/timflow-levee-toolkit.git
cd timflow-levee-toolkit
pip install -e ".[download,subsurface]"     # or: uv pip install -e ".[download,subsurface]"
```

The extras are optional. `download` adds hydropandas, for downloading BRO and Rijkswaterstaat
data. `subsurface` adds nlmod and brodata, for CPTs, boreholes, REGIS and GeoTOP.

Then open the notebooks in [`notebooks/`](notebooks/README.md) and run them in order. By default
they use the example project [`examples/papendrecht`](examples/papendrecht/README.md): two transects
along the Beneden-Merwede, with public BRO and Rijkswaterstaat data from one week in December 2025.
The minimal path runs offline.

## Workflow

| Step | Notebook | Required |
|---|---|---|
| 0 | `00 Set up project` | yes |
| 1 | `01 Piezometer locations` | yes |
| 2 | `10 Import time series from Excel`, or `11 Download BRO groundwater levels` and `12 Download river levels (Rijkswaterstaat)` | yes (Example uses Excel) |
| | `15 Overview of measurements` | optional |
| 3 | `20 Geohydrological scheme` | yes |
| | `21 Subsurface data` | optional |
| 4 | `51 Prepare model inputs` | yes |
| 5 | `52 Timflow model`: model, calibration, response factors, storm event | yes |
| 6 | `60 Summary over transects` | optional |

See [`notebooks/README.md`](notebooks/README.md) for the input and output of each step and the
layout of a project folder.

## Your own project

A project is a folder with a `project_settings.toml` (optional) and the input in Excel:

- `transects_metadata.xlsx`: one row per transect, with the polder level, undisturbed head, river
  gauge, and widths of river, foreland and hinterland. The model period is not part of it: you choose
  it in notebook 51, from the figures of the complete series.
- `piezometers.xlsx`: one row per piezometer filter, with transect, coordinates, filter screen,
  model layer and x in the cross-section (given by hand).
- `timeseries.xlsx`: heads and river levels, one column per series. Instead of this file, you can
  download the series from BRO and Rijkswaterstaat with notebooks 11 and 12.
- `model_parameters_<transect>.xlsx`: the geohydrological scheme per transect.
- Optional: `storm_event_<id>.xlsx`, a river level scenario per location.

Copy the example project as a template: each Excel file has a sheet `explanation` describing its
columns. Then set `project_dir` in the notebooks to your project folder. The project folder can be
anywhere, e.g. in its own repository; it only holds data and results, the code stays here.

## Repository layout

```
├── timflow_levee_toolkit/   the Python package (import timflow_levee_toolkit as tlt)
├── notebooks/               the workflow notebooks
└── examples/papendrecht/    example project with public data
```

The package has the modules `project`, `timeseries`, `model`, `response`, `subsurface` and
`output`. All public functions are also available at the top level, e.g. `tlt.load_project`.

## Development

Install with the test dependencies and run the tests from the repository root:

```
pip install -e ".[test]"
pytest -m "not slow"      # unit tests, a few seconds
pytest -m slow            # runs notebooks 00-52 on a copy of the example (about 2 minutes)
ruff check timflow_levee_toolkit tests
```

GitHub Actions runs ruff and the unit tests on every push and pull request. The example notebooks run once a week and on request (*Actions → tests → Run workflow*), because they download background maps from OpenStreetMap; run them before merging a change to the notebooks.
Once a month (and on request, *Actions → security audit → Run workflow*) the dependencies are checked for
known vulnerabilities with `pip-audit`: a fix for a direct dependency is proposed as a pull request (raised
minimum version in `pyproject.toml`); other findings are reported in an issue with the label `security`.

The version is set in `__version__` in `timflow_levee_toolkit/__init__.py`, and each release is tagged
(`v0.1.0`, ...). The version badge at the top of this README is static (the repository is private): update it
together with `__version__`; a test checks that they match. The notebooks print the version, so the executed notebooks record which version
produced the results. To reproduce results of a project, check out the tag in your clone (`git checkout v0.1.0`).

## Status and limitations

- Calibration, analysis and storm event share one notebook (52), because calibrated Timflow models
  cannot yet be saved and loaded in an efficient way. Once that is possible
  (see discussion at [timflow PR #171](https://github.com/timflow-org/timflow/pull/171)), the notebook can be split.
- Some plot functions are copies of functionality proposed for Timflow itself (e.g. PR #191).
  These might be moved to Timflow and then removed here.
- The calibration parameters are set in notebook 52; the example uses the set of the Papendrecht
  transects (two aquifers). Adapt it to the geohydrological scheme of each transect.

## Conventions

- Heads and water levels in m+ref (m NAP); coordinates in RD New (EPSG:28992).
- Times without time zone, in Dutch winter time (UTC+1).
- In the model, x = 0 is the boundary between foreland and hinterland (usually the inner toe of the
  levee). The river is at negative x and the hinterland at positive x.

## License

The code, the notebooks and the geohydrological schemes of the example (created by CWG Ingenieurs from
an interpretation of REGIS and soil investigations) are licensed under the [MIT License](LICENSE).

The other example data keep the terms of their source: open data from the BRO (groundwater levels) and
Rijkswaterstaat (river levels), and storm events created with the
[Waterstandsverlopen tool](https://iplo.nl/thema/water/applicaties-modellen/waterveiligheidsmodellen/waterstandsverlopen-tool/);
see [`examples/papendrecht/README.md`](examples/papendrecht/README.md).
