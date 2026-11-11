"""Subsurface data that support filling in the geohydrological scheme:

- BRO cone penetration tests (CPT) and boreholes (BHR), and DINO borehole
  samples (GBO), with `brodata`;
- REGIS and GeoTOP along the cross-section line, with `nlmod`.

The functions are thin wrappers: each docstring names the `brodata` or
`nlmod` call it uses, so you can also call these packages directly (as
notebook 21 does for most steps). See https://github.com/ArtesiaWater/brodata
and https://nlmod.readthedocs.io.

`brodata` and `nlmod` are only needed for these functions (install the extra
`timflow_levee_toolkit[subsurface]`), so they are imported inside them.
"""

import logging
from contextlib import contextmanager
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

from .maps import add_basemap, square_extent


class _SkipUnsupportedTags(logging.Filter):
    """Skip brodata's warnings about XML tags it does not read ("Tag ... not supported").

    These tags are not needed for the locations, files and graphs; other warnings and errors are kept.
    """

    def filter(self, record):
        return not record.getMessage().startswith("Tag ")


@contextmanager
def quiet_brodata():
    """Hide the "Tag ... not supported" warnings of brodata within the block.

    brodata warns about every XML tag it does not read. These tags are not
    needed here; other warnings and errors are still shown.

    Examples
    --------
    >>> with tlt.quiet_brodata():
    ...     cpt = brodata.cpt.get_characteristics(extent=extent)
    """
    logger = logging.getLogger("brodata.util")
    skip = _SkipUnsupportedTags()
    logger.addFilter(skip)
    try:
        yield
    finally:
        logger.removeFilter(skip)


# -----------------------------------------------------------------------------
# BRO: CPTs, boreholes and monitoring wells
# -----------------------------------------------------------------------------
def get_bro_locations(extent):
    """Get the locations of BRO subsurface data within an extent.

    Wraps `brodata.cpt.get_characteristics`, `brodata.bhr.get_characteristics`,
    `brodata.gmw.get_characteristics` and `brodata.dino.get_boormonsterprofiel`
    (each with `extent=extent`). A data type that fails is reported and set to
    None, so it does not stop the others.

    Parameters
    ----------
    extent : sequence of float
        `[xmin, xmax, ymin, ymax]` [m, EPSG:28992].

    Returns
    -------
    dict
        GeoDataFrames (or None) for 'cpt' (cone penetration tests), 'bhr'
        (geotechnical boreholes), 'gmw' (groundwater monitoring wells) and
        'gbo' (DINO borehole samples), all in EPSG:28992.
    """
    import brodata

    getters = {
        "cpt": lambda: brodata.cpt.get_characteristics(extent=extent),
        "bhr": lambda: brodata.bhr.get_characteristics(extent=extent),
        "gmw": lambda: brodata.gmw.get_characteristics(extent=extent),
        "gbo": lambda: brodata.dino.get_boormonsterprofiel(extent=extent),
    }
    locations = {}
    for kind, get in getters.items():
        try:
            with quiet_brodata():
                locations[kind] = get()
        except Exception as e:  # a missing data type should not stop the others
            print(f"No {kind} locations: {type(e).__name__}: {e}")
            locations[kind] = None
        # The DINO samples come without a coordinate reference system; like the extent, they are in RD New
        gdf = locations[kind]
        if gdf is not None and hasattr(gdf, "set_crs") and gdf.crs is None:
            locations[kind] = gdf.set_crs(28992)
    return locations


def save_bro_locations(locations, gpkg_file):
    """Save the BRO locations to a geopackage, one layer per data type.

    Parameters
    ----------
    locations : dict
        From `get_bro_locations`.
    gpkg_file : str or pathlib.Path
        Geopackage to write; existing layers with the same name are replaced.
    """
    Path(gpkg_file).parent.mkdir(parents=True, exist_ok=True)
    for kind, gdf in locations.items():
        if gdf is not None and len(gdf) > 0:
            gdf.to_file(gpkg_file, layer=kind, driver="GPKG")
            print(f"{kind}: {len(gdf)} locations saved")


