"""From parsed plates and per-well fits to the tables every view is drawn from."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import kruskal, mannwhitneyu

from .fitting import FitSettings, describe_indices, fit_initial_rate, fit_points, no_fit
from .reader import COLS, ROWS, WELLS, Plate

#: Fit statuses whose rate is a validated linear-phase estimate.
ACCEPTED = ("ok", "manual")

#: Fit statuses set by hand rather than by the automatic fit.
BY_HAND = ("manual", "excluded")

#: The override that marks a well "no fit": its rate is NaN.
NO_FIT: tuple[int, ...] = ()

#: Per-well export columns, in order; the rest of the per-well table stays internal.
COLUMNS = ["label", "plate", "well", "row", "col", "role",
           "vmax", "se", "intercept", "vmax_norm", "vmax_norm_se", "pos_mean_plate",
           "r2", "n_points", "t_end_s", "fit_source", "fit_points", "vmax_auto",
           "vmax_initial", "stopped_by", "status", "n_available", "n_timepoints",
           "a_start", "a_max", "T_window"]


def auto_fits(plate: Plate, settings: FitSettings) -> list[dict]:
    """The automatic fit of every well on a plate, in WELLS order."""
    return [fit_initial_rate(plate.t, plate.a[:, j], settings) for j in range(96)]


def _row(name: str, plate: Plate, j: int, fit: dict, auto: dict, role: str) -> dict:
    well, idx = WELLS[j], fit["idx"]
    a = plate.a[:, j]
    # Only a fit that passed its checks has a rate; a failed one keeps its line's slope
    # (for drawing, and for the control statistics) but reports NaN.
    rate = fit["status"] in ACCEPTED
    return dict(
        label=f"{name}-{well}", plate=name, well=well, row=well[0], col=int(well[1:]),
        role=role, clock=plate.clock,
        vmax=fit["slope"] * 60 if rate else np.nan, se=fit["se"] * 60 if rate else np.nan,
        line_rate=fit["slope"] * 60, intercept=fit["intercept"],
        r2=fit["r2"], n_points=fit["n_points"],
        t_end_s=plate.t[max(idx)] if idx else np.nan,
        fit_source="manual" if fit["status"] in BY_HAND else "auto",
        fit_points=describe_indices(idx), idx=idx,
        vmax_auto=auto["slope"] * 60 if auto["status"] in ACCEPTED else np.nan,
        vmax_initial=auto["slope_0"] * 60,
        stopped_by=fit["stopped_by"], status=fit["status"],
        n_available=fit["n_available"], n_timepoints=fit["n_timepoints"],
        a_start=a[0], a_max=np.nanmax(a) if np.isfinite(a).any() else np.nan,
        T_window=float(np.nanmean(plate.temp[list(idx)])) if idx else np.nan,
        saturated=bool(plate.sat[:, j].any()),
    )


def build_fits(plates: dict[str, Plate], autos: dict[str, list[dict]],
               overrides: dict[tuple[str, str], tuple[int, ...]],
               pos_wells: list[str], neg_wells: list[str]) -> pd.DataFrame:
    """One row per (plate, well): the automatic fit, or the manual one where set.

    An override is the readings to fit through, or ``NO_FIT`` for a well with no rate.
    """
    role = {w: "positive" if w in pos_wells else "negative" if w in neg_wells
            else "sample" for w in WELLS}
    records = []
    for name, plate in plates.items():
        for j, well in enumerate(WELLS):
            auto = autos[name][j]
            idx = overrides.get((name, well))
            fit = (auto if idx is None else no_fit(plate.a[:, j]) if idx == NO_FIT
                   else fit_points(plate.t, plate.a[:, j], idx))
            records.append(_row(name, plate, j, fit, auto, role[well]))

    fits = pd.DataFrame(records)
    order = list(plates)
    fits["plate"] = pd.Categorical(fits.plate, order, ordered=True)
    starts = {n: p.started for n, p in plates.items() if p.started}
    t0 = min(starts.values()) if starts else None
    fits["run_order_min"] = fits.plate.map(
        {n: (s - t0).total_seconds() / 60 for n, s in starts.items()}).astype(float)

    ctrl = controls(fits)
    fits["pos_mean_plate"] = fits.plate.map(ctrl.pos_mean).astype(float)
    fits["vmax_norm"] = fits.vmax / fits.pos_mean_plate
    # SE of a ratio, from the well's fit SE and the SEM of the plate's +ctrl mean
    pos_sem = fits.plate.map(ctrl.pos_sd / np.sqrt(ctrl.n_pos)).astype(float)
    fits["vmax_norm_se"] = (np.hypot(fits.se, fits.vmax_norm * pos_sem)
                            / fits.pos_mean_plate.abs())
    return fits


def zprime(pos: pd.Series, neg: pd.Series) -> float:
    if pos.count() < 2 or neg.count() < 2:
        return np.nan
    return 1 - 3 * (pos.std(ddof=1) + neg.std(ddof=1)) / abs(pos.mean() - neg.mean())


def controls(fits: pd.DataFrame) -> pd.DataFrame:
    """Per-plate control statistics and Z'.

    From each control's measured slope, failed fit or not: a no-enzyme control has no
    linear phase by design. Only wells marked no fit by hand drop out.
    """
    out = {}
    for p, d in fits.groupby("plate", observed=True):
        pos, neg = d[d.role == "positive"].line_rate, d[d.role == "negative"].line_rate
        out[p] = dict(clock=d.clock.iloc[0], n_pos=pos.count(), n_neg=neg.count(),
                      pos_mean=pos.mean(), pos_sd=pos.std(ddof=1),
                      neg_mean=neg.mean(), neg_sd=neg.std(ddof=1),
                      zprime=zprime(pos, neg))
    ctrl = pd.DataFrame.from_dict(out, orient="index")
    ctrl.index.name = "plate"
    ctrl["pos_cv_pct"] = 100 * ctrl.pos_sd / ctrl.pos_mean
    ctrl["signal_window"] = ctrl.pos_mean - ctrl.neg_mean
    return ctrl


def read_qc(plates: dict[str, Plate]) -> pd.DataFrame:
    """One row per plate: what was read and how cleanly."""
    return pd.DataFrame([dict(
        plate=n, clock=p.clock,
        timepoints=len(p.t), duration_s=p.t[-1],
        interval_s=round(float(np.median(np.diff(p.t))), 1) if len(p.t) > 1 else np.nan,
        T_min=np.nanmin(p.temp) if np.isfinite(p.temp).any() else np.nan,
        T_max=np.nanmax(p.temp) if np.isfinite(p.temp).any() else np.nan,
        partial_sweeps_dropped=p.dropped, ovrflw=int(p.sat.sum()))
        for n, p in plates.items()]).set_index("plate")


def samples(fits: pd.DataFrame) -> pd.DataFrame:
    return fits[fits.role == "sample"]


def plate_summary(fits: pd.DataFrame) -> pd.DataFrame:
    """Per-plate sample-well distribution beside the controls: the batch-effect table."""
    smp, ctrl = samples(fits), controls(fits)
    g = smp.groupby("plate", observed=True)
    out = pd.DataFrame({
        "run_order_min": fits.groupby("plate", observed=True).run_order_min.first(),
        "med_raw": g.vmax.median(), "med_norm": g.vmax_norm.median(),
        "iqr_raw": g.vmax.quantile(.75) - g.vmax.quantile(.25),
        "n_no_fit": smp[~smp.status.isin(ACCEPTED)].groupby("plate", observed=True).size(),
        "n_manual": fits[fits.status == "manual"].groupby("plate", observed=True).size(),
    }).reindex(ctrl.index).fillna({"n_no_fit": 0, "n_manual": 0})
    return ctrl.join(out)


def cv(s: pd.Series) -> float:
    s = s.dropna()
    return 100 * s.std(ddof=1) / s.mean() if len(s) > 1 else np.nan


def is_edge(d: pd.DataFrame) -> pd.Series:
    """Wells on the plate's outer ring."""
    return d.row.isin([ROWS[0], ROWS[-1]]) | d.col.isin([COLS[0], COLS[-1]])


def _kruskal(smp: pd.DataFrame, col: str, by: str) -> tuple[float, float]:
    groups = [g[col].dropna().values for _, g in smp.groupby(by, observed=True)]
    groups = [g for g in groups if len(g)]
    return kruskal(*groups) if len(groups) > 1 else (np.nan, np.nan)


def batch_stats(fits: pd.DataFrame) -> dict:
    """The numbers behind the batch-effect and spatial views."""
    smp, ps = samples(fits), plate_summary(fits)
    out = dict(cv_raw=cv(ps.med_raw), cv_norm=cv(ps.med_norm))
    edge = is_edge(smp)
    out["kw_row"] = _kruskal(smp, "vmax_norm", "row")
    out["kw_col"] = _kruskal(smp, "vmax_norm", "col")
    e, i = smp.loc[edge, "vmax_norm"].dropna(), smp.loc[~edge, "vmax_norm"].dropna()
    out["edge"] = (e.median(), i.median(),
                   mannwhitneyu(e, i).pvalue if len(e) and len(i) else np.nan)
    return out


def export_table(fits: pd.DataFrame) -> pd.DataFrame:
    return fits[COLUMNS]
