"""Quality control: what was read, how the fits went, the controls and Z', and batch
effects between and within plates."""

import numpy as np
import streamlit as st

import session
from kineticist import analysis, plots, theme

d = session.require()
fits = session.fits(d)
ctrl = analysis.controls(fits)
qc = analysis.read_qc(d.plates)
NUM = st.column_config.NumberColumn

with st.container(horizontal=True):
    st.metric("Plates", len(d.plates), border=True)
    st.metric("Wells", len(fits), border=True)
    st.metric("Linear fit", int((fits.status == "ok").sum()), border=True)
    st.metric("No linear phase", int((fits.status == "no_linear_fit").sum()), border=True)
    st.metric("Fitted by hand", int((fits.status == "manual").sum()), border=True)
    st.metric("Marked no fit", int((fits.status == "excluded").sum()), border=True)
    st.metric("Z′ range", f"{ctrl.zprime.min():.2f} – {ctrl.zprime.max():.2f}"
              if ctrl.zprime.notna().any() else "–", border=True)

if fits.saturated.any():
    st.warning(f"{int(fits.saturated.sum())} wells hit detector saturation (OVRFLW). Those "
               "readings are dropped and each fit uses the readings before them.",
               icon=":material/warning:")
if (fits.status == "insufficient_data").any():
    st.warning(f"{int((fits.status == 'insufficient_data').sum())} wells have fewer "
               f"readings than the {d.settings.min_points}-point initial window.",
               icon=":material/warning:")

with st.container(border=True):
    st.subheader("Controls and Z′", anchor=False)
    st.dataframe(ctrl[["clock", "pos_mean", "pos_sd", "pos_cv_pct", "neg_mean", "neg_sd",
                       "signal_window", "zprime"]],
                 column_config={"clock": "Read", "pos_mean": NUM("+ctrl mean", format="%.4f"),
                                "pos_sd": NUM("+ctrl SD", format="%.4f"),
                                "pos_cv_pct": NUM("+ctrl CV %", format="%.1f"),
                                "neg_mean": NUM("−ctrl mean", format="%+.4f"),
                                "neg_sd": NUM("−ctrl SD", format="%.4f"),
                                "signal_window": NUM("Signal window", format="%.4f"),
                                "zprime": st.column_config.ProgressColumn(
                                    "Z′", format="%.2f", min_value=0, max_value=1)})
    st.plotly_chart(plots.controls_by_plate(fits, list(d.plates),
                                            {p: v.clock for p, v in d.plates.items()}),
                    key="controls")
    neg = fits[fits.role == "negative"].line_rate
    if len(neg) and ctrl.pos_mean.notna().any():
        st.caption(f"Negative controls: mean {neg.mean():+.5f}, largest |rate| "
                   f"{neg.abs().max():.5f} ΔA₃₄₀/min "
                   f"({100 * neg.abs().max() / ctrl.pos_mean.mean():.1f} % of the mean "
                   f"+ctrl). Positive controls between plates: CV "
                   f"{analysis.cv(ctrl.pos_mean):.1f} %.")

with st.container(border=True):
    st.subheader("Reads and fits", anchor=False)
    st.dataframe(qc, column_config={
        "clock": "Read",
        "timepoints": "Reads", "duration_s": NUM("Duration (s)", format="%.0f"),
        "interval_s": NUM("Interval (s)", format="%.1f"),
        "T_min": NUM("T min (°C)", format="%.1f"), "T_max": NUM("T max (°C)", format="%.1f"),
        "partial_sweeps_dropped": NUM("Partial sweeps dropped"),
        "ovrflw": NUM("OVRFLW readings")})
    status = (fits.groupby(["role", "status"], observed=True).size()
              .unstack(fill_value=0).reindex(["positive", "negative", "sample"]).dropna(how="all"))
    st.markdown("**Fit status by role**")
    st.dataframe(status.astype(int))
    ok = fits[fits.status == "ok"]
    bound = ok[ok.stopped_by == "slope_drift"]
    if len(bound):
        drop = 100 * (1 - bound.vmax / bound.vmax_initial)
        st.caption(f"The slope gate ended the window on {len(bound)} wells, holding them "
                   f"to a median {drop.median():.1f} % (max {drop.max():.1f} %) below their "
                   f"{d.settings.min_points}-point slope. Window lengths: "
                   f"{ok.n_points.min()}–{ok.n_points.max()} readings "
                   f"(median {ok.n_points.median():.0f}).")


def p_value(v: float) -> str:
    return f"{v:.1e}" if np.isfinite(v) else "–"


st.header("Batch effects", anchor=False)
if len(d.plates) < 2:
    st.info("Batch effects compare plates; upload at least two.", icon=":material/info:")
elif ctrl.pos_mean.isna().all():
    st.warning("Set positive-control wells in the sidebar: the batch views compare raw "
               "rates with rates normalised to them.", icon=":material/warning:")
else:
    ps = analysis.plate_summary(fits)
    stats = analysis.batch_stats(fits)
    with st.container(border=True):
        st.subheader("Plates side by side", anchor=False)
        st.dataframe(ps[["run_order_min", "med_raw", "med_norm", "iqr_raw", "n_no_fit",
                         "n_manual"]],
                     column_config={"run_order_min": NUM("Run order (min)", format="%.1f"),
                                    "med_raw": NUM("Sample median", format="%.4f"),
                                    "med_norm": NUM("Sample median, norm.", format="%.3f"),
                                    "iqr_raw": NUM("Sample IQR", format="%.4f"),
                                    "n_no_fit": NUM("No linear phase", format="%d"),
                                    "n_manual": NUM("Manual fits", format="%d")})

        left, right = st.columns(2, gap="medium")
        with left:
            st.markdown(f"**Sample wells, raw** · between-plate CV of the median "
                        f"{stats['cv_raw']:.0f} %")
            st.plotly_chart(plots.sample_distributions(
                fits, "vmax", analysis.samples(fits).vmax.median(), theme.RATE_LAB),
                key="dist_raw")
        with right:
            st.markdown(f"**Sample wells, normalised to plate +ctrl** · CV "
                        f"{stats['cv_norm']:.0f} %")
            st.plotly_chart(plots.sample_distributions(fits, "vmax_norm", 1.0,
                                                       theme.NORM_LAB), key="dist_norm")

    with st.container(border=True):
        st.subheader("Spatial effects within plates", anchor=False)
        st.plotly_chart(plots.spatial_marginals(fits), key="spatial")
        em, im, ep = stats["edge"]
        st.caption(f"Row effect: Kruskal p = {p_value(stats['kw_row'][1])} · column "
                   f"effect: Kruskal p = {p_value(stats['kw_col'][1])} · edge vs interior: "
                   f"median {em:.3f} vs {im:.3f}, Mann–Whitney p = {p_value(ep)}.")
