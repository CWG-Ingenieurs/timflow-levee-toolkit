"""Response factors, flow resistance and leakage lengths.

The `calculate_rf_*` functions work on (time series of) heads, so the same
function is used for modeled and observed heads.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from scipy.signal import find_peaks

from ._units import _label
from .model import calculate_head_t


def calculate_flow_resistance(model_steady, inhom_name: str, layer: int = -1) -> float:
    """Calculate the flow resistance (W) for an inhomogeneity, see Technisch Rapport Waterspanningen bij Dijken (TRWD) page b4-5.

    Parameters
    ----------
    model_steady : timflow.steady Model
        The solved steady timflow model. Must be the steady model: the
        leakage factor (`aq.lab[0]`) is only a meaningful scalar per
        layer/eigenmode there, not on a transient model - see
        https://github.com/timflow-org/timflow/issues/187.
    inhom_name : str
        Name of the inhomogeneity (key in model_steady.aq.inhomdict).
    layer : int, optional
        Layer index for the transmissivity `kD`. Default is `-1` (deepest
        layer).

    Returns
    -------
    float
        The flow resistance (dutch: stromingsweerstand) W [T/L].
    """
    inhom = model_steady.aq.inhomdict[inhom_name]
    kD = inhom.T[layer]

    # This length may not be finite, but that is no problem for the tanh
    L = inhom.x2 - inhom.x1

    leakagefactor = inhom.lab[0]
    return (leakagefactor / kD) * np.tanh(L / leakagefactor)


def calculate_response_profile(x, leakage_length_foreland, leakage_length_hinterland):
    """Response factor along x, based on the dutch publication Technisch Rapport Waterspanningen bij Dijken (TRWD).

        The first formula is an alternative derivation of the ratio W1/W3, based on
        TRWD p. b4-6: W = leakage length / kD for long foreland and hinterland with
        equal transmissivity (kD) in both.

        The second formula (response factor at the hinge point, 'kantelpunt') is from
        TRWD p. b4-5: a rewritten form of the formula for phi_2 for L_2 = 0 (so W_2 = 0).

        The third formula (response over distance) is from TRWD p. b4-6: the formula
        for phi(x) in the hinterland for L_2 = 0 (so a = 0).

        Parameters
        ----------
        x : np.array
            x-locations [m]
        leakage_length_foreland : float
            Leakage length of the foreland [m]
        leakage_length_hinterland : float
            Leakage length of the hinterland [m]

        Returns
        -------
        np.array
            Response factor per location

        
    """
    ratio_W1_W3 = leakage_length_foreland / leakage_length_hinterland

    # Response at the hinge point ('kantelpunt')
    rk = 1 / (1 + (ratio_W1_W3))

    # Decay of the response with the distance x in the hinterland
    r_x = np.exp(-1 * (x / leakage_length_hinterland))

    return rk * r_x


# -----------------------------------------------------------------------------
# Response factors
# -----------------------------------------------------------------------------
# The calculation of response factors is split from the model: the
# `calculate_rf_*` functions work on (time series of) heads, so the same
# function is used for modeled and observed heads. They all return a
# DataFrame indexed by observation location with columns 'x_crosssection'
# and 'modellayer' plus response factor columns named
# `rf_<method>_<mod|obs>` (e.g. 'rf_steady_mod', 'rf_tidal_obs'). Tables of
# different methods can be combined with `combine_rf`, fitted with
# `fit_response_profile` and plotted with `plot_rf_x`.


def calculate_rf_steady(model_steady, obslocs, h_river, h_obs=None):
    """Calculate steady-state response factors for all observation locations.

    The response factor is the modeled head relative to the far field
    (the head at x=1e6), divided by the average river head relative to the
    far field reference.

    Parameters
    ----------
    model_steady : timflow.steady.ModelXsection
        The solved steady timflow model.
    obslocs : pandas.DataFrame
        Observation locations; must have columns 'x_crosssection' and
        'modellayer'.
    h_river : float
        Average observed river head relative to the far field reference.
    h_obs : pandas.Series, optional
        Average observed heads relative to the far field reference, indexed
        by observation location (e.g. `obs_avg_farfieldref`). If given, an
        observed response factor `h_obs / h_river` is added as column
        'rf_steady_obs' (NaN for locations missing in `h_obs`).

    Returns
    -------
    pandas.DataFrame
        Indexed by observation location with columns 'x_crosssection',
        'modellayer', 'rf_steady_mod' and, if `h_obs` is given,
        'rf_steady_obs'.
    """
    records = []
    for obsloc, row in obslocs.iterrows():
        x = row["x_crosssection"]
        layer = int(row["modellayer"])
        h = model_steady.head(x, 0, layers=layer) - model_steady.head(1e6, 0, layers=layer)
        record = {
            "obsloc": obsloc,
            "x_crosssection": x,
            "modellayer": layer,
            "rf_steady_mod": float(np.squeeze(h)) / h_river,
        }
        if h_obs is not None:
            record["rf_steady_obs"] = h_obs.get(obsloc, np.nan) / h_river
        records.append(record)
    return pd.DataFrame(records).set_index("obsloc")


def _find_peaks_in_series(series, min_peak_period):
    """Return times and values of the peaks in a series (NaN values dropped)."""
    s = series.dropna()
    if len(s) < 2:
        return np.array([]), np.array([])
    t = s.index.to_numpy()
    h = s.to_numpy()
    dt = np.median(np.diff(t))
    peaks, _ = find_peaks(h, distance=max(1, int(min_peak_period / dt)))
    return t[peaks], h[peaks]


def calculate_rf_peaks(h_t, h_river, min_peak_period=11 / 24):
    """Calculate a response factor and time lag for every tidal peak.

    Peaks are detected with `scipy.signal.find_peaks`, with a minimum time
    between two peaks of `min_peak_period`. Each river peak is matched to
    the nearest (in time) peak of the piezometer, which gives per peak:

    - response factor: h_peak_piezo / h_peak_river
    - time lag: t_peak_piezo - t_peak_river

    Works the same for modeled and observed heads; use `summarize_rf_tidal`
    to get one value per location.

    Parameters
    ----------
    h_t : pandas.DataFrame
        Heads relative to their own average, with time [days] as index and
        one column per observation location (e.g. `obs_dh[...]`). For
        MultiIndex columns (e.g. `(layer, obsloc)` from `select_obslocs`)
        the last level is used as location name.
    h_river : pandas.Series
        River head relative to its average, with time [days] as index.
    min_peak_period : float, optional
        Minimum time between two peaks [days]. Default is 11/24 (11 hours).

    Returns
    -------
    pandas.DataFrame
        One row per location and river peak, with columns 'obsloc',
        't_peak_river', 't_peak_piezo', 'h_peak_river', 'h_peak_piezo',
        't_offset' [days] and 'response_factor' [-].
    """
    columns = ["obsloc", "t_peak_river", "t_peak_piezo", "h_peak_river",
               "h_peak_piezo", "t_offset", "response_factor"]
    t_river, h_peak_river = _find_peaks_in_series(h_river, min_peak_period)

    records = []
    for col, series in h_t.items():
        obsloc = col[-1] if isinstance(col, tuple) else col
        t_piezo, h_peak_piezo = _find_peaks_in_series(series, min_peak_period)
        if len(t_piezo) == 0:
            continue
        for t_riv, h_riv in zip(t_river, h_peak_river):
            i = np.argmin(np.abs(t_piezo - t_riv))
            records.append({
                "obsloc": obsloc,
                "t_peak_river": t_riv,
                "t_peak_piezo": t_piezo[i],
                "h_peak_river": h_riv,
                "h_peak_piezo": h_peak_piezo[i],
                "t_offset": t_piezo[i] - t_riv,
                "response_factor": h_peak_piezo[i] / h_riv if h_riv != 0 else np.nan,
            })
    return pd.DataFrame(records, columns=columns)


def summarize_rf_tidal(peaks, obslocs):
    """Summarize the tidal response per location as the median over all peaks.

    Parameters
    ----------
    peaks : dict
        Per kind (e.g. "mod", "obs") a table from `calculate_rf_peaks`.
    obslocs : pandas.DataFrame
        Observation locations; must have columns 'x_crosssection' and
        'modellayer'.

    Returns
    -------
    pandas.DataFrame
        Indexed by observation location with columns 'x_crosssection',
        'modellayer' and per kind `<kind>`: 'rf_tidal_<kind>' (median
        response factor [-]), 'lag_tidal_<kind>_hours' (median time lag
        [hours]) and 'n_peaks_<kind>' (number of river peaks). Locations
        without peaks get NaN.
    """
    df = obslocs[["x_crosssection", "modellayer"]].copy()
    df["modellayer"] = df["modellayer"].astype(int)
    for kind, table in peaks.items():
        grouped = table.groupby("obsloc")
        df[f"rf_tidal_{kind}"] = grouped["response_factor"].median()
        df[f"lag_tidal_{kind}_hours"] = grouped["t_offset"].median() * 24
        df[f"n_peaks_{kind}"] = grouped.size()
    df.index.name = "obsloc"
    return df


def calculate_rf_mhw(h_t, h_river, obslocs, kind="mod"):
    """Calculate response factors for the design hydrograph (MHW) of a storm event.

    MHW stands for the design situation: the design hydrograph (*waterstandsverloop*)
    with the design high water level (*maatgevende hoogwaterstand*) as its peak.
    Per location, the response factor is the peak of the head divided by the
    peak of the river level, both relative to the average river level:
    `max(h(t)) / max(h_river(t))`. The peak of the head comes later than the
    peak of the river level; the time of the peak of the head is returned too.

    Parameters
    ----------
    h_t : pandas.DataFrame
        Heads relative to the average river level (the transient part of the
        model), with time [days] as index and MultiIndex columns
        `(layer, obsloc)`, e.g. from `select_obslocs`.
    h_river : pandas.Series
        River head relative to the average river level, with time [days] as
        index.
    obslocs : pandas.DataFrame
        Observation locations; must have columns 'x_crosssection' and
        'modellayer'.
    kind : str, optional
        Suffix of the result columns: "mod" (default) for modeled or "obs"
        for observed response factors.

    Returns
    -------
    pandas.DataFrame
        Indexed by observation location with columns 'x_crosssection',
        'modellayer', 'rf_mhw_<kind>' and 't_mhw_<kind>' (time of the peak of
        the head [days]).
    """
    h_river_max = h_river.max()

    records = []
    for (layer, obsloc), h in h_t.items():
        t_max = h.idxmax()
        records.append({
            "obsloc": obsloc,
            "x_crosssection": obslocs.loc[obsloc, "x_crosssection"],
            "modellayer": layer,
            f"rf_mhw_{kind}": h[t_max] / h_river_max,
            f"t_mhw_{kind}": t_max,
        })
    return pd.DataFrame(records).set_index("obsloc")


def fit_response_profile(df, colname, layer=None, p0=(300.0, 1000.0), ax=None, units=None):
    """Fit `calculate_response_profile` to response factors over the cross-section.

    Fits the leakage lengths of the foreland and hinterland to the response
    factors of a single model layer.

    Parameters
    ----------
    df : pandas.DataFrame
        Response factors with columns 'x_crosssection', 'modellayer' and
        `colname`, e.g. the output of `calculate_rf_steady` or
        `calculate_rf_mhw`.
    colname : str
        Column with the response factors to fit (e.g. 'rf_steady_mod').
    layer : int, optional
        Model layer to fit. Default is the deepest layer in `df`.
    p0 : tuple of float, optional
        Initial guess for (leakage_length_foreland, leakage_length_hinterland) [m].
        Default is (300.0, 1000.0). Both are bounded to positive values.
    ax : matplotlib.axes.Axes, optional
        If given, the data and fitted curve are plotted on this axes.
    units : dict, optional
        Units for the axis labels, see `DEFAULT_UNITS` (key 'x').

    Returns
    -------
    dict
        Keys 'leakage_length_foreland', 'leakage_length_hinterland' [m], 'r_squared'
        [-], 'layer' and 'colname'.
    """
    if layer is None:
        layer = df["modellayer"].max()
    selected = df[df["modellayer"] == layer].dropna(subset=[colname]).sort_values("x_crosssection")
    xs = selected["x_crosssection"].to_numpy(dtype=float)
    rf = selected[colname].to_numpy(dtype=float)

    # Leakage lengths are positive: bound the fit (avoids meaningless negative values)
    (leakage_length_foreland, leakage_length_hinterland), _ = curve_fit(
        calculate_response_profile, xs, rf, p0, bounds=(0, np.inf)
    )

    rf_fit = calculate_response_profile(xs, leakage_length_foreland, leakage_length_hinterland)
    r_squared = 1 - np.sum((rf - rf_fit) ** 2) / np.sum((rf - rf.mean()) ** 2)

    if ax is not None:
        ax.plot(xs, rf, ".", label="data")
        ax.plot(xs, rf_fit, "--", label="fitted")
        ax.set_xlabel(_label("x", units, "x"))
        ax.set_ylabel(f"{colname} [-]")
        ax.set_title(f"layer {layer}", loc="right")
        ax.legend(frameon=False)
        ax.grid(True)

    return {
        "leakage_length_foreland": leakage_length_foreland,
        "leakage_length_hinterland": leakage_length_hinterland,
        "r_squared": r_squared,
        "layer": int(layer),
        "colname": colname,
    }


def _rf_profile(values, x):
    """Response factor profile as DataFrame: index x, one column per layer."""
    df = pd.DataFrame(np.asarray(values).T, index=pd.Index(x, name="x [m]"))
    df.columns.name = "layer"
    return df


def calculate_rf_steady_x(model_steady, x, h_river):
    """Calculate the modeled steady-state response factor along x, for all layers.

    Same definition as `calculate_rf_steady`, but continuous along x.

    Parameters
    ----------
    model_steady : timflow.steady.ModelXsection
        The solved steady timflow model.
    x : array_like
        x-coordinates [m].
    h_river : float
        Average observed river head relative to the far field reference.

    Returns
    -------
    pandas.DataFrame
        Index x [m], one column per layer.
    """
    x = np.asarray(x, dtype=float)
    h = model_steady.headalongline(x, np.zeros_like(x)) - model_steady.head(1e6, 0)[:, np.newaxis]
    return _rf_profile(h / h_river, x)


def calculate_rf_tidal_x(model_transient, x, t, h_river, min_peak_period=11 / 24):
    """Calculate the modeled tidal response factor along x, for all layers.

    Same definition as `calculate_rf_peaks` + `summarize_rf_tidal` (median
    over all tidal peaks), but continuous along x. The transient model must
    be forced with the tidal boundary condition.

    Parameters
    ----------
    model_transient : timflow.transient.ModelXsection
        Solved transient model (transient part only).
    x : array_like
        x-coordinates [m].
    t : array_like
        Times [days], the same as the index of `h_river`.
    h_river : pandas.Series
        River head relative to its average, with time [days] as index.
    min_peak_period : float, optional
        Minimum time between two peaks [days]. Default is 11/24 (11 hours).

    Returns
    -------
    pandas.DataFrame
        Index x [m], one column per layer.
    """
    x = np.asarray(x, dtype=float)
    h_t = calculate_head_t(model_transient, x, t)
    columns = {}
    for layer in sorted(h_t.columns.get_level_values("layer").unique()):
        peaks = calculate_rf_peaks(h_t[layer], h_river, min_peak_period)
        columns[layer] = peaks.groupby("obsloc")["response_factor"].median()
    df = pd.DataFrame(columns).reindex(x)
    df.index.name = "x [m]"
    df.columns.name = "layer"
    return df


def calculate_rf_mhw_x(model_transient, x, h_river):
    """Calculate the modeled response factor for the design hydrograph (MHW) along x, for all layers.

    Same definition as `calculate_rf_mhw` (peak of the head divided by the
    peak of the river level), but continuous along x. The transient model must
    be forced with the storm boundary condition.

    Parameters
    ----------
    model_transient : timflow.transient.ModelXsection
        Solved transient model (transient part only).
    x : array_like
        x-coordinates [m].
    h_river : pandas.Series
        River head relative to the average river level, with time [days] as
        index.

    Returns
    -------
    pandas.DataFrame
        Index x [m], one column per layer.
    """
    x = np.asarray(x, dtype=float)
    h_t = calculate_head_t(model_transient, x, h_river.index.to_numpy())
    df = (h_t.max() / h_river.max()).unstack("layer").reindex(x)
    df.index.name = "x [m]"
    return df


def combine_rf(obslocs, *tables):
    """Combine response factor tables of several methods into one table.

    Parameters
    ----------
    obslocs : pandas.DataFrame
        Observation locations; must have columns 'x_crosssection' and
        'modellayer'. Defines the rows of the result.
    *tables : pandas.DataFrame
        Tables from the `calculate_rf_*` / `summarize_rf_tidal` functions.

    Returns
    -------
    pandas.DataFrame
        Indexed by observation location, sorted by 'x_crosssection' and
        'modellayer', with all columns of `tables` except the repeated
        location columns.
    """
    base = obslocs[["x_crosssection", "modellayer"]].copy()
    base["modellayer"] = base["modellayer"].astype(int)
    rest = [t.drop(columns=["x_crosssection", "modellayer"], errors="ignore") for t in tables]
    df = pd.concat([base, *rest], axis=1)
    df.index.name = "obsloc"
    return df.sort_values(["x_crosssection", "modellayer"])


def _split_rf_column(colname):
    """Split 'rf_<method>_<kind>' into (method, kind); kind defaults to 'mod'."""
    name = colname.removeprefix("rf_")
    method, _, kind = name.rpartition("_")
    if kind not in ("mod", "obs"):
        return name, "mod"
    return method, kind


def plot_rf_x(df_rf, columns=None, profiles=None, figsize=None, units=None):
    """Plot response factors against x, with one subplot per model layer.

    Each method gets its own color. Modeled values are drawn as a
    continuous line if a profile is given (with markers at the observation
    locations), otherwise as filled markers connected by a line. Observed
    values are drawn as open markers.

    Parameters
    ----------
    df_rf : pandas.DataFrame
        Response factors with columns 'x_crosssection', 'modellayer' and
        `rf_<method>_<mod|obs>` columns, e.g. from `combine_rf`.
    columns : list of str, optional
        Response factor columns to plot. Default: all columns starting
        with 'rf_'.
    profiles : dict, optional
        Per response factor column a profile along x from the
        `calculate_rf_*_x` functions (index x, one column per layer), e.g.
        `{"rf_steady_mod": calculate_rf_steady_x(...)}`.
    figsize : tuple of float, optional
        Figure size. Default is `(10, 3 * nlayers)`.
    units : dict, optional
        Units for the axis labels, see `DEFAULT_UNITS` (key 'x').

    Returns
    -------
    fig : matplotlib.figure.Figure
    axes : numpy.ndarray of matplotlib.axes.Axes
        One axes per layer.
    """
    columns = columns or [c for c in df_rf.columns if c.startswith("rf_")]
    layers = sorted(df_rf["modellayer"].dropna().astype(int).unique())
    methods = list(dict.fromkeys(_split_rf_column(c)[0] for c in columns))
    colors = {method: f"C{i}" for i, method in enumerate(methods)}

    figsize = figsize or (10, 3 * len(layers))
    fig, axes = plt.subplots(
        len(layers), 1, figsize=figsize, sharex=True, sharey=True, layout="constrained"
    )
    axes = np.atleast_1d(axes)

    for ax, layer in zip(axes, layers):
        selected = df_rf[df_rf["modellayer"] == layer].sort_values("x_crosssection")
        for col in columns:
            data = selected[["x_crosssection", col]].dropna()
            method, kind = _split_rf_column(col)
            profile = (profiles or {}).get(col)
            if profile is not None and layer in profile.columns:
                ax.plot(profile.index, profile[layer], color=colors[method], label=col)
                ax.plot(data["x_crosssection"], data[col], "o", color=colors[method])
                continue
            if data.empty:
                continue
            if kind == "obs":
                style = {"marker": "s", "linestyle": "none", "markerfacecolor": "none"}
            else:
                style = {"marker": "o", "linestyle": "-"}
            ax.plot(data["x_crosssection"], data[col], color=colors[method], label=col, **style)

        ax.legend(loc=(0, 1), frameon=False, ncol=3, fontsize="x-small")
        ax.set_ylabel("response factor [-]")
        ax.set_title(f"layer {layer}", loc="right")
        ax.grid(True)
    axes[-1].set_xlabel(_label("x", units, "x"))
    return fig, axes


def plot_rf_peaks(obsloc, h_river, series, peaks, title=None, figsize=(10, 8), units=None):
    """Plot the tidal response per peak for one observation location.

    Upper graph: river and piezometer heads with the matched peaks.
    Lower graph: response factor (left axis) and time lag in hours (right
    axis) per river peak, with the median response factor as dotted line.

    Parameters
    ----------
    obsloc : str
        Name of the observation location.
    h_river : pandas.Series
        River head relative to its average, with time [days] as index.
    series : dict
        Per kind (e.g. "mod", "obs") the head series of this location, with
        time [days] as index. A value of None is skipped.
    peaks : dict
        Per kind a table from `calculate_rf_peaks` (all locations).
    title : str, optional
        Title of the upper graph. Default is `obsloc`.
    figsize : tuple of float, optional
        Figure size. Default is `(10, 8)`.
    units : dict, optional
        Units for the axis labels, see `DEFAULT_UNITS` (keys 'head_rel' and
        'time').

    Returns
    -------
    fig : matplotlib.figure.Figure
    axes : numpy.ndarray of matplotlib.axes.Axes
        `[upper, lower]`; the lower axes has a twin axes for the time lag.
    """
    fig, axes = plt.subplots(2, 1, figsize=figsize, sharex=True, layout="constrained")
    ax_h, ax_rf = axes
    ax_lag = ax_rf.twinx()

    # Drop NaN values (series with different time steps), otherwise no line is drawn
    h_river = h_river.dropna()
    ax_h.plot(h_river.index, h_river.values, label="river", color="C0")
    river_marked = False
    for i, (kind, s) in enumerate(series.items()):
        color = f"C{i + 1}"
        table = peaks.get(kind)
        loc_peaks = table[table["obsloc"] == obsloc] if table is not None else pd.DataFrame()
        if s is None:
            continue
        s = s.dropna()
        ax_h.plot(s.index, s.values, label=kind, color=color)
        if loc_peaks.empty:
            continue
        if not river_marked:
            ax_h.plot(loc_peaks["t_peak_river"], loc_peaks["h_peak_river"], "x", ms=5, color="C0")
            river_marked = True
        ax_h.plot(loc_peaks["t_peak_piezo"], loc_peaks["h_peak_piezo"], "x", ms=5, color=color)

        rf_median = loc_peaks["response_factor"].median()
        ax_rf.plot(loc_peaks["t_peak_river"], loc_peaks["response_factor"], ".-", color=color,
                   label=f"RF {kind}")
        ax_rf.axhline(rf_median, linestyle=":", color=color, label=f"median {kind} ({rf_median:.3f})")
        ax_lag.plot(loc_peaks["t_peak_river"], loc_peaks["t_offset"] * 24, "x--", color=color,
                    alpha=0.5, label=f"lag {kind}")

    ax_h.legend(loc=(0, 1), frameon=False, ncol=3, fontsize="x-small")
    ax_h.set_ylabel(_label("head", units, "head_rel"))
    ax_h.set_title(title or obsloc, loc="right")
    ax_h.grid(True)

    lines1, labels1 = ax_rf.get_legend_handles_labels()
    lines2, labels2 = ax_lag.get_legend_handles_labels()
    ax_rf.legend(lines1 + lines2, labels1 + labels2, loc=(0, 1), frameon=False, ncol=3,
                 fontsize="x-small")
    ax_rf.set_ylabel("response factor [-]")
    ax_lag.set_ylabel("time lag [hours]")
    ax_rf.set_xlabel(_label("time of river peak", units, "time"))
    ax_rf.grid(True)
    return fig, axes
