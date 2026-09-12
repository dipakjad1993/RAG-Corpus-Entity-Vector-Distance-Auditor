"""Reporting percent helpers: fractions scale, percents pass through.

Regression test for the v1.2.0 `1810%` / `10000%` double-scaling bug.
No network, no models.
"""

from ragevda.reporting.pdf_report import _pct as pdf_pct, _pct100 as pdf_pct100
from ragevda.reporting.narrative import _pct as nar_pct, _pct100 as nar_pct100


def test_fraction_scales():
    assert pdf_pct(0.181) == "18.1%"
    assert nar_pct(0.5) == "50.0%"


def test_already_percent_passthrough():
    assert pdf_pct(18.1) == "18.1%"
    assert pdf_pct100(18.1) == "18.1%"
    assert nar_pct100(100.0) == "100.0%"
    assert pdf_pct100(28.0) == "28.0%"


def test_missing_renders_dash():
    assert pdf_pct(None) == "—"
    assert pdf_pct100(None) == "—"
    assert nar_pct100(None) == "&mdash;"
