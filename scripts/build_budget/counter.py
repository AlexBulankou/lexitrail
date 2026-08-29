"""issue-7947 / goal 1.1 — per-repo BUILD-COUNT quota (the enforcement unit).

Replaces dollars as the ENFORCEMENT unit. Dollars survive as the RECALIBRATOR
(`reconcile` recomputes each repo's p90 cost/build and the daily count falls
automatically if builds get fatter) — see `bucket.py`, which is not retired.

🔴 WHY COUNTS AND NOT DOLLARS, and it is not a preference (zz1, 2026-08-09):

    A build's dollar cost is not knowable until it FINISHES — the cost model
    needs a duration. So a dollar quota is STRUCTURALLY INCAPABLE of refusing a
    build at admission; it can only ever indict one that already ran. A count is
    known at createTime. That is the difference between a quota and a report.

Every dollar-measurement defect fixed on 2026-08-09 was a dollar-measurement
defect: a wrong project id, unswept regions, a UTC date boundary, a partial
sweep, and a billing export that lags hours AND whose newest day is incomplete.
Counting builds has none of those failure modes: the build either happened or it
did not.

A DAILY COUNTER, NOT A TOKEN BUCKET — the difference is the whole point.

A rolling bucket with a one-day cap still permits a day's banked quota PLUS a
day's refill inside one window straddling midnight, i.e. 2x on a rolling 24h.
Alex asked for "the same day", which means a HARD RESET: accrue hourly, bank
unused hours, never exceed the day's total, zero at midnight PT. That is what
makes the daily ceiling a real ceiling.

Pure functions over an explicit state dict. No I/O, no clock: `now_ts` is passed
in. Same split as `bucket.py` — this module owns the arithmetic, the caller owns
durability and cross-project atomicity. That is what makes the reset boundary
and the DST cases unit-testable rather than something you observe in production
once a year.

✅ DST IS A NON-ISSUE, and the reason is the wall-clock hour INDEX — not the cap.

🔴 An earlier version of this docstring claimed the long day would over-grant
25/24 and that `accrued()`'s `min(daily_total, ...)` was what prevented it. That
is FALSE. Caught by a mutation count BELOW prediction: deleting the cap redded
ZERO tests, because the cap never binds. Measured across all three day lengths:

    day             absolute hours   max hours_elapsed   accrued at 23:59
    normal  08-10        24.0              23                  24
    long    11-01        25.0              23                  24
    short   03-08        23.0              23                  24

`hours_elapsed` is wall-clock (`local - local_midnight` by hour index), so it is
bounded by 23 on EVERY day and the extra/missing DST hour is absorbed. Every PT
calendar day therefore grants exactly the daily total, once. **The ceiling is
exact on all three day types** — a better property than the asymmetry the old
comment claimed, and it is the one now pinned.

The consequence that IS real: accrual runs slightly slower in real time on the
25-hour day (24 builds over 25h) and slightly faster on the 23-hour day. The
CEILING never moves, which is the property this design exists to protect.

The `min(daily_total, ...)` in `accrued()` is retained as defence-in-depth and
is documented at its site as currently-unreachable — per `detector-controls.md`,
a guard that cannot fire must not be described as the thing providing safety.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

try:  # py>=3.9
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - the fleet is 3.11+
    ZoneInfo = None  # type: ignore

QUOTA_TZ = "America/Los_Angeles"
HOURS_PER_DAY = 24


@dataclass(frozen=True)
class CountDecision:
    """The full verdict for ONE build. Every field on every row.

    `would_refuse` is the quota's opinion; `enforcing` is the operator's. Keeping
    them separate is what lets the same row shape describe an enforcing repo and
    a shadowed one — inherited deliberately from `bucket.Decision`, so a consumer
    can read both eras of row without branching.
    """

    repo: str
    day: str
    used_before: int
    used_after: int
    accrued: int
    daily_total: int
    would_refuse: bool
    enforcing: bool
    refused: bool
    # 🔴 NOT optional on a refusal. An agent told only "no" retry-loops and costs
    # more than the build it was denied (constraint 2, carried over from
    # bucket.py). Under a daily counter this is the next HOUR boundary, not a
    # computed affordable_at — the arithmetic got simpler, the contract did not.
    refills_at_ts: Optional[float]
    break_glass: bool = False
    degraded: bool = False
    degraded_reason: Optional[str] = None
    notes: list = field(default_factory=list)

    @property
    def remaining(self) -> int:
        return max(0, self.accrued - self.used_after)


def _tz():
    if ZoneInfo is None:  # pragma: no cover
        raise RuntimeError("zoneinfo unavailable; refusing to guess the TZ")
    return ZoneInfo(QUOTA_TZ)


def day_key(now_ts: float) -> str:
    """The PT calendar day. This string IS the reset boundary."""
    return datetime.fromtimestamp(now_ts, _tz()).strftime("%Y-%m-%d")


def _local_midnight(now_ts: float) -> datetime:
    local = datetime.fromtimestamp(now_ts, _tz())
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def hours_elapsed(now_ts: float) -> int:
    """Whole hours since local midnight — 0 during the first hour."""
    local = datetime.fromtimestamp(now_ts, _tz())
    delta = local - _local_midnight(now_ts)
    return max(0, int(delta.total_seconds() // 3600))


def accrued(daily_total: int, now_ts: float) -> int:
    """Builds granted so far today. Banking is implicit: this is CUMULATIVE.

    The first hour grants its share immediately (`h+1`) rather than after an
    hour has passed — otherwise every repo is refused between midnight and 01:00
    every single day, which reads as an outage and would make the skip-var the
    habit within a week.
    """
    if daily_total <= 0:
        return 0
    h = hours_elapsed(now_ts) + 1
    # 🔴 max(1, ...) — hcl@ on #8201. floor(daily*1/24) is 0 for ANY repo under
    # 24/day, so familylore (17) and lexitrail (16) were refused for the whole
    # first hour of EVERY day. That is the exact daily-outage the `h+1` above
    # exists to prevent; it just only prevented it for repos at or above 24.
    # A positive allowance must always afford its first build at the reset.
    # ⚠️ The min() is DEFENCE-IN-DEPTH and is currently UNREACHABLE: hours_elapsed
    # is bounded by 23 on every day (incl. the 25-hour one), so h <= 24 and the
    # floor() can never exceed daily_total. Retained because a future change to
    # hours_elapsed — e.g. switching to absolute elapsed time — would make it
    # load-bearing immediately. Per detector-controls.md it is labelled rather
    # than claimed as the protection: deleting it reds no test, which is exactly
    # how the false DST claim in this module's docstring was found.
    return min(daily_total, max(1, int(math.floor(daily_total * h / HOURS_PER_DAY))))


def next_refill_ts(now_ts: float) -> float:
    """Top of the next local hour — what a refusal message must say."""
    local = datetime.fromtimestamp(now_ts, _tz())
    nxt = (local.replace(minute=0, second=0, microsecond=0)
           + timedelta(hours=1))
    return nxt.timestamp()


# A day plus a margin. A pool cannot go longer than 24h without an increase, so
# failing to find one inside this bound means the inputs are wrong, and saying so
# beats returning a confident timestamp.
_MAX_INCREASE_LOOKAHEAD_HOURS = 26


def next_increase_ts(daily_total: int, now_ts: float) -> Optional[float]:
    """The next hour boundary at which `accrued` ACTUALLY GOES UP. None if none found.

    🔴 NOT `next_refill_ts`, whose docstring above claims to be "what a refusal message
    must say" and is wrong for any pool with `daily_build_count < 24`. Those pools have
    `24 - daily` boundaries that grant NOTHING. lexitrail runs at 5/day — accrual moments
    are 00:00 / 09:00 / 14:00 / 19:00 / 23:00 local — so **19 of every 24 hours grant
    nothing** and the refusal names one of them 19/24 of the time. Measured live: build
    62fa85aa was refused at 20:25 PDT and told to come back at **21:00**, when the true
    next increase was **23:00** (2026-08-29).

    ⚠️ 19, not 20: the PT 23:30 hour looks dead to a naive `accrued(next) <= accrued(now)`
    because `accrued` DROPS across the roll (5 -> 1), but the roll is the largest increase
    of the day — `roll_day` zeroes `used`. I published 20 here and sbl@ caught it while
    re-deriving for stopbystop. Same artifact inflates daily=8 (16, not 17) and daily=22
    (2, not 3). That fails in the REASSURING
    direction, which is the one that gets acted on: the agent returns, merges, is refused
    again, and leaves a second red required check carrying no information (lexitrail#245).

    ⚠️ THE DAY ROLL COUNTS AS AN INCREASE EVEN THOUGH `accrued` DROPS ACROSS IT. At
    PT23 on a `daily >= 24` pool every remaining boundary is capped, so an
    accrued-only search finds nothing and would answer "never" on the eve of a full
    reset — `roll_day` zeroes `used` at local midnight, which is the largest increase
    of the day.

    Ported verbatim from ensemble's copy (ensemble#8819), which is verified: a full-day
    sweep finds it wrong 0/24 hours at each of daily in {5, 8, 24}, and it coincides with
    `next_refill_ts` 24/24 at daily=24. `counter.py` is vendored per-repo with no sync;
    lexitrail, market-mind and stopbystop all carried blob 0f16a2b6 without this.
    """
    if daily_total <= 0:
        return None
    here = accrued(daily_total, now_ts)
    today = day_key(now_ts)
    ts = now_ts
    for _ in range(_MAX_INCREASE_LOOKAHEAD_HOURS):
        ts = next_refill_ts(ts)
        if day_key(ts) != today:
            return ts
        if accrued(daily_total, ts) > here:
            return ts
    return None



def hourly_rate(daily_total: int) -> float:
    """DERIVED, never typed. A second hardcoded number is #7970 all over again."""
    return daily_total / HOURS_PER_DAY


def new_state(now_ts: float) -> dict:
    return {"day": day_key(now_ts), "used": 0, "lifetime_builds": 0,
            "lifetime_would_refuse": 0, "lifetime_break_glass": 0,
            "lifetime_degraded": 0}


def roll_day(state: dict, now_ts: float) -> dict:
    """HARD reset at the PT day boundary. Lifetime counters deliberately survive.

    Resetting `used` is what makes the daily ceiling real; resetting the lifetime
    counters too would erase the only evidence that the quota ever refused
    anything, which is the record #7914's over-fire rate is computed from.
    """
    today = day_key(now_ts)
    if state.get("day") == today:
        return dict(state)
    st = dict(state)
    st["day"] = today
    st["used"] = 0
    return st


def decide(state: dict, *, repo: str, now_ts: float, daily_total: int,
           enforcing: bool = False, break_glass: bool = False,
           degraded: bool = False,
           degraded_reason: Optional[str] = None) -> tuple[dict, CountDecision]:
    """Charge ONE build against the day's count. Returns (new_state, decision).

    Debits when the build PROCEEDS — allowed, shadow and break-glass alike. A
    build that ran consumed a slot whether or not we approved of it, so a counter
    that only debits its allows drifts permanently optimistic.

    🔴 A REFUSED BUILD DOES NOT DEBIT, and the earlier rule that it should was
    an assumption inherited from the wrong caller (mpl@, 2026-08-10).

    `bucket.decide` debits on every path *correctly*, because it is a RECONCILER:
    it re-reads builds that already ran, so everything it sees genuinely consumed
    money. `inbuild` is a GATE. A refused build stops at step 0 — a container
    pull and a few seconds — and never reaches the work the quota exists to
    ration. Charging it a full slot is not conservative, it is self-compounding:

        refusal charges a slot -> `used` climbs while nothing runs
        a retry charges again  -> recovery moves an hour further out per attempt
        at 1/hour accrual, a handful of retries spends the whole day on
        builds that never happened

    Observed live within an hour of enforcement going on: `used: 3` against
    `accrued: 1`, of which 2 were refusals. The quota was consuming itself.

    The refusal is still RECORDED — `lifetime_would_refuse` and `lifetime_builds`
    both count it — so nothing is hidden; it simply does not spend capacity that
    no build used. As mpl@ put it, "do not retry" is then arithmetic rather than
    etiquette, and this makes the arithmetic stop punishing the retry.
    """
    notes: list = []

    if degraded:
        # Constraint 1: fail OPEN, but LOUD and COUNTED. Blocking every build on
        # an instrument glitch is worse than a day of overspend — but an
        # override nobody counts becomes the habit, so it increments.
        st = dict(state)
        st["lifetime_degraded"] = int(st.get("lifetime_degraded", 0)) + 1
        return st, CountDecision(
            repo=repo, day=state.get("day", ""), used_before=-1, used_after=-1,
            accrued=-1, daily_total=daily_total, would_refuse=False,
            enforcing=enforcing, refused=False, refills_at_ts=None,
            break_glass=break_glass, degraded=True,
            degraded_reason=degraded_reason or "counter unreadable",
            notes=["fail-open: allowed without a count check"],
        )

    st = roll_day(state, now_ts)
    before = int(st.get("used", 0))
    granted = accrued(daily_total, now_ts)

    would_refuse = before >= granted
    if would_refuse and granted >= daily_total:
        notes.append(
            "the day's entire allowance is spent — refills at midnight PT, "
            "not at the next hour")

    refused = bool(would_refuse and enforcing and not break_glass)

    # Only a build that PROCEEDS spends a slot. See the docstring: charging a
    # refusal makes refusals self-compounding, which is the opposite of what a
    # ration is for.
    if not refused:
        st["used"] = before + 1
    st["lifetime_builds"] = int(st.get("lifetime_builds", 0)) + 1
    if would_refuse:
        st["lifetime_would_refuse"] = int(st.get("lifetime_would_refuse", 0)) + 1
    if break_glass:
        st["lifetime_break_glass"] = int(st.get("lifetime_break_glass", 0)) + 1
        notes.append("break-glass: refusal overridden, build still counted")

    return st, CountDecision(
        repo=repo, day=st["day"], used_before=before,
        used_after=int(st["used"]),
        accrued=granted, daily_total=daily_total, would_refuse=would_refuse,
        enforcing=enforcing, refused=refused,
        # `next_increase_ts` can return None only when the inputs are wrong — and a
        # slightly-early time still beats no time at all, because an agent told only
        # "no" retry-loops. Same fallback as ensemble's copy.
        refills_at_ts=((next_increase_ts(daily_total, now_ts) or next_refill_ts(now_ts))
                       if would_refuse else None),
        break_glass=break_glass, notes=notes,
    )


def refusal_message(d: CountDecision) -> str:
    """The message the in-build step prints before exiting NON-ZERO.

    Exit 0 on a refusal is a correctness bug, not a softer option: a green check
    on a build that never ran is a false pass, and it is worse than the overspend
    it was trying to avoid (Alex + zz1 both, 2026-08-09).
    """
    when = datetime.fromtimestamp(d.refills_at_ts, _tz()).strftime("%H:%M %Z") \
        if d.refills_at_ts else "midnight PT"
    return (
        f"BUILD QUOTA: {d.repo} has used {d.used_before} of {d.accrued} builds "
        f"accrued so far today ({d.daily_total}/day, "
        f"~{hourly_rate(d.daily_total):.1f}/hour). More quota at {when}."
    )
