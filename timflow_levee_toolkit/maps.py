"""Background maps for map figures (needs internet)."""

# Tile servers can refuse requests without a User-Agent that identifies the application
# (OpenStreetMap then returns 'Access blocked' tiles).
USER_AGENT = "timflow-levee-toolkit (+https://github.com/CWG-Ingenieurs/timflow-levee-toolkit)"

# Background maps by name: (tile URL in web mercator, attribution)
BASEMAPS = {
    "osm": ("https://tile.openstreetmap.org/{z}/{x}/{y}.png", "© OpenStreetMap contributors"),
    "brt": ("https://service.pdok.nl/brt/achtergrondkaart/wmts/v2_0/standaard/EPSG:3857/{z}/{x}/{y}.png",
            "Kaartgegevens © Kadaster"),
    "brt_grey": ("https://service.pdok.nl/brt/achtergrondkaart/wmts/v2_0/grijs/EPSG:3857/{z}/{x}/{y}.png",
                 "Kaartgegevens © Kadaster"),
}


def add_basemap(ax, crs, source="osm", alpha=1.0, zoom="auto"):
    """Add a background map to a map figure, with contextily.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Axes with the data plotted; the map covers the current axis limits, so set
        the limits (e.g. with `ax.margins`) before calling this function.
    crs : str or int
        Coordinate reference system of the data, e.g. `project.crs` or 28992.
    source : str or xyzservices.TileProvider, optional
        A name from `BASEMAPS`: 'osm' (OpenStreetMap, default), 'brt' (topographic map of
        the Netherlands from PDOK, Kadaster) or 'brt_grey' (the same in grey); or a
        contextily provider or tile URL.
    alpha : float, optional
        Transparency of the map. Default 1.
    zoom : int or 'auto', optional
        Zoom level of the tiles. Default 'auto'.

    Returns
    -------
    bool
        True if the map was added; False (with a message) if not, e.g. without internet.
    """
    url, attribution = BASEMAPS.get(source, (source, None)) if isinstance(source, str) else (source, None)
    try:
        import contextily as ctx

        ctx.add_basemap(ax, crs=crs, source=url, attribution=attribution, alpha=alpha, zoom=zoom,
                        headers={"User-Agent": USER_AGENT}, zorder=0)
        return True
    except Exception as e:
        print(f"No background map ({type(e).__name__}: {e})")
        return False


def square_extent(ax, x, y, margin=0.3, min_size=100.0):
    """Set square axis limits around the points `x`, `y`, with a margin for the surroundings.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    x, y : array_like
        Coordinates to show, e.g. of the piezometers and the cross-section line.
    margin : float, optional
        Extra space on each side, as a fraction of the size of the points. Default 0.3.
    min_size : float, optional
        Minimum width and height [m], so a single point still shows its surroundings.
        Default 100.
    """
    xmin, xmax, ymin, ymax = min(x), max(x), min(y), max(y)
    half = max(xmax - xmin, ymax - ymin, min_size) * (0.5 + margin)
    xc, yc = (xmin + xmax) / 2, (ymin + ymax) / 2
    ax.set_xlim(xc - half, xc + half)
    ax.set_ylim(yc - half, yc + half)
    ax.set_aspect("equal")


def plot_transect_map(piezometers, line=None, crs=28992, source="osm", title=None, figsize=(7, 7)):
    """Map of the piezometers of one transect, with the cross-section line and a background map.

    One label per well (filters of the same well have the same location), with the name and
    the x-coordinate in the cross-section; overlapping labels are moved apart.

    Parameters
    ----------
    piezometers : pandas.DataFrame
        Piezometers of one transect, with columns 'name', 'x', 'y' and 'x_crosssection',
        e.g. from `Project.piezometers`.
    line : sequence of (x, y), optional
        Cross-section line `[(x1, y1), (x2, y2)]`, river side first, e.g. from
        `Project.crosssection`.
    crs : str or int, optional
        Coordinate reference system of the coordinates. Default 28992 (RD New).
    source : str, optional
        Background map, see `add_basemap`. Default 'osm'.
    title : str, optional
        Title above the map, on the right.
    figsize : tuple of float, optional
        Default (7, 7).

    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes
    """
    import matplotlib.pyplot as plt
    from adjustText import adjust_text

    fig, ax = plt.subplots(figsize=figsize)
    line_x, line_y = [], []
    if line is not None:
        (x1, y1), (x2, y2) = line
        line_x, line_y = [x1, x2], [y1, y2]
        ax.plot(line_x, line_y, "k-", label="cross-section")
        ax.plot(x1, y1, "bs", label="start (river side)")
    ax.scatter(piezometers["x"], piezometers["y"], c="C1", zorder=5, label="piezometers")

    wells = piezometers.drop_duplicates(["x", "y"])
    texts = [
        ax.text(row["x"], row["y"], f"{row['name'].rsplit('_', 1)[0]}\nx = {row['x_crosssection']:.0f} m",
                fontsize=7, zorder=6, bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.75))
        for _, row in wells.iterrows()
    ]
    square_extent(ax, [*piezometers["x"], *line_x], [*piezometers["y"], *line_y])
    add_basemap(ax, crs=crs, source=source)
    ax.ticklabel_format(useOffset=False, style="plain")
    # Move overlapping labels apart (after the extent is set), with a line to the point
    adjust_text(texts, x=list(wells["x"]), y=list(wells["y"]), ax=ax, expand=(1.2, 1.4),
                arrowprops=dict(arrowstyle="-", color="0.3", lw=0.5))
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.legend(loc=(0, 1), frameon=False, ncol=2, fontsize="x-small")
    if title:
        ax.set_title(title, loc="right")
    return fig, ax
