"""#97 — the startup cache-warm must not charge a future for queue time.

Two layers, because the ACs make two different kinds of claim:

* `warm_verdict` is pure, so the status policy (AC3) is tested directly — no
  database, no thread pool, no five-minute wait. Same convention as
  `tools/cd/poll_deploy.py`'s `needs_deploy` / `classify_served`.
* AC1 is a claim about a *timeout that must not happen*, which no pure function
  can demonstrate. That one is pinned with a real `ThreadPoolExecutor` running
  the OLD pattern beside the NEW one, so the test fails if the new pattern ever
  regresses to per-future-from-loop-arrival.
"""
from __future__ import annotations

import pathlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError

import pytest

# Load the policy module BY PATH. A plain `from app.cache_warm_policy import ...`
# executes `app/__init__.py`, which imports Flask -- so the import would fail in
# any environment without the backend deps, which is the very situation the
# module was split out to survive.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "cache_warm_policy",
    pathlib.Path(__file__).resolve().parents[1] / "app" / "cache_warm_policy.py")
_policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_policy)

CACHE_WARM_DEADLINE_S = _policy.CACHE_WARM_DEADLINE_S
WARM_OK, WARM_DEGRADED, WARM_FAILED = _policy.WARM_OK, _policy.WARM_DEGRADED, _policy.WARM_FAILED
warm_verdict = _policy.warm_verdict


# ---------------------------------------------------------------------------
# AC3 — a partial warm must not read as a clean one
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("total,succeeded,expected", [
    (9, 9, WARM_OK),        # everything warmed
    (9, 5, WARM_DEGRADED),  # the shape this issue is about
    (9, 0, WARM_FAILED),    # nothing warmed
    (1, 1, WARM_OK),
    (1, 0, WARM_FAILED),
    (0, 0, WARM_OK),        # empty DB is not an outage
])
def test_warm_verdict_table(total, succeeded, expected):
    assert warm_verdict(total, succeeded) == expected


def test_degraded_is_distinct_from_both_neighbours():
    """The load-bearing distinction (AC3).

    The old code set `initialized = True` at the end of the function regardless
    of how many wordsets had actually warmed, and kept only the LAST error
    string. Four timed-out wordsets and a perfect warm produced the same
    externally visible status — a failure rendering as the success state.

    So `degraded` must be its own value, not folded into either neighbour.
    """
    assert warm_verdict(9, 5) not in (WARM_OK, WARM_FAILED)
    assert WARM_OK != WARM_DEGRADED != WARM_FAILED


def test_a_single_missing_wordset_is_already_degraded():
    # Not "mostly fine". 8 of 9 means a user asking for the 9th waits on a cold
    # query, which is the symptom #52 item 6 describes.
    assert warm_verdict(9, 8) == WARM_DEGRADED


def test_deadline_is_an_overall_budget_not_a_per_wordset_one():
    # 9 wordsets that each legitimately take ~30s exceed any per-wordset 60s
    # reading of this number; it has to be big enough to be a whole-warm budget.
    assert CACHE_WARM_DEADLINE_S >= 120


# ---------------------------------------------------------------------------
# AC1 — the bug shape, reproduced with a real pool
# ---------------------------------------------------------------------------

WORKERS = 2
TASKS = 9
#: A task SLOWER than the per-future timeout. That relationship is the actual
#: precondition for the bug, and it is worth stating because my first harness
#: got it wrong and this test is what caught it:
#:
#: With uniform tasks, queueing ALONE never trips `result(timeout=T)`. Future k
#: completes at ~((k//2)+1)*TASK, and the loop only reaches it after future k-1
#: completed -- so the remaining wait is under one TASK every time, and a T
#: larger than TASK never fires. My first attempt used TASK=0.05 / T=0.15 and
#: measured ZERO timeouts.
#:
#: The bug needs the future to be unfinished T after the loop ARRIVES, i.e.
#: TASK > T. Production matches: the four errors were exactly 60s apart, which
#: is the loop waiting out its full timeout on wordsets that each take longer
#: than 60s -- queueing then compounds it for the ones behind them.
#:
#: So #97's body ("most futures are still queued when the loop reaches them")
#: named a contributing factor as if it were the cause. Corrected on the issue.
TASK_S = 0.3
PER_FUTURE_TIMEOUT_S = 0.1


