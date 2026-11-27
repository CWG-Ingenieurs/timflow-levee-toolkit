"""Observed time series: import from Excel into a pastastore, select, summarize and plot.
"""

import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
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
    pstore.plots.oseries(ax=ax, progressbar=False)
    try:
        pstore.plots.stresses(ax=ax, progressbar=False)
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
    df.index = to_days(df.index, xlim[0])
    return df


def to_days(times, start):
    """Decimal days since `start`, as used for the time axis of a timflow model.

    The one conversion from date and time to model time, used by `clip_data` and
    `read_observations`, so both give exactly the same values.

    Parameters
    ----------
    times : sequence of datetime
    start : datetime
        Start of the model period.

    Returns
    -------
    pandas.Index
        Float index named 'Time [days]'.
    """
    days = (pd.DatetimeIndex(times) - pd.Timestamp(start)).total_seconds() / 3600 / 24
    return pd.Index(days, name="Time [days]")


def check_trend(obs, max_change=0.25, window=25 / 24):
    """Check the model period for a trend in the daily mean of the heads and the river level.

    The model period should have a fairly constant daily mean: with a trend, the tidal response
    is mixed with a slow change. The tidal peaks at the end of the period then lie around or below
    the mean of the period, and the tidal response factors of notebook 52 become meaningless. The
    tide is filtered out with a centred moving average over `window` (25 hours: about two tidal
    periods); the change is the range (max - min) of this daily mean, without the first and last
    half window, where the average is incomplete.

    Parameters
    ----------
    obs : pandas.DataFrame
        Observations of the model period with the time in days as index (e.g. `obs_ref` of
        notebook 51) and one column per series.
    max_change : float, optional
        Largest acceptable change of the daily mean in the model period, in the unit of the
        heads. Default is 0.25 (m). A warning is given for each series above it.
    window : float, optional
        Width of the moving average [days]. Default is 25/24 (25 hours).

    Returns
    -------
    pandas.DataFrame
        Per series: 'change' (range of the daily mean), 'start' and 'end' (daily mean at the
        start and end of the period) and 'trend' (True if 'change' exceeds `max_change`).
    """
    t = pd.to_timedelta(np.asarray(obs.index, dtype=float), unit="D")
    index_td = pd.TimedeltaIndex(t)
    half = pd.Timedelta(days=window / 2)
    rows = {}
    for name, series in obs.items():
        s = pd.Series(series.to_numpy(dtype=float), index=index_td).dropna().sort_index()
        if len(s) < 2 or s.index[-1] - s.index[0] <= 2 * half:
            rows[name] = {"change": np.nan, "start": np.nan, "end": np.nan}
            continue
        daily = s.rolling(pd.Timedelta(days=window), center=True).mean()
        daily = daily[(daily.index >= s.index[0] + half) & (daily.index <= s.index[-1] - half)]
        rows[name] = {"change": daily.max() - daily.min(), "start": daily.iloc[0], "end": daily.iloc[-1]}
    table = pd.DataFrame.from_dict(rows, orient="index")
    table.index.name = "series"
    table["trend"] = table["change"] > max_change
    if table["trend"].any():
        names = ", ".join(f"{n} ({c:.2f})" for n, c in table.loc[table["trend"], "change"].items())
        warnings.warn(
            f"Trend in the model period: the daily mean changes more than {max_change} for {names}. "
            "The tidal response factors may be unreliable; consider a calmer period.",
            stacklevel=2,
        )
    return table


MODEL_PERIOD_MODES = ("tide", "wave")


