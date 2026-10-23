# Example project: Papendrecht

A complete, small example of the workflow: two transects (cross-sections) through the levee
along the Beneden-Merwede at Papendrecht, with the river level at Dordrecht, for one week
(1-8 December 2025).

| Transect | Location | Piezometer filters | Storm event |
|---|---|---|---|
| `Papendrecht West` | Papendrecht | 6 (one not used in the calibration) | `storm_event_308113.xlsx` |
| `Papendrecht East` | Papendrecht, near the Merwede bridge | 6 | `storm_event_303520.xlsx` |

All input is included, so the minimal path runs offline.

## Run the example

Open the notebooks in the folder `notebooks/` of the repository and run them in this order.
They use this example by default (`project_dir` in the second cell). Notebooks 51 and 52 work on
one transect: set `transect_name` to `Papendrecht West` or `Papendrecht East`, and run them for each transect.

| Step | Notebook | What it does |
|---|---|---|
| 0 | `00 Set up project` | checks the transects metadata and creates the folders |
| 1 | `01 Piezometer locations` | reads the piezometers and writes the geopackage |
| 2 | `10 Import time series from Excel` | imports the time series into the pastastore of each transect |
| 3 | `20 Geohydrological scheme` | checks the geohydrological scheme (model parameters) |
| 4 | `51 Prepare model inputs` | selects the model period and prepares the observations |
| 5 | `52 Timflow model` | builds and calibrates the Timflow model, response factors, storm event |
| | `60 Summary over transects` | optional: combines the results of both transects |

The optional notebooks 11, 12, 15 and 21 (downloads, overview, subsurface data) also work on the
example, but need an internet connection.

## Input files

| File | Contents |
|---|---|
| `project_settings.toml` | folder and file names, units (all settings listed, all optional) |
| `data/general/transects_metadata.xlsx` | one row per transect: polder level, undisturbed head, river gauge, widths, model period, rectangle and cross-section line |
| `data/general/piezometers.xlsx` | one row per piezometer filter: transect, coordinates, filter screen, model layer, x in the cross-section |
| `data/general/timeseries.xlsx` | observed heads and river level, one column per series |
| `data/general/storm_events/storm_event_<id>.xlsx` | storm events ('waterstandsverloop') at locations 308113 and 303520, return period 30,000 years (see the header of the files) |
| `data/transects/<transect>/model_parameters_<transect>.xlsx` | geohydrological scheme: tab `initial` |

Each Excel file has a sheet `explanation` describing its columns. Use them as templates for your own project.

The x-coordinate of each piezometer in the cross-section (`x_crosssection`) is entered by hand: the
distance from the boundary between foreland and hinterland (usually the inner toe of the levee),
positive towards the hinterland. In a real levee the piezometers are rarely on a straight line, so
this is a choice of the modeller.

Files created by the notebooks (geopackage, pastastore, results, downloads) are not stored in the repository.

## Conventions

- Heads and water levels in m NAP; coordinates in RD New (EPSG:28992).
- Times without time zone, in Dutch winter time (UTC+1). This is the convention of hydropandas
  for BRO and Rijkswaterstaat data.
- In the model, x = 0 is the boundary between foreland and hinterland (the inner toe of the levee);
  the river is at negative x.

## Data sources

- Groundwater levels: [BRO](https://www.broloket.nl) (Basisregistratie Ondergrond), downloaded
  with [hydropandas](https://github.com/ArtesiaWater/hydropandas) 0.20.2.
- River level Dordrecht: Rijkswaterstaat, via Matroos, downloaded with hydropandas.

BRO and Rijkswaterstaat data are open data. Check the terms of use of the sources before reusing the data.