def _slow():
    time.sleep(TASK_S)
    return "warmed"


def test_the_old_pattern_times_out_on_futures_that_never_ran():
    """The bug shape itself. If this ever stops failing, the harness is wrong.

    Iterating in SUBMISSION order and calling `future.result(timeout=...)`
    starts the clock when the LOOP REACHES the future — not when the task
    starts. With fewer workers than tasks, later futures are still queued at
    that moment and are charged for waiting.
    """
    timeouts = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(_slow) for _ in range(TASKS)]
        for f in futures:
            try:
                f.result(timeout=PER_FUTURE_TIMEOUT_S)
            except FuturesTimeoutError:
                timeouts += 1

    assert timeouts > 0, (
        "the old pattern did not reproduce its own bug — the harness no longer "
        "demonstrates anything, so the passing test below proves nothing")


def test_the_new_pattern_completes_the_same_work_without_timing_out():
    """AC1 — the fix, against the identical workload.

    `as_completed` consumes in COMPLETION order against ONE deadline for the
    whole warm, so nothing is charged for queue time.
    """
    overall = TASK_S * TASKS  # generous vs ~TASK_S*TASKS/WORKERS actual; still bounded
    warmed = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(_slow) for _ in range(TASKS)]
        for f in as_completed(futures, timeout=overall):
            assert f.result() == "warmed"
            warmed += 1

    assert warmed == TASKS, "every task must be accounted for, none abandoned"


def test_the_new_pattern_still_has_a_bound():
    """The negative control.

    A fix that simply waited forever would pass the test above while removing
    the protection the timeout existed to provide. A deadline shorter than the
    work must still raise — the guard has to be able to fire.
    """
    with pytest.raises(FuturesTimeoutError):
        with ThreadPoolExecutor(max_workers=1) as ex:
            futures = [ex.submit(_slow) for _ in range(TASKS)]
            for f in as_completed(futures, timeout=TASK_S / 2):
                f.result()


# ---------------------------------------------------------------------------
# hc2 review of PR #103 — the deadline must bound the OBSERVABLE STATUS, not
# just the log line.
#
# `ThreadPoolExecutor.__exit__` calls `shutdown(wait=True)` unconditionally,
# including when an exception was caught and handled inside the block. So code
# placed after a `with` block does not run until every straggler finishes --
# the deadline would bound what we SAY and not what we DO.
# ---------------------------------------------------------------------------

SLOW_TASK_S = 1.0
TIGHT_DEADLINE_S = 0.3
SLOW_TASK_COUNT = 3   # 3 x 1.0s on ONE worker = a ~3s drain vs a 0.3s deadline:
                      # a 10x gap, which is all the demonstration needs. Kept small
                      # deliberately -- the first version used 5 x 2.0s and cost the
                      # suite 10 seconds to prove the same thing.


def _very_slow():
    time.sleep(SLOW_TASK_S)
    return "warmed"


def test_the_with_block_shape_defers_past_the_deadline():
    """The bug shape. If this stops failing, `with` became safe and the fix is moot.

    Asserts the DEFERRAL is real: with a `with` block, the first statement after
    it runs only after the full drain, not at the deadline.
    """
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as ex:
        futures = [ex.submit(_very_slow) for _ in range(SLOW_TASK_COUNT)]
        try:
            for f in as_completed(futures, timeout=TIGHT_DEADLINE_S):
                pass
        except FuturesTimeoutError:
            caught_at = time.monotonic() - t0
    after_block_at = time.monotonic() - t0

    assert caught_at < TIGHT_DEADLINE_S * 2, "the deadline itself should fire on schedule"
    assert after_block_at > SLOW_TASK_S, (
        "the `with` shape no longer defers past the deadline -- if that is true, "
        "re-evaluate whether the explicit-shutdown fix is still needed")