def plot_bro_locations(locations, extent, line=None, title=None, basemap=True, figsize=(8, 8)):
    """Map of the BRO locations, with labels.

    The map is square around the extent, with a margin of 3% of its long side on each
    side; the extent is drawn as a dashed outline. A cross-section line that extends
    beyond the map is cut off at its edge.

    Parameters
    ----------
    locations : dict
        From `get_bro_locations`.
    extent : sequence of float
        `[xmin, xmax, ymin, ymax]`: the extent of the transect in the metadata
        (`xmin_extent` .. `ymax_extent`), in which the BRO locations were searched.
    line : sequence of (x, y), optional
        Cross-section line to draw.
    title : str, optional
        Title of the map.
    basemap : bool, optional
        Add a background map with contextily (needs internet). Default True.
    figsize : tuple of float, optional
        Figure size. Default (8, 8).

    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes
    """
    styles = {
        "cpt": {"color": "red", "marker": "v", "label": "CPT"},
        "bhr": {"color": "saddlebrown", "marker": "o", "label": "borehole (BHR)"},
        "gbo": {"color": "green", "marker": "D", "label": "borehole sample (DINO)"},
        "gmw": {"color": "blue", "marker": "o", "label": "monitoring well (GMW)"},
    }
    fig, ax = plt.subplots(figsize=figsize)
    xmin, xmax, ymin, ymax = extent
    ax.plot([xmin, xmax, xmax, xmin, xmin], [ymin, ymin, ymax, ymax, ymin], "--", color="0.4", lw=0.8,
            label="extent")
    square_extent(ax, [xmin, xmax], [ymin, ymax], margin=0.03, min_size=0.0)
    ax.ticklabel_format(useOffset=False, style="plain")
    texts = []
    for kind, style in styles.items():
        gdf = locations.get(kind)
        if gdf is None or len(gdf) == 0:
            continue
        gdf.plot(ax=ax, markersize=20, **style)
        if kind != "gbo":
            for name, point in zip(gdf.index, gdf.geometry):
                texts.append(ax.text(point.x, point.y, str(name)[-7:], fontsize=7, color=style["color"],
                                     bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                                               edgecolor=style["color"], alpha=0.8)))
    if line is not None:
        xs, ys = zip(*line)
        ax.plot(xs, ys, "k-", linewidth=1, label="cross-section")
    if texts:
        from adjustText import adjust_text

        adjust_text(texts, ax=ax, arrowprops=dict(arrowstyle="->", color="gray", alpha=0.5))
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.legend(loc=(0, 1), frameon=False, ncol=3, fontsize="x-small")
    if title:
        ax.set_title(title, loc="right")
    if basemap:
        add_basemap(ax, crs=28992)
    return fig, ax


def suggest_z_limits(locations):
    """Suggest the vertical range of profiles from the BRO locations.

    Uses the highest ground level and the deepest end depth of the CPTs,
    boreholes and monitoring wells.

    Returns
    -------
    (float, float)
        `(z_min, z_max)` [m NAP], rounded outwards to whole metres.
    """
    tops, bottoms = [], []
    specs = {
        "cpt": ("offset", "finalDepth", None),
        "bhr": ("offset", "finalDepthBoring", None),
        "gmw": ("groundLevelPosition", None, "deepestScreenBottomPosition"),
    }
    for kind, (top_col, depth_col, bottom_col) in specs.items():
        gdf = locations.get(kind)
        if gdf is None or len(gdf) == 0 or top_col not in gdf.columns:
            continue
        top = gdf[top_col].astype(float)
        if bottom_col and bottom_col in gdf.columns:
            bottom = gdf[bottom_col].astype(float)
        elif depth_col and depth_col in gdf.columns:
            bottom = top - gdf[depth_col].astype(float)
        else:
            continue
        tops.append(top.max())
        bottoms.append(bottom.min())
    if not tops:
        return None
    return float(np.floor(np.nanmin(bottoms))), float(np.ceil(np.nanmax(tops)))


