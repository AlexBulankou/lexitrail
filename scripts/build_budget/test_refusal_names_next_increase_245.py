#!/usr/bin/env python3
"""A refusal must name an hour that GRANTS something (issue-245).

`next_refill_ts` returns the top of the next local hour unconditionally, but
`accrued()` only rises when `floor(daily * h / 24)` does. At lexitrail's
`daily_build_count = 5` that is 4 hours out of 24 — so 20/24 refusals named an
hour with no new quota, always EARLIER than the truth. Measured live on build
`62fa85aa` (2026-08-29): the gate said "More quota at 21:00 PDT" when the true
next increase was 23:00 PDT.

🔴 These are bug-shaped on purpose: every assertion below FAILS against the
copy this repo shipped before the fix. A test written only against a 24/day
pool is green on the bug, because `next_refill_ts` and the correct answer
COINCIDE at 24/day — which is why AC3's negative control is a separate test
rather than the only one.

Run:  python3 -m pytest scripts/build_budget/test_refusal_names_next_increase_245.py
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import counter  # noqa: E402

PT = counter._tz()
LEXITRAIL_DAILY = 5


def _at(day: int, hour: int, minute: int = 30) -> float:
    return dt.datetime(2026, 8, day, hour, minute, tzinfo=PT).timestamp()


def _refusal_ts(now: float, daily: int) -> float:
    """The timestamp a REFUSAL would name — through `decide`, not the helper.

    Going through `decide` is the point: the helper existing and the refusal
    path using it are two different facts, and only the second one reaches a
    human. Ensemble wired `next_increase_ts` into `allowance.py` and a Slack
    surface too, so a fix could plausibly have landed there and left this path
    on the old value.
    """
    st = counter.new_state(now)
    st["used"] = counter.accrued(daily, now)      # exactly spent -> refuses
    _s, d = counter.decide(st, repo="lexitrail", now_ts=now,
                           daily_total=daily, enforcing=True)
    assert d.would_refuse, "fixture must actually refuse, or this proves nothing"
    return d.refills_at_ts


def test_refusal_names_an_hour_that_actually_grants():
    """AC1, at lexitrail's own daily=5 — every hour of a full day."""
    bad = []
    for h in range(24):
        now = _at(28, h)
        here = counter.accrued(LEXITRAIL_DAILY, now)
        named = _refusal_ts(now, LEXITRAIL_DAILY)
        rolls = counter.day_key(named) != counter.day_key(now)
        if not rolls and counter.accrued(LEXITRAIL_DAILY, named) <= here:
            bad.append((h, dt.datetime.fromtimestamp(named, PT).strftime("%H:%M")))
    assert not bad, f"refusal named a NO-GRANT hour at PT {bad}"


def test_the_measured_live_case():
    """The exact 2026-08-29 refusal: 21:00 PDT was named, 23:00 was the truth."""
    now = _at(28, 20, 30)                      # PT 20:30 == 03:30Z, when it fired
    named = _refusal_ts(now, LEXITRAIL_DAILY)
    assert dt.datetime.fromtimestamp(named, PT).strftime("%H:%M") == "23:00"


def test_negative_control_24_per_day_still_names_the_next_hour():
    """AC3. At 24/day every hour grants, so the two answers must COINCIDE.

    Without this, 'name the next increase' could be satisfied by something that
    skips hours a 24/day pool genuinely refills on.
    """
    for h in range(23):                        # 23:xx crosses the roll; see below
        now = _at(28, h)
        assert _refusal_ts(now, 24) == counter.next_refill_ts(now), f"PT {h}"


def test_the_day_roll_counts_as_an_increase():
    """`accrued` DROPS 24 -> 1 across the roll, yet the roll is the real answer.

    An accrued-only search answers "never" on the eve of a full reset, because
    every remaining boundary of the day is capped. This is the case that made
    my own sweep report a phantom 1/24 failure at daily=24.
    """
    now = _at(28, 23, 30)
    named = _refusal_ts(now, 24)
    assert counter.day_key(named) != counter.day_key(now)
    assert dt.datetime.fromtimestamp(named, PT).strftime("%H:%M") == "00:00"


def test_helper_returns_none_only_on_bad_input():
    assert counter.next_increase_ts(0, _at(28, 12)) is None
    assert counter.next_increase_ts(-1, _at(28, 12)) is None
    assert counter.next_increase_ts(LEXITRAIL_DAILY, _at(28, 12)) is not None
