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
