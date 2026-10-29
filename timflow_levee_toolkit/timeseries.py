"""Observed time series: import from Excel into a pastastore, select, summarize and plot.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from ._units import _label


def plot_select(pstore, xlim=None, ylim=None, title=None, subset=None, figsize=(12, 10), units=None):
    """Plot all oseries and stresses in a pastastore in one figure.

    Parameters
    ----------
    pstore : pastastore.PastaStore
        The pastastore to plot.
    xlim : sequence of datetime, optional
        Time limits `[start, end]` of the x-axis. Default is the full period.
    ylim : sequence of float, optional
        Limits of the y-axis. Default is automatic.
    title : str, optional
        First part of the plot title (e.g. the transect name).
    subset : str, optional
        Second part of the plot title (e.g. "all series").
    figsize : tuple of float, optional
        Figure size `(width, height)` in inches. Default is `(12, 10)`.
    units : dict, optional
        Units for the axis labels, see `DEFAULT_UNITS` (key 'head').

    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes
    """
    fig, ax = plt.subplots(figsize=figsize)
    pstore.plots.oseries(ax=ax)
    try:
        pstore.plots.stresses(ax=ax)
    except Exception:
        print("No stresses available in the Pastastore file")

    ax.set_title(f"{title} - {subset} ", loc="right")
    ax.set_ylabel(_label("Heads", units, "head"))
    ax.set_xlabel("Date")
    ax.yaxis.grid(True, alpha=0.7)
    ax.legend(loc=(0, 1), frameon=False, ncol=3, fontsize="x-small")

    if xlim:
        ax.set_xlim(xlim)
    if ylim:
        ax.set_ylim(ylim)
    return fig, ax


def clip_data(pstore, series, xlim):
    """Clip an oseries from a pastastore to a time period.

    The datetime index is converted to decimal days since the start of the
    period, as used for the time axis of a timflow model.

    Parameters
    ----------
    pstore : pastastore.PastaStore
        The pastastore containing the oseries.
    series : str
        Name of the oseries.
    xlim : sequence of datetime
        Time period `[start, end]`, e.g. `[dt(2025, 2, 9), dt(2025, 2, 16)]`.

    Returns
    -------
    pandas.DataFrame
        The clipped series (without NaN values) with index 'Time [days]'.
    """
    oseries = pstore.get_oseries(series).loc[xlim[0] : xlim[1]].dropna()
    df = pd.DataFrame(oseries)

    # Recalculate index to decimal days since start of period
    df.index = (df.index - xlim[0]).total_seconds() / 3600 / 24
    df.index.name = "Time [days]"
    return df


def plot_daily_situation(
    df, title, ylabel=None, name="", xlim=None, savepath=None, figsize=(10, 4),
    units=None, relative=False,
):
    """Plot observed heads for the daily situation.

    The series are interpolated for plotting only, because they can have
    different time intervals. Gaps at the start and end are not filled.

    Parameters
    ----------
    df : pandas.DataFrame
        Heads with one column per location, e.g. `obs_ref` or `obs_dh`.
    title : str
        Plot title (shown on the right).
    ylabel : str, optional
        Label of the y-axis. Default is 'Hydraulic head [unit]' from `units`.
    name : str, optional
        Name (e.g. the transect) shown in the note below the plot.
    xlim : sequence of datetime, optional
        Period `[start, end]` the data was clipped to; shown in the note
        below the plot.
    savepath : str or pathlib.Path, optional
        If given, the figure is saved to this file (300 dpi).
    figsize : tuple of float, optional
        Figure size `(width, height)` in inches. Default is `(10, 4)`.
    units : dict, optional
        Units for the axis labels, see `DEFAULT_UNITS`.
    relative : bool, optional
        True if `df` holds heads relative to their average (e.g. `obs_dh`):
        the label then uses the unit of 'head_rel' instead of 'head'.
        Default is False.

    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes
    """
    if ylabel is None:
        ylabel = _label("Hydraulic head", units, "head_rel" if relative else "head")
    fig, ax = plt.subplots(figsize=figsize)
    df.interpolate(limit_area="inside").plot(grid=True, ax=ax)
    ax.legend(loc=(0, 1), frameon=False, ncol=5, fontsize=8)
    ax.set_ylabel(ylabel)
    ax.set_title(title, loc="right")

    note = name
    if xlim is not None:
        note = f"{note} ({xlim[0].date()} to {xlim[1].date()})".strip()
    if note:
        ax.text(1, -0.15, note, ha="right", va="bottom", transform=ax.transAxes, fontsize=8)

    if savepath is not None:
        fig.savefig(Path(savepath), dpi=300, bbox_inches="tight")
    return fig, ax


def summarize_observations(obs_ref, obslocs, loc_farfield, loc_river):
    """Summarize the average observed heads in the daily situation.

    Parameters
    ----------
    obs_ref : pandas.DataFrame
        Observed heads (e.g. m NAP) with one column per location, including the
        river and the far-field reference column.
    obslocs : pandas.DataFrame
        Observation locations; must have columns 'x_crosssection' and
        'modellayer'.
    loc_farfield : str
        Column in `obs_ref` used as the far-field reference (e.g. 'polder').
    loc_river : str
        Column in `obs_ref` with the river water level.

    Returns
    -------
    pandas.DataFrame
        One row per location (in `obs_ref` and/or `obslocs`), sorted by
        'x_crosssection' and 'modellayer', with columns:
          h_avg          : average head (datum of `obs_ref`, e.g. m NAP)
          h_avg_farfield : average head relative to the far-field reference [m]
          h_scaled       : h_avg_farfield divided by that of the river [-]
          x_crosssection, modellayer : from `obslocs` (NaN for e.g. the river)
    """
    h_avg = obs_ref.mean()
    h_avg_farfield = h_avg - h_avg[loc_farfield]

    summary = pd.DataFrame(
        {
            "h_avg": h_avg,
            "h_avg_farfield": h_avg_farfield,
            "h_scaled": h_avg_farfield / h_avg_farfield[loc_river],
        }
    )
    summary = pd.concat([summary, obslocs[["x_crosssection", "modellayer"]]], axis=1)
    return summary.sort_values(["x_crosssection", "modellayer"])


def calculate_max_response(h_river, h_piezo):
    """Calculate the response of a piezometer to the river from their maxima.

    Simple estimate based on the single highest value of each series: the
    response factor is the ratio of the maxima, the time lag is the time
    between them. For a series with several tides, see
    `calculate_rf_peaks`, which matches each peak.

    Parameters
    ----------
    h_river : pandas.Series
        River head relative to its average, with time [days] as index.
    h_piezo : pandas.Series
        Piezometer head relative to its average, with time [days] as index.

    Returns
    -------
    dict
        Keys 'response_factor' [-] and 'time_lag_hours' [hours].
    """
    t_river, t_piezo = h_river.idxmax(), h_piezo.idxmax()
    return {
        "response_factor": h_piezo[t_piezo] / h_river[t_river],
        "time_lag_hours": (t_piezo - t_river) * 24,
    }


def plot_hysteresis(h_river, h_piezo, ax=None, units=None):
    """Plot piezometer head against river head to show hysteresis.

    Each point is one time step; a loop instead of a straight line means
    the piezometer lags behind the river.

    Parameters
    ----------
    h_river : pandas.Series
        River head relative to its average, with time [days] as index.
    h_piezo : pandas.Series
        Piezometer head relative to its average, with time [days] as index.
    ax : matplotlib.axes.Axes, optional
        Axes to plot on. Default creates a new figure.
    units : dict, optional
        Units for the axis labels, see `DEFAULT_UNITS` (key 'head_rel').

    Returns
    -------
    matplotlib.axes.Axes
    """
    if ax is None:
        _, ax = plt.subplots()
    df = pd.concat({"river": h_river, "piezo": h_piezo}, axis=1).dropna()
    ax.plot(df["river"], df["piezo"], ".-", ms=3, lw=0.5)
    ax.set_xlabel(_label(h_river.name or "river", units, "head_rel"))
    ax.set_ylabel(_label(h_piezo.name or "piezometer", units, "head_rel"))
    ax.grid(True)
    return ax


def read_timeseries_excel(path, sheet_name="timeseries", info_sheet="series_info"):
    """Read observed time series from the Excel template.

    The sheet `sheet_name` has one column 'datetime' and one column per
    series (named after the piezometer filter or the river gauge), with the
    heads in m NAP (or the datum of the project). Times are without time
    zone, in Dutch winter time (UTC+1), the convention of BRO and
    Rijkswaterstaat data in hydropandas. Series may have different time
    steps; empty cells are ignored.

    The optional sheet `info_sheet` has one row per series that is not a
    piezometer (e.g. a river gauge), with columns 'name' and optionally 'x',
    'y' and 'kind'.

    Parameters
    ----------
    path : str or pathlib.Path
        Excel file (template `timeseries.xlsx`).
    sheet_name : str, optional
        Sheet with the time series. Default is 'timeseries'.
    info_sheet : str, optional
        Sheet with information on series that are not piezometers. Default
        is 'series_info'; skipped if the sheet does not exist.

    Returns
    -------
    timeseries : pandas.DataFrame
        Indexed by datetime, one column per series.
    info : pandas.DataFrame
        Indexed by series name (empty if there is no info sheet).
    """
    timeseries = pd.read_excel(path, sheet_name=sheet_name, index_col=0)
    timeseries.index = pd.to_datetime(timeseries.index)
    if timeseries.index.tz is not None:
        raise ValueError(f"Times in '{path}' must be without time zone (Dutch winter time, UTC+1)")
    if timeseries.index.has_duplicates:
        raise ValueError(f"Duplicate times in '{path}'")
    timeseries.index.name = "datetime"
    timeseries = timeseries.sort_index().apply(pd.to_numeric, errors="raise")

    sheets = pd.ExcelFile(path).sheet_names
    if info_sheet in sheets:
        info = pd.read_excel(path, sheet_name=info_sheet, dtype={"name": str}).set_index("name")
    else:
        info = pd.DataFrame(index=pd.Index([], name="name"))
    return timeseries, info


def import_timeseries(pstore, timeseries, metadata=None, overwrite=False):
    """Add time series to a pastastore as oseries.

    Parameters
    ----------
    pstore : pastastore.PastaStore
        Pastastore to add the series to.
    timeseries : pandas.DataFrame
        One column per series, indexed by datetime (e.g. a selection of
        `read_timeseries_excel`). Empty values are dropped.
    metadata : pandas.DataFrame, optional
        Metadata per series, indexed by series name (e.g. x, y, screen_top,
        screen_bottom). Stored with the series in the pastastore.
    overwrite : bool, optional
        Replace series that are already in the pastastore. Default is False:
        existing series are skipped.

    Returns
    -------
    list of str
        Names of the series that were added.
    """
    added = []
    for name, series in timeseries.items():
        series = series.dropna()
        if series.empty:
            print(f"Skipped '{name}': no values")
            continue
        if name in pstore.oseries_names and not overwrite:
            print(f"Skipped '{name}': already in the pastastore (use overwrite=True to replace)")
            continue
        meta = {}
        if metadata is not None and name in metadata.index:
            row = metadata.loc[name]
            meta = {k: (v.item() if hasattr(v, "item") else v) for k, v in row.items() if pd.notna(v)}
        pstore.conn.add_oseries(series.rename(name), name, metadata=meta, overwrite=overwrite)
        added.append(name)
    return added