def candidate_model_periods(rivers, heads, length=7, mode="tide", min_completeness=0.95, max_river_high=0.5,
                            n_best=10, window=25):
    """Rank candidate model periods (e.g. weeks) by the data and the river level.

    A candidate starts at 00:00 of every day and lasts `length` days. The tide is
    filtered out with a centred moving average over `window` hours (25 hours:
    about two tidal periods). Per candidate:

    - `completeness`: the lowest fraction of hours with data over all series
      (`least_complete`: that series);
    - `river_change`: the largest range (max - min) of the filtered river level [m];
    - `head_change`: the largest range of the filtered heads [m];
    - `river_high`: the highest filtered river level above the median of that gauge
      over the whole series [m];
    - `tidal_range`: the largest range of the (unfiltered) river level [m].

    Two kinds of model period, `mode`:

    - 'tide' (a river with tide): the tidal response is calibrated, so the daily
      mean should be fairly constant (see `check_trend`) and the river not high.
      Candidates with complete data and `river_high` <= `max_river_high` are
      ranked by `river_change + head_change`, smallest first.
    - 'wave' (a river without tide, e.g. held by weirs): the response to a
      high-water wave is calibrated, so the river should change. Candidates with
      complete data are ranked by `river_change`, largest first.

    Parameters
    ----------
    rivers, heads : pandas.DataFrame
        Hourly river levels and heads on one time axis, e.g. from
        `Project.model_period_series`.
    length : float, optional
        Length of a candidate period [days]. Default is 7.
    mode : {'tide', 'wave'}, optional
        Default is 'tide'.
    min_completeness : float, optional
        Smallest fraction of hours with data, for every series. Default is 0.95.
    max_river_high : float, optional
        Mode 'tide': highest filtered river level above its median [m]. Default is 0.5.
    n_best : int, optional
        Number of best candidates that are ranked (they don't overlap). Default is 10.
    window : int, optional
        Width of the moving average [hours]. Default is 25.

    Returns
    -------
    pandas.DataFrame
        One row per candidate (index: start), with the columns above, 'end',
        'score', 'candidate' (complete, and in mode 'tide' no high water) and
        'rank' (1 = best; NaN if not among the `n_best`).
    """
    if mode not in MODEL_PERIOD_MODES:
        raise ValueError(f"mode must be one of {MODEL_PERIOD_MODES}, not {mode!r}")
    duration = pd.Timedelta(days=length)
    min_periods = int(round(0.8 * window))
    river_f = rivers.rolling(window, center=True, min_periods=min_periods).mean()
    head_f = heads.rolling(window, center=True, min_periods=min_periods).mean()
    river_median = rivers.median()
    index = rivers.index.union(heads.index)

    rows = []
    for start in pd.date_range(index[0].ceil("D"), index[-1] - duration, freq="D"):
        sl = slice(start, start + duration - pd.Timedelta(hours=1))
        completeness = pd.concat([rivers.loc[sl], heads.loc[sl]], axis=1).notna().mean()
        rf, hf = river_f.loc[sl], head_f.loc[sl]
        rows.append({
            "start": start,
            "end": start + duration,
            "completeness": completeness.min(),
            "least_complete": completeness.idxmin() if len(completeness) else None,
            "river_change": (rf.max() - rf.min()).max(),
            "head_change": (hf.max() - hf.min()).max() if heads.shape[1] else 0.0,
            "river_high": (rf.max() - river_median).max(),
            "tidal_range": (rivers.loc[sl].max() - rivers.loc[sl].min()).max(),
        })
    periods = pd.DataFrame(rows).set_index("start")
    if periods.empty:
        raise ValueError(f"The series are shorter than one period of {length} days")
    complete = periods["completeness"] >= min_completeness
    if mode == "tide":
        periods["score"] = periods["river_change"] + periods["head_change"]
        periods["candidate"] = complete & (periods["river_high"] <= max_river_high)
        order = periods[periods["candidate"]].sort_values("score")
    else:
        periods["score"] = periods["river_change"]
        periods["candidate"] = complete
        order = periods[periods["candidate"]].sort_values("score", ascending=False)
    best = []
    for start in order.index:
        if all(abs(start - b) >= duration for b in best):
            best.append(start)
        if len(best) == n_best:
            break
    periods["rank"] = pd.Series(range(1, len(best) + 1), index=best, dtype=float)
    return periods


def plot_candidate_model_periods(rivers, heads, periods, current=None, min_completeness=0.95, units=None):
    """Figure of the candidate model periods of `candidate_model_periods`.

    Four panels: the river levels (and their filtered daily mean), the filtered
    heads relative to their median, the completeness and the score. The ranked
    candidates are shaded green with their rank; the `current` model period red.

    Parameters
    ----------
    rivers, heads : pandas.DataFrame
        Hourly river levels and heads, as passed to `candidate_model_periods`.
    periods : pandas.DataFrame
        Result of `candidate_model_periods`.
    current : tuple of datetime, optional
        (start, end) of the current model period.
    min_completeness : float, optional
        Shown as a line in the completeness panel. Default is 0.95.
    units : dict, optional
        Units for the axis labels (`project.units`).

    Returns
    -------
    matplotlib.figure.Figure
    """
    import matplotlib.dates as mdates

    head_unit = (units or {}).get("head", "m NAP")
    rel_unit = (units or {}).get("head_rel", "m")
    river_f = rivers.rolling(25, center=True, min_periods=20).mean()
    head_f = heads.rolling(25, center=True, min_periods=20).mean()
    best = periods["rank"].dropna().sort_values()
    duration = (periods["end"] - periods.index).iloc[0]
    fig, axes = plt.subplots(4, 1, figsize=(14, 11), sharex=True, layout="constrained",
                             gridspec_kw={"height_ratios": [3, 3, 1, 2]})
    for name in rivers.columns:
        axes[0].plot(rivers.index, rivers[name], lw=0.2, alpha=0.4)
        axes[0].plot(river_f.index, river_f[name], lw=1.2, label=f"{name} (25 h mean)")
    axes[0].set_ylabel(f"river level [{head_unit}]")
    axes[0].legend(loc="upper left", fontsize="small", ncol=3)
    for name in heads.columns:
        axes[1].plot(head_f.index, head_f[name] - heads[name].median(), lw=0.7)
    axes[1].set_ylabel(f"head - median\n(25 h mean) [{rel_unit}]")
    axes[2].plot(periods.index, periods["completeness"], color="k", lw=0.8)
    axes[2].axhline(min_completeness, color="tab:red", ls="--", lw=0.8)
    axes[2].set_ylabel("completeness\n(period from date)")
    axes[2].set_ylim(0, 1.05)
    ok = periods["candidate"]
    axes[3].plot(periods.index, periods["score"].where(ok), color="k", lw=0.8, label="score (candidates)")
    axes[3].plot(periods.index, periods["score"].where(~ok), color="0.7", lw=0.8, label="score (other periods)")
    axes[3].set_ylabel(f"score [{rel_unit}]\n(period from date)")
    axes[3].legend(loc="upper left", fontsize="small")
    for ax in axes:
        for start, rank in best.items():
            ax.axvspan(start, start + duration, color="tab:green", alpha=0.25, lw=0)
            if ax is axes[0]:
                ax.text(start + duration / 2, 1.0, str(int(rank)), transform=ax.get_xaxis_transform(),
                        ha="center", va="bottom", fontsize="small", color="tab:green")
        if current is not None:
            ax.axvspan(pd.Timestamp(current[0]), pd.Timestamp(current[1]), color="tab:red", alpha=0.25, lw=0)
        ax.grid(alpha=0.3)
    axes[0].set_title("Candidate model periods (green, ranked)"
                      + (" and the current model period (red)" if current is not None else ""), loc="left")
    locator = mdates.AutoDateLocator(minticks=3, maxticks=12)
    axes[-1].xaxis.set_major_locator(locator)
    axes[-1].xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    return fig


