import sys

sys.path.insert(0, ".")

from scripts.rug_watch import severity_for


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