def download_cpt_graphs(cpt_locations, save_dir):
    """Download each CPT (XML) and its graph (SVG) from the BRO.

    Wraps `brodata.cpt.ConePenetrationTest.from_bro_id(bro_id, to_file=...)`
    and `brodata.cpt.graph(...)`. The combined graph against depth is used
    where available, otherwise the graph against length. Read a saved CPT with
    `brodata.cpt.ConePenetrationTest(xml_file)` and plot it with
    `brodata.plot.cone_penetration_test`.
    """
    import brodata

    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    for bro_id in cpt_locations.index:
        fname_xml = save_dir / f"{bro_id}.xml"
        with quiet_brodata():
            brodata.cpt.ConePenetrationTest.from_bro_id(bro_id, to_file=fname_xml)
        fname_svg = save_dir / f"{bro_id}_depth.svg"
        brodata.cpt.graph(fname_xml, graphType="cptCombinedDepth", to_file=fname_svg)
        if fname_svg.stat().st_size < 1024:  # no graph against depth available
            fname_svg.unlink()
            brodata.cpt.graph(fname_xml, graphType="cptCombinedLength", to_file=save_dir / f"{bro_id}_length.svg")
    print(f"{len(cpt_locations)} CPTs downloaded to {save_dir}")


def download_bhr_graphs(bhr_locations, save_dir, z_limits):
    """Download each geotechnical borehole (XML) and its log (SVG) from the BRO.

    Wraps `brodata.bhr.GeotechnicalBoreholeResearch.from_bro_id(bro_id, to_file=...)`
    and `brodata.bhr.bhrgt_graph(...)`. Read a saved borehole with
    `brodata.bhr.GeotechnicalBoreholeResearch(xml_file)` and plot it with
    `brodata.plot.descriptive_borehole_log`.

    Parameters
    ----------
    bhr_locations : geopandas.GeoDataFrame
        From `get_bro_locations(...)["bhr"]`.
    save_dir : str or pathlib.Path
        Folder for the files.
    z_limits : (float, float)
        `(z_min, z_max)` [m NAP] of the logs, e.g. from `suggest_z_limits`.
    """
    import brodata

    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    no_graph = []
    for bro_id in bhr_locations.index:
        fname_xml = save_dir / f"{bro_id}.xml"
        fname_svg = save_dir / f"{bro_id}.svg"
        with quiet_brodata():
            brodata.bhr.GeotechnicalBoreholeResearch.from_bro_id(bro_id, to_file=fname_xml)
        brodata.bhr.bhrgt_graph(fname_xml, to_file=fname_svg, asNAP=True,
                                topNap=z_limits[1], bottomNap=z_limits[0])
        # The BRO service returns an error message instead of a graph when it fails
        if "<svg" not in fname_svg.read_text(encoding="utf-8", errors="ignore"):
            fname_svg.unlink()
            no_graph.append(bro_id)
    print(f"{len(bhr_locations)} boreholes downloaded to {save_dir}")
    if no_graph:
        print(f"No log (SVG) from the BRO service for: {', '.join(no_graph)}")


def plot_dino_lithology(gbo_locations, line, ax=None):
    """Lithology of the DINO borehole samples along the cross-section line.

    Wraps `brodata.plot.lithology_along_line(gbo_locations, line, kind="dino")`.
    """
    import brodata

    if ax is None:
        _, ax = plt.subplots(figsize=(10, 6))
    brodata.plot.lithology_along_line(gbo_locations, line, ax=ax, kind="dino")
    ax.set_xlabel("distance along the cross-section [m]")
    ax.set_ylabel("z [m NAP]")
    return ax


# -----------------------------------------------------------------------------
# REGIS and GeoTOP
# -----------------------------------------------------------------------------
def extent_around_line(line, margin=100.0):
    """`[xmin, xmax, ymin, ymax]` of a line plus a margin [m]."""
    xs, ys = zip(*line)
    return [min(xs) - margin, max(xs) + margin, min(ys) - margin, max(ys) + margin]


