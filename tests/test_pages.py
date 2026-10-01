"""Every page renders, headless, against synthetic plates."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from kineticist.fitting import FitSettings
from session import Data

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["fits", "rates", "qc", "export", "about"]


def run(page: str, plates, overrides=None) -> AppTest:
    at = AppTest.from_file(str(ROOT / "app_pages" / f"{page}.py"), default_timeout=30)
    at.session_state["data"] = Data(plates=plates, ids={n: n for n in plates},
                                    settings=FitSettings(), pos=["A1", "A2", "A3"],
                                    neg=["A4", "A5", "A6"])
    at.session_state["overrides"] = overrides or {}
    at.session_state["nonce"] = 0
    return at.run()


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page, plates):
    at = run(page, plates)
    assert not at.exception, at.exception


def test_fits_page_shows_a_manual_fit(plates):
    at = run("fits", plates, {("EPI1", "A1"): (0, 1, 2, 3, 4, 5)})
    assert not at.exception
    assert any("Manual fit" in m.value for m in at.markdown)
    assert any("vs auto" in m.value for m in at.markdown)


def test_a_failed_fit_names_its_check(plates):
    at = run("fits", plates)
    at.session_state["well"] = "A4"            # a no-enzyme control: no linear phase
    at.run()
    assert any("R²" in m.value and "<" in m.value for m in at.markdown)
    at.session_state["well"] = "B1"            # a sample with a fit
    at.run()
    assert any("Linear fit" in m.value for m in at.markdown)


def test_rates_colour_by_sample_type(plates):
    at = run("rates", plates)
    at.segmented_control(key="rates_colour").set_value("Sample type").run()
    assert not at.exception, at.exception


def test_qc_with_one_plate_skips_only_batch_effects(plates):
    at = run("qc", {"EPI1": plates["EPI1"]})
    assert not at.exception, at.exception
    assert any("at least two" in m.value for m in at.info)
    assert any("Controls" in s.value for s in at.subheader)
