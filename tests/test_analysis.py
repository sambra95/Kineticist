import numpy as np
import pytest
from conftest import T, curves, export_bytes

from kineticist import analysis
from kineticist.fitting import (FitSettings, describe_indices, fit_initial_rate, fit_points,
                                why_no_fit)
from kineticist.reader import WELLS, read_plate

POS, NEG = ["A1", "A2", "A3"], ["A4", "A5", "A6"]


def test_linear_trace_fills_the_longest_window():
    a = 0.3 + 0.001 * T
    f = fit_initial_rate(T, a)
    assert f["status"] == "ok" and f["stopped_by"] == "max_window"
    assert f["n_points"] == 2 * FitSettings().min_points
    assert f["slope"] == pytest.approx(0.001)


def test_window_ends_with_a_trace_shorter_than_the_longest_window():
    a = 0.3 + 0.001 * T
    a[8] = np.nan
    f = fit_initial_rate(T, a)
    assert f["stopped_by"] == "end_of_trace" and f["idx"] == tuple(range(8))


def test_rolling_window_finds_the_linear_phase_after_a_lag():
    a = 0.3 + 0.001 * np.clip(T - T[30], 0, None)
    f = fit_initial_rate(T, a)
    assert f["status"] == "ok" and f["idx"][0] >= 30
    assert f["slope"] == pytest.approx(0.001) and f["slope_0"] == pytest.approx(0.001)


def test_slope_gate_stops_a_bending_trace_early():
    a = 0.3 + 0.6 * (1 - np.exp(-0.005 * T / 0.6))
    f = fit_initial_rate(T, a, FitSettings(slope_tol=0.05))
    assert f["status"] == "ok" and f["stopped_by"] == "slope_drift"
    assert f["slope"] >= 0.95 * f["slope_0"]
    assert f["n_points"] < 2 * FitSettings().min_points


def test_slope_gate_holds_a_falling_trace_like_a_rising_one():
    rise = 0.3 + 0.6 * (1 - np.exp(-0.005 * T / 0.6))
    up, down = fit_initial_rate(T, rise), fit_initial_rate(T, 1.2 - rise)
    assert down["stopped_by"] == "slope_drift" and down["idx"] == up["idx"]
    assert down["slope"] == pytest.approx(-up["slope"])


def test_flat_trace_has_no_linear_phase():
    f = fit_initial_rate(T, np.full(len(T), 0.3))
    assert f["status"] == "no_linear_fit" and np.isnan(f["r2"])


def test_short_trace_is_insufficient():
    a = 0.3 + 0.001 * T
    a[3] = np.nan
    assert fit_initial_rate(T, a)["status"] == "insufficient_data"


def test_manual_fit_uses_exactly_the_chosen_points():
    a = 0.3 + 0.001 * T
    a[2] += 0.2                                   # an outlier, left out of the pick
    f = fit_points(T, a, (0, 1, 3, 4, 5, 9))
    assert f["idx"] == (0, 1, 3, 4, 5, 9) and f["status"] == "manual"
    assert f["slope"] == pytest.approx(0.001) and f["r2"] == pytest.approx(1.0)


def test_describe_indices():
    assert describe_indices((0, 1, 2, 5, 6, 9)) == "0-2,5-6,9"
    assert describe_indices(()) == ""


def test_export_round_trip():
    a = curves()
    p = read_plate(export_bytes(a), "screen_EPI1.xlsx")
    assert p.a.shape == (len(T), 96) and np.allclose(p.a, a)
    assert np.allclose(p.t, T) and p.clock == "15:51:11"


def test_decimal_comma_export():
    a = curves()
    a[:, 0] += 1.0                                  # A1 >= 1: thousands-grouped by Excel
    p = read_plate(export_bytes(a, comma=True), "screen_EPI1.xlsx")
    assert p.dropped == 0 and np.allclose(p.a, a) and np.allclose(p.temp, 29.4)


