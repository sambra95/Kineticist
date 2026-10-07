"""Initial-rate ("V-max") fitting of a single progress curve.

The automatic fit is a rolling slope: windows of every length from ``min_points``
to twice that slide across the trace, and each gets a least-squares slope. Windows
with R2 < ``r2_threshold`` are dropped; the steepest survivor, in whichever direction
the trace runs, is the reference rate. The fit reported is the longest surviving
window whose rate is no more than ``slope_tol`` below the reference: the extra
readings steady the slope, and the slope gate holds them to the linear phase (these
curves bend while R2 stays above 0.99, so R2 alone over-runs into substrate depletion).

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
    min_points: int = 5        # shortest sliding window; the longest is twice this
    r2_threshold: float = 0.95  # gate 1: a window counts only with R2 at or above this
    slope_tol: float = 0.05     # gate 2: and with its rate no more than this below the steepest


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


def _rolling(x: np.ndarray, y: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Slope and R2 of every ``n``-point window, element for element what :func:`ols` gives."""
    xw = np.lib.stride_tricks.sliding_window_view(x, n)
    yw = np.lib.stride_tricks.sliding_window_view(y, n)
    xc = xw - xw.mean(axis=1, keepdims=True)
    yc = yw - yw.mean(axis=1, keepdims=True)
    sxx = (xc * xc).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        slope = np.where(sxx > 0, (xc * yc).sum(axis=1) / sxx, np.nan)
        ss_res = ((yc - slope[:, None] * xc) ** 2).sum(axis=1)
        ss_tot = (yc * yc).sum(axis=1)
        noise_floor = 16 * n * (np.finfo(float).eps
                                * np.maximum(np.abs(yw).max(axis=1), 1e-12)) ** 2
        r2 = np.where(ss_tot > noise_floor, 1 - ss_res / ss_tot, np.nan)
    return slope, r2


def _windows(t: np.ndarray, a: np.ndarray, m: int, n_avail: int) -> dict:
    """Rolling slope and R2 for each window length ``m``..``2m`` that fits the readings."""
    return {n: _rolling(t[:n_avail], a[:n_avail], n) for n in range(m, min(2 * m, n_avail) + 1)}


def _best_r2(scan: dict) -> float:
    """The highest R2 of any window in a scan; NaN if every window is flat."""
    r2 = np.concatenate([r for _, r in scan.values()]) if scan else np.array([])
    return float(np.nanmax(r2)) if np.isfinite(r2).any() else np.nan


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
    """Automatic initial rate. ``status`` is ok / no_linear_fit / insufficient_data.

    ``slope_0`` is the reference rate, the steepest window passing R2. ``stopped_by``
    says why the window is no longer: ``end_of_trace`` (it spans every valid reading),
    ``max_window`` (it is the longest window tried), ``slope_drift`` (a longer window
    passes R2 but not the slope gate) or ``r2`` (no longer window passes R2).
    """
    n_avail, n_tp, m = _leading_valid(a), len(a), s.min_points

    if n_avail < m:
        return _result(np.nan, np.nan, np.nan, np.nan, (), "no_data",
                       "insufficient_data", np.nan, n_avail, n_tp)

    scan = _windows(t, a, m, n_avail)
    passing = {n: r2 >= s.r2_threshold for n, (_, r2) in scan.items()}  # NaN fails too
    if not any(p.any() for p in passing.values()):
        # No linear stretch anywhere: report the first window's line, flagged.
        slope_0, intercept_0, r2_0, se_0 = ols(t[:m], a[:m])
        return _result(slope_0, intercept_0, r2_0, se_0, range(m), "r2_at_start",
                       "no_linear_fit", slope_0, n_avail, n_tp)

    # The trace runs the way of its steepest linear stretch; that rate is the reference.
    rates = np.concatenate([scan[n][0][p] for n, p in passing.items()])
    slope_0 = rates[np.argmax(np.abs(rates))]
    sign, floor = np.sign(slope_0), (1 - s.slope_tol) * abs(slope_0)

    # Longest window passing both gates; the steepest of that length, then the earliest.
    both = {n: np.where(p & (sign * scan[n][0] >= floor), sign * scan[n][0], -np.inf)
            for n, p in passing.items()}
    n = max(n for n, rate in both.items() if np.isfinite(rate).any())
    start = int(np.argmax(both[n]))

    longer = [k for k in passing if k > n]
    stopped_by = ("end_of_trace" if n == n_avail else "max_window" if not longer
                  else "slope_drift" if any(passing[k].any() for k in longer) else "r2")
    idx = range(start, start + n)
    slope, intercept, r2, se = ols(t[idx.start:idx.stop], a[idx.start:idx.stop])
    return _result(slope, intercept, r2, se, idx, stopped_by, "ok",
                   slope_0, n_avail, n_tp)


def why_no_fit(t: np.ndarray, a: np.ndarray, s: FitSettings = FitSettings()) -> dict:
    """Which check an automatic fit failed, and the nearest settings that pass it.

    ``check`` is 'short' (fewer readings than the shortest window before the trace is
    cut by a missing or saturated reading), 'flat' (every window is constant to the
    reader's resolution, so R2 is undefined) or 'r2' (no window reaches the minimum R2).
    ``r2_0`` is the best R2 of any window. ``window`` is the shortest-window size, within
    MIN_POINTS_RANGE and nearest the current one, for which some window clears the
    current minimum, with that window's R2; None if none does. ``r2_max`` is the highest
    minimum R2 the current windows pass, or None if there is none within R2_RANGE.
    """
    n_avail, m = _leading_valid(a), s.min_points
    r2_0 = _best_r2(_windows(t, a, m, n_avail)) if n_avail >= m else np.nan
    check = "short" if n_avail < m else "flat" if not np.isfinite(r2_0) else "r2"

    lo, hi = MIN_POINTS_RANGE
    best = {n: _best_r2({n: _rolling(t[:n_avail], a[:n_avail], n)})
            for n in range(lo, min(2 * hi, n_avail) + 1)}
    passing = [(n, r2) for n in range(lo, min(hi, n_avail) + 1)
               if (r2 := np.nanmax([best[k] for k in range(n, min(2 * n, n_avail) + 1)]
                                   + [-np.inf])) >= s.r2_threshold]
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


def no_fit(a: np.ndarray) -> dict:
    """A well marked by hand as having no rate: every fitted value is NaN."""
    return _result(np.nan, np.nan, np.nan, np.nan, (), "excluded", "excluded",
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