def combined_layer_model(extent, geotop, regis_botm_layer="MSz1", geotop_layers=("HLc",)):
    """Layer model of REGIS with the Holocene layers replaced by GeoTOP.

    The same as `nlmod.read.regis.get_combined_layer_models(extent,
    regis_botm_layer, geotop_layers=...)`, but with an already downloaded
    GeoTOP and with the REGIS layer names as object: with pandas >= 3, xarray
    cannot concatenate the string dtype of REGIS with GeoTOP (nlmod 0.11).

    Parameters
    ----------
    extent : sequence of float
        `[xmin, xmax, ymin, ymax]`.
    geotop : xarray.Dataset
        GeoTOP, from `nlmod.read.geotop.download_geotop(extent)`.
    regis_botm_layer : str, optional
        Deepest REGIS layer of the combined model. Default 'MSz1'.
    geotop_layers : sequence of str, optional
        REGIS layers replaced by GeoTOP. Default ('HLc',).

    Returns
    -------
    xarray.Dataset
    """
    import nlmod

    regis_layers = nlmod.read.regis.download_regis(extent, regis_botm_layer)
    regis_layers = regis_layers.assign_coords(layer=regis_layers.layer.values.astype(object))
    return nlmod.read.regis.add_geotop_to_regis_layers(regis_layers, geotop, layers=list(geotop_layers))


def download_regis_geotop(extent, regis_botm_layer="MSz1", geotop_layers=("HLc",)):
    """Download REGIS, the combined REGIS-GeoTOP layer model and GeoTOP.

    Wraps `nlmod.read.regis.download_regis`, `nlmod.read.geotop.download_geotop`
    and `combined_layer_model`.

    Parameters
    ----------
    extent : sequence of float
        `[xmin, xmax, ymin, ymax]`.
    regis_botm_layer : str, optional
        Deepest REGIS layer of the combined model. Default 'MSz1'.
    geotop_layers : sequence of str, optional
        REGIS layers replaced by GeoTOP in the combined model. Default ('HLc',).

    Returns
    -------
    dict
        xarray Datasets 'regis', 'combined' and 'geotop'.
    """
    import nlmod

    regis = nlmod.read.regis.download_regis(
        extent, variables=["top", "botm", "kh", "kv", "kD", "c"], drop_layer_dim_from_top=False
    )
    geotop = nlmod.read.geotop.download_geotop(extent, probabilities=True)
    combined = combined_layer_model(extent, geotop, regis_botm_layer, geotop_layers)
    return {"regis": regis, "combined": combined, "geotop": geotop}


def plot_layer_models(ds1, line, ds2=None, zmin=-30, zmax=5, title1="REGIS", title2="REGIS + GeoTOP",
                      min_label_area=1000):
    """Cross-section of one or two layer models (e.g. REGIS and the combined model).

    Wraps `nlmod.plot.DatasetCrossSection` with `plot_layers` and `plot_grid`,
    in the colours of `nlmod.read.regis.get_legend(kind="combined")`.
    """
    import nlmod
    from nlmod.plot import DatasetCrossSection

    colors = nlmod.read.regis.get_legend(kind="combined")["color"].to_dict()
    nrows = 1 if ds2 is None else 2
    fig, axes = plt.subplots(nrows, 1, figsize=(14, 6 * nrows), sharex=True, squeeze=False)
    for ax, ds, title in zip(axes[:, 0], (ds1, ds2), (title1, title2)):
        if ds is None:
            continue
        cs = DatasetCrossSection(ds, line=line, ax=ax, zmin=zmin, zmax=zmax)
        cs.plot_layers(colors=colors, min_label_area=min_label_area)
        cs.plot_grid(linewidth=0.5, vertical=False)
        ax.set_ylabel("z [m NAP]")
        ax.set_title(title, loc="right")
    axes[-1, 0].set_xlabel("distance along the cross-section [m]")
    return fig, axes[:, 0]


