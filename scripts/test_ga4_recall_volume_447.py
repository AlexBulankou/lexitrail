"""lexitrail#447 — `verdict()` must be a partition of POSITIVE tests.

The bug this pins, measured live on 2026-09-13: GA4 returned
`cards_count sum 26, eventCount 122` and `verdict()` answered

    NOT MET: cards_count sum 26 == eventCount 122

— a verdict about the bulk path, asserting an equality that is false on its
own two numbers. NOT_MET was the trailing `else`, so it absorbed a shape
nobody had listed.

🔴 These tests assert the DIRECTION of each branch, not the wording of its
message. A docstring saying "the unrecognised case is refused" is not a
contract; a test that drives the function to that case is.
"""
import importlib.util
import pathlib

import pytest

_SRC = pathlib.Path(__file__).with_name("ga4_recall_volume.py")
_spec = importlib.util.spec_from_file_location("ga4_recall_volume", _SRC)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

MET, NOT_MET, UNDECIDED, ERROR = _mod.MET, _mod.NOT_MET, _mod.UNDECIDED, _mod.ERROR


def test_the_live_2026_09_13_reading_is_undecided_not_a_verdict():
    """26 of 122 events carry the metric — the window straddles registration."""
    rc, msg = _mod.verdict(events=122, cards=26)
    assert rc == UNDECIDED, f"regression: 26/122 reported rc={rc} — {msg}"
    # and it must NOT claim the two numbers are equal
    assert "26 == 122" not in msg


def test_partial_window_is_undecided_for_any_0_lt_cards_lt_events():
    for events, cards in ((122, 26), (10, 9), (2, 1), (100, 1)):
        rc, _ = _mod.verdict(events=events, cards=cards)
        assert rc == UNDECIDED, f"{cards}/{events} should be UNDECIDED, got {rc}"


def test_equal_is_not_met_and_is_a_positive_test():
    rc, msg = _mod.verdict(events=50, cards=50)
    assert rc == NOT_MET
    assert "sum 50 == eventCount 50" in msg, "the NOT MET message states the equality it tests"


def test_greater_is_met():
    rc, _ = _mod.verdict(events=10, cards=25)
    assert rc == MET


def test_zero_sum_is_undecided():
    rc, _ = _mod.verdict(events=99, cards=0)
    assert rc == UNDECIDED


def test_the_three_verdicts_are_distinct_codes():
    """A partition is worthless if two states share a return code."""
    assert len({MET, NOT_MET, UNDECIDED, ERROR}) == 4


@pytest.mark.parametrize("events,cards", [(0, 5), (-1, 3), (10, -5)])
def test_unrecognised_shapes_refuse_rather_than_guess(events, cards):
    """CONTROL — the else-branch must fail ALARMING, never reassuring.

    `events=0, cards=5` is a sum with NO events -- both numbers come from the
    same runReport row, so that is incoherent, not a strong MET. I found this by
    running the test rather than reasoning about it: my first patch returned MET
    here, i.e. a verdict on data it could not explain.

    `(10, -5)` is the shape no other branch claims, and it is why this control
    is not vacuous -- it reached ERROR before the incoherence guard existed.
    """
    rc, msg = _mod.verdict(events=events, cards=cards)
    assert rc == ERROR, f"unrecognised {cards}/{events} returned rc={rc} — {msg}"
    assert rc not in (MET, NOT_MET), "an unknown state must not read as a verdict"
