"""Synthetic plates: real-shaped kinetics without shipping anyone's data."""

from __future__ import annotations

import io
import sys
from datetime import datetime, time
from pathlib import Path

import numpy as np
import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kineticist.reader import WELLS, Plate  # noqa: E402

T = np.arange(4, 4 + 11 * 120, 11.0)  # 120 reads, 11 s apart, from t = 4 s


def curves(seed: int = 0, scale: float = 1.0) -> np.ndarray:
    """Michaelis-Menten-like progress curves: linear, then bending to a plateau.

    A1-A3 fast (positive control), A4-A6 flat (no enzyme), the rest spread out.
    """
    rng = np.random.default_rng(seed)
    v0 = rng.uniform(0.0002, 0.0012, 96) * scale       # dA/s
    v0[:3], v0[3:6] = 0.0009 * scale, 0.0
    cap = 0.6
    a = 0.3 + cap * (1 - np.exp(-np.outer(T, v0) / cap))
    return np.round(a + rng.normal(0, 0.0005, a.shape), 3)


def make_plate(name="EPI1", seed=0, scale=1.0, hour=15) -> Plate:
    a = curves(seed, scale)
    return Plate(file=f"screen_{name}_x.xlsx", t=T.copy(), temp=np.full(len(T), 29.0),
                 a=a, sat=np.zeros_like(a, bool), dropped=0,
                 started=datetime(2026, 9, 11, hour, 0, 0))


def export_bytes(a: np.ndarray) -> bytes:
    """A minimal kinetic export of absorbance matrix ``a`` (reads x 96), with the
    instrument's own metadata and results, which the reader ignores."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Software Version", "3.18.17"])
    ws.append(["Plate Number", "Plate 6"])
    ws.append(["Date", datetime(2026, 9, 11)])
    ws.append(["Time", time(15, 51, 11)])
    ws.append([])
    ws.append([None, "Time", "T° 340", *WELLS])
    for i, row in enumerate(a):
        s = int(T[i])
        ws.append([None, time(s // 3600, s % 3600 // 60, s % 60), 29, *row.tolist()])
    ws.append([])
    ws.append(["Results"])
    ws.append([None, None, *range(1, 13)])
    for r in "ABCDEFGH":
        ws.append([None, r, *[1.0] * 12])        # V-max, mOD/min
        ws.append([None, None, *[0.99] * 12])    # R2 line beneath it
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def plates():
    return {"EPI1": make_plate("EPI1", 0, 1.0, 15),
            "EPI2": make_plate("EPI2", 1, 1.1, 15),
            "DMS1": make_plate("DMS1", 2, 0.9, 16)}