def test_explicit_shutdown_releases_at_the_deadline():
    """The fix: status-setting code runs AT the deadline, not after the drain."""
    t0 = time.monotonic()
    ex = ThreadPoolExecutor(max_workers=1)
    futures = [ex.submit(_very_slow) for _ in range(SLOW_TASK_COUNT)]
    status_set_at = None
    try:
        for f in as_completed(futures, timeout=TIGHT_DEADLINE_S):
            pass
    except FuturesTimeoutError:
        ex.shutdown(wait=False, cancel_futures=True)
        status_set_at = time.monotonic() - t0

    assert status_set_at is not None
    assert status_set_at < TIGHT_DEADLINE_S * 2, (
        f"status became visible at {status_set_at:.2f}s -- the deadline must bound "
        "the OBSERVABLE STATUS, not only the log line (hc2, PR #103)")


# ---------------------------------------------------------------------------
# #106 — a wordset whose warm RAISED must not count as warmed
#
# THE BUG SHAPE. `init_wordset_cache` used to swallow every exception and
# `return None`; the consumer counted successes with `if isinstance(result,
# tuple): ... else: succeeded += 1`, and `isinstance(None, tuple)` is False.
# So a wordset that raised landed in the `else` and was counted as warmed —
# `warm_verdict` then returned `ok` over a cache missing entries, which is the
# failure-renders-as-success shape #97 exists to remove, on the one path that
# does not signal its own failure.
# ---------------------------------------------------------------------------

classify_warm_result = _policy.classify_warm_result
WARM_RESULT_OK = _policy.WARM_RESULT_OK
WARM_RESULT_ERROR_RESPONSE = _policy.WARM_RESULT_ERROR_RESPONSE
WARM_RESULT_NONE = _policy.WARM_RESULT_NONE


def test_none_is_not_counted_as_a_successful_warm():
    """THE regression. `None` is what the swallowed exception returned."""
    assert classify_warm_result(None) != WARM_RESULT_OK
    assert classify_warm_result(None) == WARM_RESULT_NONE


def test_none_is_distinguishable_from_an_error_response():
    """AC2/AC4 — the two failure kinds must not collapse onto one sentinel.

    Merging them would leave a reader unable to tell a query failure from a
    warm that returned nothing, which is the same 'one value, two meanings'
    problem the deadline message is careful to avoid in words.
    """
    assert classify_warm_result(None) != classify_warm_result(("boom", 500))


def test_an_error_response_tuple_is_still_a_failure():
    """The path that already worked must keep working."""
    assert classify_warm_result(("error", 500)) == WARM_RESULT_ERROR_RESPONSE


@pytest.mark.parametrize("value", [
    [{"word_id": 1}],   # the ordinary success
    [],                 # DELIBERATE: an empty wordset warmed fine and has
                        # nothing to show. Requiring truthiness here would
                        # report it as a failed warm.
    {"words": []},
    "ok",
    0,                  # falsy but not None — still a positive result
])
def test_positive_results_are_ok_including_falsy_ones(value):
    assert classify_warm_result(value) == WARM_RESULT_OK


def test_ok_is_a_positive_test_not_the_fallthrough():
    """The `else` that adopted everything is why this bug existed.

    Any value that is neither a recognised success nor a recognised failure
    must land on a FAILURE, never on `ok` — the safe direction for a status
    field whose job is to not overstate. Asserting the classifier's own shape
    would just restate the implementation, so this asserts the CONSEQUENCE:
    a warm of 1 wordset that returned None must not read as a clean warm.
    """
    outcome = classify_warm_result(None)
    succeeded = 1 if outcome == WARM_RESULT_OK else 0
    assert warm_verdict(1, succeeded) == WARM_FAILED, (
        "a wordset that returned nothing rendered as a clean warm")