OBSERVATIONS_EXPLANATION = [
    ("observations", "time", "Date and time of the measurement, without time zone (Dutch winter time, UTC+1)"),
    ("observations", "days since start", "Model time: days since the start of the model period (sheet 'info'); "
                                         "used as time axis by notebook 52"),
    ("observations", "<name>", "Observed head or river level [m NAP], one column per series; the far-field "
                               "reference is a constant column"),
    ("info", "start, end", "Model period chosen in notebook 51"),
]


def write_observations(obs, path, start, end):
    """Write the observations of the model period to Excel (notebook 51), for notebook 52.

    Each row has the date and time of the measurement and the model time in days since
    `start`; notebook 52 uses the latter as time axis (`read_observations`). Excel stores
    numbers with 16 significant digits, so the days can differ from those in notebook 51
    in the last digit (less than a nanosecond).

    Parameters
    ----------
    obs : pandas.DataFrame
        Observations with the time in days since `start` as index (from `clip_data`) and
        one column per series.
    path : str or pathlib.Path
        Excel file to write, e.g. 'observations_model_period.xlsx'.
    start, end : datetime
        The model period.
    """
    if len(obs) > 1_048_575:
        raise ValueError(f"{len(obs)} rows do not fit in an Excel sheet: choose a shorter model period")
    table = obs.copy()
    table.insert(0, "days since start", obs.index.to_numpy())
    # Date and time of the measurement (whole seconds)
    table.index = (pd.Timestamp(start) + pd.to_timedelta(obs.index.to_numpy(), unit="D")).round("s")
    table.index.name = "time"
    info = pd.DataFrame({"value": [pd.Timestamp(start), pd.Timestamp(end)]}, index=pd.Index(["start", "end"], name="item"))
    explanation = pd.DataFrame(OBSERVATIONS_EXPLANATION, columns=["sheet", "column", "explanation"])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl", datetime_format="yyyy-mm-dd hh:mm:ss") as writer:
        table.to_excel(writer, sheet_name="observations")
        info.to_excel(writer, sheet_name="info")
        explanation.to_excel(writer, sheet_name="explanation", index=False)
        for ws in writer.sheets.values():
            for column in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in column[:200])
                ws.column_dimensions[column[0].column_letter].width = min(max(width, 10), 60) + 2


def read_observations(path):
    """Read the observations of the model period written by `write_observations` (notebook 52).

    Returns
    -------
    pandas.DataFrame
        Observations with the column 'days since start' as index ('Time [days]') and one
        column per series. The model period is in `attrs["start"]` and `attrs["end"]`.
    """
    info = pd.read_excel(path, sheet_name="info", index_col=0)["value"]
    obs = pd.read_excel(path, sheet_name="observations", index_col=0)
    obs.index = pd.Index(obs.pop("days since start").to_numpy(dtype=float), name="Time [days]")
    obs.attrs.update(start=pd.Timestamp(info["start"]), end=pd.Timestamp(info["end"]))
    return obs


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


def plot_hysteresis(h_river, h_piezo, ax=None, units=None, label=None):
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
    label : str, optional
        Label for the legend. Default is the name of `h_piezo`.

    Returns
    -------
    matplotlib.axes.Axes
    """
    if ax is None:
        _, ax = plt.subplots()
    df = pd.concat({"river": h_river, "piezo": h_piezo}, axis=1).dropna()
    ax.plot(df["river"], df["piezo"], ".-", ms=3, lw=0.5, label=label or h_piezo.name)
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

    Wraps `pstore.conn.add_oseries(series, name, metadata=..., overwrite=...)`
    for each column, with the metadata of that series.

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
