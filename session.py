"""Streamlit glue: the sidebar inputs, cached parsing and fitting, and manual fits.

Everything per-user lives in ``st.session_state``; ``kineticist/`` stays free of
Streamlit so the analysis can be tested and reused on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import count

import pandas as pd
import streamlit as st

from kineticist import analysis
from kineticist.fitting import MIN_POINTS_RANGE, R2_RANGE, FitSettings
from kineticist.reader import WELLS, Plate, read_plate


@dataclass
class Data:
    plates: dict[str, Plate]     # plate name -> parsed read, in display order
    ids: dict[str, str]          # plate name -> uploaded file id (cache key)
    settings: FitSettings
    pos: list[str]
    neg: list[str]


def init() -> None:
    """All session state, initialised in one place."""
    st.session_state.setdefault("overrides", {})   # (plate, well) -> reading indices,
                                                   # or analysis.NO_FIT
    st.session_state.setdefault("nonce", 0)        # bumped to reset a chart's selection
    st.session_state.setdefault("data", None)       # the analysis the pages show
    st.session_state.setdefault("staged", None)     # what Analyse would run now
    st.session_state.setdefault("plate_names", {})  # uploaded file id -> plate name


# ---------------------------------------------------------------- cached work
# Shared, not copied per call: plates and fits are only ever read.
@st.cache_resource(max_entries=200, show_spinner="Reading plates…")
def _parse(file_id: str, _data: bytes, filename: str) -> Plate:
    return read_plate(_data, filename)


@st.cache_resource(max_entries=200, show_spinner="Fitting wells…")
def _auto(file_id: str, settings: FitSettings, _plate: Plate) -> list[dict]:
    return analysis.auto_fits(_plate, settings)


def autos(d: Data) -> dict[str, list[dict]]:
    return {n: _auto(d.ids[n], d.settings, p) for n, p in d.plates.items()}


def fits(d: Data) -> pd.DataFrame:
    """The per-well table: cached automatic fits with the manual ones laid over."""
    return analysis.build_fits(d.plates, autos(d), st.session_state.overrides, d.pos, d.neg)


# ---------------------------------------------------------------- manual fits
def set_override(plate: str, well: str, idx: tuple[int, ...]) -> None:
    st.session_state.overrides[(plate, well)] = idx


def set_no_fit(plate: str, well: str) -> None:
    st.session_state.overrides[(plate, well)] = analysis.NO_FIT
    st.session_state.nonce += 1


def clear_override(plate: str, well: str) -> None:
    st.session_state.overrides.pop((plate, well), None)
    st.session_state.nonce += 1


# ---------------------------------------------------------------- sidebar
def _plate_table(plates: dict[str, Plate]) -> pd.DataFrame:
    """One row per uploaded file, in upload order, with its plate name: Plate 1,
    Plate 2, ... until renamed. Names are kept per file, so adding or removing a file
    leaves the other plates' names alone."""
    names = st.session_state.plate_names
    for pos, i in enumerate(plates, start=1):   # its upload position, or the next free
        if i not in names:
            taken = {names[j] for j in plates if j in names}
            names[i] = next(f"Plate {n}" for n in count(pos) if f"Plate {n}" not in taken)
    return pd.DataFrame({"plate": [names[i] for i in plates],
                         "file": [plates[i].file for i in plates]}, index=list(plates))


def _signature(d: Data | None) -> tuple | None:
    """What an analysis was run on: files and their names, settings and controls."""
    return d and (tuple(d.ids.items()), d.settings, tuple(d.pos), tuple(d.neg))


