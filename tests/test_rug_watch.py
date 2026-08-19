import re
import sys

sys.path.insert(0, ".")

from scripts.rug_watch import ELEVATED, SEVERE, severity_for, severity_for_multiday_drawdown

DASHBOARD_TEMPLATE_PATH = "paper_trading/dashboard_template.html"


def _coin(change_24h_pct, pct_from_24h_high):
    return {"change_24h_pct": change_24h_pct, "pct_from_24h_high": pct_from_24h_high}


def test_severity_none_below_both_thresholds():
    assert severity_for(_coin(-5, -5)) is None


def test_severity_elevated_on_change_alone():
    assert severity_for(_coin(-16, -1)) == "elevated"


def test_severity_elevated_on_drawdown_alone():
    assert severity_for(_coin(-1, -26)) == "elevated"


def test_severity_severe_on_change_alone():
    assert severity_for(_coin(-31, -1)) == "severe"


def test_severity_severe_on_drawdown_alone():
    assert severity_for(_coin(-1, -41)) == "severe"


def test_severity_boundary_values_are_inclusive():
    # Exactly at the threshold should trigger, not just past it.
    assert severity_for(_coin(-15, 0)) == "elevated"
    assert severity_for(_coin(-30, 0)) == "severe"


def test_multiday_drawdown_none_below_threshold():
    assert severity_for_multiday_drawdown(-10) is None


def test_multiday_drawdown_elevated():
    assert severity_for_multiday_drawdown(-25) == "elevated"


def test_multiday_drawdown_severe():
    assert severity_for_multiday_drawdown(-40) == "severe"


def test_multiday_drawdown_boundary_values_are_inclusive():
    assert severity_for_multiday_drawdown(-25) == "elevated"
    assert severity_for_multiday_drawdown(-40) == "severe"


def test_dashboard_js_thresholds_match_the_python_source_of_truth():
    # This module's own docstring calls out that dashboard_template.html
    # re-implements these same thresholds in JS with no shared code path -
    # nothing previously checked that the two hadn't drifted apart, which
    # would silently mis-flag or under-flag coins in the live Rug Pull
    # Watch table. Parse the JS constants back out and compare them to the
    # real Python values instead of trusting a comment to stay accurate.
    with open(DASHBOARD_TEMPLATE_PATH) as f:
        js = f.read()

    def _js_object(name):
        m = re.search(
            r"const\s+" + re.escape(name) + r"\s*=\s*\{\s*"
            r"change\s*:\s*(-?\d+(?:\.\d+)?)\s*,\s*"
            r"fromHigh\s*:\s*(-?\d+(?:\.\d+)?)\s*\}",
            js,
        )
        assert m, f"couldn't find `const {name} = {{ change: ..., fromHigh: ... }}` in {DASHBOARD_TEMPLATE_PATH}"
        return {"change": float(m.group(1)), "fromHigh": float(m.group(2))}

    js_severe = _js_object("RUG_SEVERE")
    js_elevated = _js_object("RUG_ELEVATED")

    assert js_severe == {"change": SEVERE["change"], "fromHigh": SEVERE["from_high"]}
    assert js_elevated == {"change": ELEVATED["change"], "fromHigh": ELEVATED["from_high"]}
