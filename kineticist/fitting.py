"""Initial-rate ("V-max") fitting of a single progress curve.

The automatic fit starts from the first ``min_points`` readings and extends the
window one point at a time for as long as it keeps R2 >= ``r2_threshold`` AND
keeps the rate from falling more than ``slope_tol`` below the initial-window rate,
in whichever direction the trace runs. The slope gate is what holds the window to
the linear phase: these curves bend while cumulative R2 stays above 0.99, so R2
alone over-runs into substrate depletion.

A manual fit is an ordinary least-squares line through exactly the readings
the user picked.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


#: What the sidebar accepts for each setting, so a suggested change is one it takes.
MIN_POINTS_RANGE = (3, 50)
R2_RANGE = (0.5, 0.999)


@dataclass(frozen=True)
class FitSettings:
    min_points: int = 5        # initial window; its slope is the reference rate
    r2_threshold: float = 0.95  # gate 1: extend while R2 stays at or above this
    slope_tol: float = 0.05     # gate 2: and while the rate falls no more than this fraction


def ols(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float, float]:
    """Slope, intercept, R2 and slope standard error for a 1-D least-squares fit.

    Mean-centred rather than the raw normal equations: with t ~ 1e2 s and
    A ~ 1e-1 the uncentred sums cancel catastrophically on wells that are
    constant to the reader's 3-decimal resolution.
    """
    n = len(x)
    xc, yc = x - x.mean(), y - y.mean()
    sxx = (xc * xc).sum()
    if sxx == 0:
        return np.nan, np.nan, np.nan, np.nan

    slope = (xc * yc).sum() / sxx
    intercept = y.mean() - slope * x.mean()
    ss_res = ((yc - slope * xc) ** 2).sum()
    ss_tot = (yc * yc).sum()

    # A trace flat to within floating-point noise carries no signal, so R2 is
    # undefined rather than 0 or 1. The floor only ever catches exactly-constant wells.
    noise_floor = 16 * n * (np.finfo(float).eps * max(np.abs(y).max(), 1e-12)) ** 2
    r2 = 1 - ss_res / ss_tot if ss_tot > noise_floor else np.nan

    se = np.sqrt(ss_res / (n - 2) / sxx) if n > 2 else np.nan
    return slope, intercept, r2, se


def _leading_valid(a: np.ndarray) -> int:
    """Readings before the first missing or saturated one."""
    bad = ~np.isfinite(a)
    return int(np.argmax(bad)) if bad.any() else len(a)


def _result(slope, intercept, r2, se, idx, stopped_by, status, slope_0, n_avail, n_tp):
    """One fit as a flat dict; ``slope``/``se`` are per second, ``idx`` the readings used."""
    return dict(slope=slope, intercept=intercept, r2=r2, se=se,
                idx=tuple(int(i) for i in idx), n_points=len(idx),
                slope_0=slope_0, stopped_by=stopped_by, status=status,
                n_available=n_avail, n_timepoints=n_tp)


def fit_initial_rate(t: np.ndarray, a: np.ndarray, s: FitSettings = FitSettings()) -> dict:
    """Automatic initial rate. ``status`` is ok / no_linear_fit / insufficient_data."""
    n_avail, n_tp, m = _leading_valid(a), len(a), s.min_points

    if n_avail < m:
        return _result(np.nan, np.nan, np.nan, np.nan, (), "no_data",
                       "insufficient_data", np.nan, n_avail, n_tp)

    slope_0, intercept_0, r2_0, se_0 = ols(t[:m], a[:m])
    if not (r2_0 >= s.r2_threshold):             # NaN-safe: undefined R2 fails too
        return _result(slope_0, intercept_0, r2_0, se_0, range(m), "r2_at_start",
                       "no_linear_fit", slope_0, n_avail, n_tp)

    best, stopped_by = (slope_0, intercept_0, r2_0, se_0, m), "end_of_trace"
    sign, floor = np.sign(slope_0), (1 - s.slope_tol) * abs(slope_0)
    for n in range(m + 1, n_avail + 1):
        slope, intercept, r2, se = ols(t[:n], a[:n])
        if not (r2 >= s.r2_threshold):
            stopped_by = "r2"; break
        if sign * slope < floor:
            stopped_by = "slope_drift"; break
        best = (slope, intercept, r2, se, n)

    slope, intercept, r2, se, n = best
    return _result(slope, intercept, r2, se, range(n), stopped_by, "ok",
                   slope_0, n_avail, n_tp)


def why_no_fit(t: np.ndarray, a: np.ndarray, s: FitSettings = FitSettings()) -> dict:
    """Which check an automatic fit failed, and the nearest settings that pass it.

    ``check`` is 'short' (fewer readings than the initial window before the trace is
    cut by a missing or saturated reading), 'flat' (the initial window is constant to
    the reader's resolution, so R2 is undefined) or 'r2' (its R2 is below the minimum).
    ``window`` is the initial-window size, within MIN_POINTS_RANGE and nearest the
    current one, whose R2 clears the current minimum, with that R2; None if none does.
    ``r2_max`` is the highest minimum R2 the current window passes, or None if there is
    none within R2_RANGE.
    """
    n_avail, m = _leading_valid(a), s.min_points
    r2_0 = ols(t[:m], a[:m])[2] if n_avail >= m else np.nan
    check = "short" if n_avail < m else "flat" if not np.isfinite(r2_0) else "r2"

    lo, hi = MIN_POINTS_RANGE
    passing = [(n, r2) for n in range(lo, min(hi, n_avail) + 1)
               if (r2 := ols(t[:n], a[:n])[2]) >= s.r2_threshold]
    window = min(passing, key=lambda p: (abs(p[0] - m), p[0])) if passing else None
    r2_max = (np.floor(r2_0 * 1000) / 1000
              if np.isfinite(r2_0) and r2_0 >= R2_RANGE[0] else None)
    return dict(check=check, n_available=n_avail, r2_0=r2_0, window=window, r2_max=r2_max)


def fit_points(t: np.ndarray, a: np.ndarray, idx: tuple[int, ...]) -> dict:
    """Manual fit through exactly the readings ``idx`` (gaps allowed)."""
    idx = tuple(sorted(i for i in set(idx) if 0 <= i < len(a) and np.isfinite(a[i])))
    slope, intercept, r2, se = (ols(t[list(idx)], a[list(idx)]) if len(idx) >= 2
                                else (np.nan,) * 4)
    return _result(slope, intercept, r2, se, idx, "manual", "manual",
                   np.nan, _leading_valid(a), len(a))


def describe_indices(idx: tuple[int, ...]) -> str:
    """Compact run-length text for a set of reading indices: (0,1,2,5,6) -> '0-2,5-6'."""
    if not idx:
        return ""
    runs, start, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i != prev + 1:
            runs.append((start, prev)); start = i
        prev = i
    runs.append((start, prev))
    return ",".join(f"{a}-{b}" if a != b else f"{a}" for a, b in runs)