def sidebar() -> None:
    """Uploads, plate names, control wells and fit settings, applied by Analyse.

    The inputs are staged in ``session_state.staged``; only the Analyse button copies
    them to ``session_state.data``, the analysis every page shows, and in doing so
    discards every manual fit and no-fit mark. Every input is drawn on every run (a
    widget that is not drawn forgets its value); the checks come after.
    """
    with st.sidebar:
        files = st.file_uploader(
            "Kinetic exports", type=["xlsx"], accept_multiple_files=True,
            key="uploads", help="One .xlsx kinetic export per plate.")
        table_slot = st.container()

        with st.expander("Control wells", icon=":material/science:"):
            pos = st.multiselect("Positive control", WELLS, default=["A1", "A2", "A3"],
                                 key="pos_wells", placeholder="None",
                                 help="Every rate is normalised to the mean of these, "
                                      "plate by plate.")
            neg = st.multiselect("Negative control (no enzyme)", WELLS,
                                 default=["A4", "A5", "A6"], key="neg_wells",
                                 placeholder="None",
                                 help="Used with the positive controls for Z′.")
        with st.expander("Fit settings", icon=":material/tune:"):
            settings = FitSettings(
                min_points=st.number_input(
                    "Initial window (points)", *MIN_POINTS_RANGE, 5, key="min_points",
                    help="The shortest sliding window; the longest is twice this."),
                r2_threshold=st.number_input(
                    "Minimum R²", *R2_RANGE, 0.95, 0.01, key="r2", format="%.3f",
                    help="A window counts only with R² at or above this."),
                slope_tol=st.number_input(
                    "Slope tolerance", 0.01, 0.5, 0.05, 0.01, key="slope_tol",
                    format="%.2f",
                    help="The longest window whose rate is no more than this fraction "
                         "below the steepest window's gives V-max."),
            )
        action_slot = st.container()

    st.session_state.staged = _stage(files, table_slot, settings, pos, neg)
    staged, data = st.session_state.staged, st.session_state.data

    with action_slot:
        if st.button("Analyse", type="primary", icon=":material/play_arrow:",
                     width="stretch", disabled=staged is None,
                     help="Fit every well afresh with the settings above. Discards all "
                          "manual fits and no-fit marks."):
            st.session_state.data = data = staged
            st.session_state.overrides = {}
            st.session_state.nonce += 1
        if staged is not None and _signature(staged) != _signature(data):
            st.caption(":orange[:material/pending:] Changes not yet analysed."
                       if data is not None else "Click Analyse to fit the plates.")


def _stage(files, table_slot, settings: FitSettings, pos: list[str],
           neg: list[str]) -> Data | None:
    """The uploads, named and checked, as the next analysis; None if there is none."""
    plates, errors = {}, []
    for f in files or []:
        try:
            plates[f.file_id] = _parse(f.file_id, f.getvalue(), f.name)
        except Exception as exc:  # a malformed file should not take the app down
            errors.append(f"{f.name}: {exc}")

    with table_slot:
        for e in errors:
            st.error(e, icon=":material/error:")
        if not plates:
            return None
        st.subheader("Plates", anchor=False)
        named = st.data_editor(
            _plate_table(plates), hide_index=True, disabled=["file"],
            key="names-" + "-".join(sorted(plates)),
            column_config={
                "plate": st.column_config.TextColumn("Plate", required=True, width="small"),
                "file": st.column_config.TextColumn("File")})
        names = named.plate.str.strip()
        st.session_state.plate_names.update(names)
        if names.duplicated().any() or (names == "").any():
            st.error("Every plate needs its own, non-empty name.", icon=":material/error:")
            return None
        if set(pos) & set(neg):
            st.error("A well cannot be both a positive and a negative control.",
                     icon=":material/error:")
            return None

    return Data(plates={names[i]: plates[i] for i in named.index},
                ids={names[i]: i for i in named.index},
                settings=settings, pos=pos, neg=neg)


def require() -> Data:
    """The loaded data, or a pointer to the sidebar and a stop."""
    d = st.session_state.get("data")
    if d is None:
        if st.session_state.get("staged") is not None:
            st.info("Click **Analyse** in the sidebar to fit the plates.",
                    icon=":material/play_arrow:")
        else:
            st.info("Upload one or more kinetic exports (.xlsx) in the sidebar to begin.",
                    icon=":material/upload_file:")
        st.stop()
    return d