def test_build_fits_normalises_and_applies_overrides(plates):
    autos = {n: analysis.auto_fits(p, FitSettings()) for n, p in plates.items()}
    fits = analysis.build_fits(plates, autos, {}, POS, NEG)
    assert len(fits) == 96 * len(plates)
    pos = fits[fits.role == "positive"].groupby("plate", observed=True).vmax_norm.mean()
    assert np.allclose(pos, 1.0)
    neg = fits[fits.role == "negative"]
    assert (neg.status == "no_linear_fit").all() and neg.vmax.isna().all()
    assert neg.vmax_norm.isna().all() and neg.line_rate.notna().all()
    assert (fits.vmax_norm_se.dropna() >= 0).all()

    over = {("EPI1", "B7"): (0, 1, 2, 3)}
    edited = analysis.build_fits(plates, autos, over, POS, NEG).set_index("label")
    row = edited.loc["EPI1-B7"]
    assert row.fit_source == "manual" and row.n_points == 4 and row.fit_points == "0-3"
    assert row.vmax_auto == pytest.approx(fits.set_index("label").loc["EPI1-B7"].vmax)


def test_no_fit_override_leaves_vmax_empty(plates):
    autos = {n: analysis.auto_fits(p, FitSettings()) for n, p in plates.items()}
    over = {("EPI1", "B7"): analysis.NO_FIT, ("EPI1", "A1"): analysis.NO_FIT}
    fits = analysis.build_fits(plates, autos, over, POS, NEG).set_index("label")
    row = fits.loc["EPI1-B7"]
    assert row.status == "excluded" and row.fit_source == "manual" and row.n_points == 0
    assert np.isnan(row.vmax) and np.isnan(row.se) and np.isnan(row.vmax_norm)
    assert np.isfinite(row.vmax_auto)
    ctrl = analysis.controls(fits.reset_index())
    assert ctrl.loc["EPI1", "n_pos"] == 2 and np.isfinite(ctrl.loc["EPI1", "pos_mean"])
    ps = analysis.plate_summary(fits.reset_index())
    assert ps.loc["EPI1", "n_no_fit"] == 1 and ps.loc["EPI1", "n_manual"] == 0


def test_summaries_run(plates):
    autos = {n: analysis.auto_fits(p, FitSettings()) for n, p in plates.items()}
    fits = analysis.build_fits(plates, autos, {}, POS, NEG)
    ctrl = analysis.controls(fits)
    assert (ctrl.zprime > 0.5).all()
    ps = analysis.plate_summary(fits)
    assert list(ps.index) == list(plates)
    stats = analysis.batch_stats(fits)
    assert np.isfinite(stats["cv_raw"]) and np.isfinite(stats["cv_norm"])
    assert list(analysis.export_table(fits).columns) == analysis.COLUMNS
    assert set(WELLS) == set(fits.well)


def test_why_no_fit_names_the_check_and_a_passing_setting():
    rng = np.random.default_rng(1)
    noisy = 0.3 + rng.normal(0, 0.002, len(T))     # no window of 5-10 reaches R2 0.95
    s = FitSettings()
    assert fit_initial_rate(T, noisy, s)["status"] == "no_linear_fit"
    why = why_no_fit(T, noisy, s)
    assert why["check"] == "r2"
    assert why["r2_max"] == pytest.approx(np.floor(why["r2_0"] * 1000) / 1000)
    # each suggestion really does pass
    assert fit_initial_rate(T, noisy, FitSettings(r2_threshold=why["r2_max"]))["status"] == "ok"
    assert fit_initial_rate(T, noisy, FitSettings(min_points=why["window"][0]))["status"] == "ok"

    assert why_no_fit(T, np.full(len(T), 0.3))["check"] == "flat"
    short = 0.3 + 0.001 * T
    short[3] = np.nan
    why = why_no_fit(T, short)
    assert why["check"] == "short" and why["n_available"] == 3 and why["window"][0] == 3
