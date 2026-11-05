# timflow-levee-toolkit

Groundwater analysis of levees with Timflow cross-section models: project set-up, time series,
model calibration, response factors and the heads during a storm event.

The notebooks below are executed on the example project (Papendrecht, two transects) when the
documentation is built. The optional notebooks 11, 12, 15 and 21 download data from external
services (BRO, Rijkswaterstaat, PDOK, REGIS and GeoTOP): to keep the load on these services low, they
are executed only for the documentation of releases (version 'stable'); in 'latest' (the development
branch) they are shown without outputs.

```{toctree}
:caption: Introduction
:maxdepth: 1

/README
/notebooks/README
/examples/papendrecht/README
```

```{toctree}
:caption: Workflow notebooks
:maxdepth: 1

/notebooks/00 Set up project
/notebooks/01 Piezometer locations
/notebooks/10 Import time series from Excel
/notebooks/11 Download BRO groundwater levels
/notebooks/12 Download river levels (Rijkswaterstaat)
/notebooks/15 Overview of measurements
/notebooks/20 Geohydrological scheme
/notebooks/21 Subsurface data
/notebooks/51 Prepare model inputs
/notebooks/52 Timflow model
/notebooks/60 Summary over transects
```