def plot_geotop_lithology(geotop, line, zmin=-30, zmax=5):
    """GeoTOP lithology class along the cross-section line.

    Wraps `nlmod.plot.geotop_lithok_in_cross_section(line, geotop)`.
    """
    import nlmod

    fig, ax = plt.subplots(figsize=(10, 5))
    nlmod.plot.geotop_lithok_in_cross_section(line, geotop, ax=ax)
    ax.set_ylim(zmin, zmax)
    ax.set_xlabel("distance along the cross-section [m]")
    ax.set_ylabel("z [m NAP]")
    return fig, ax


def plot_geotop_conductivity(geotop, line, variable="kh", zmin=-30, zmax=5, as_layers=False):
    """Hydraulic conductivity from GeoTOP (default values per lithology class) along the line.

    Wraps `nlmod.read.geotop.add_kh_and_kv(geotop, nlmod.read.geotop.get_lithok_props())`
    and `nlmod.plot.DatasetCrossSection(...).plot_array(...)`.

    Parameters
    ----------
    geotop : xarray.Dataset
        GeoTOP from `download_regis_geotop`.
    line : sequence of (x, y)
        Cross-section line.
    variable : str, optional
        'kh' or 'kv'. Default 'kh'.
    zmin, zmax : float, optional
        Vertical range [m NAP].
    as_layers : bool, optional
        Show GeoTOP converted to model layers (with layer names) instead of
        the voxels. Default False.
    """
    import nlmod

    props = nlmod.read.geotop.get_lithok_props()
    gt = nlmod.read.geotop.add_kh_and_kv(geotop, props)
    layer = "z"
    if as_layers:
        gt = nlmod.read.geotop.to_model_layers(gt)
        layer = "layer"
    cmap = plt.get_cmap("turbo_r")
    norm = matplotlib.colors.BoundaryNorm([0.0001, 0.001, 0.01, 0.1, 1, 5, 10, 20, 50, 100], cmap.N)
    fig, ax = plt.subplots(figsize=(10, 5))
    cs = nlmod.plot.DatasetCrossSection(gt, line, layer=layer, ax=ax, zmin=zmin, zmax=zmax)
    pc = cs.plot_array(gt[variable], norm=norm, cmap=cmap)
    if as_layers:
        cs.plot_layers(alpha=0.0, min_label_area=1000.0)
        cs.plot_grid(vertical=False)
    nlmod.plot.colorbar_inside(pc, bounds=[0.05, 0.05, 0.02, 0.9],
                               format=matplotlib.ticker.FuncFormatter(lambda y, _: f"{y:g}"))
    nlmod.plot.title_inside(f"{variable} [m/d]", ax=ax)
    ax.set_xlabel("distance along the cross-section [m]")
    ax.set_ylabel("z [m NAP]")
    return fig, ax


def regis_profile(regis, x, y):
    """REGIS layers at one point, as a table (e.g. the middle of the cross-section).

    Parameters
    ----------
    regis : xarray.Dataset
        REGIS from `download_regis_geotop`.
    x, y : float
        Coordinates [m, EPSG:28992]; the nearest REGIS cell is used.

    Returns
    -------
    pandas.DataFrame
        Indexed by REGIS layer, one row per layer that is present at the point
        (thickness > 0), with the columns (if available in `regis`)
        'top [m NAP]', 'bottom [m NAP]', 'thickness [m]', 'kh [m/d]',
        'kv [m/d]', 'kD [m2/d]' and 'c [d]'. Empty values (e.g. no kh in an
        aquitard) are NaN.
    """
    point = regis.sel(x=x, y=y, method="nearest")
    df = point.to_dataframe()
    columns = [c for c in ("top", "botm", "kh", "kv", "kD", "c") if c in df.columns]
    df = df[columns]
    if {"top", "botm"} <= set(df.columns):
        df = df[(df["top"] - df["botm"]) > 0]
        df.insert(2, "thickness", df["top"] - df["botm"])
    df = df.rename(columns={"top": "top [m NAP]", "botm": "bottom [m NAP]", "thickness": "thickness [m]",
                            "kh": "kh [m/d]", "kv": "kv [m/d]", "kD": "kD [m2/d]", "c": "c [d]"})
    df.index.name = "REGIS layer"
    return df
