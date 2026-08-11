"""Pure policy for the startup cache warm (#97).

Separate from `routes/wordsets.py` for one reason: that module imports Flask and
the app package, so a test of this policy could not run without a full backend
environment. The backend suite currently cannot collect at all outside a
provisioned venv (pre-existing — `tests/test_wordsets.py` fails the same way,
and lexitrail has no CI triggers, #77), so a policy left in there would ship
with no executable test of any kind.

Keeping the decision pure is also this codebase's existing convention for
exactly this kind of rule — see `tools/cd/poll_deploy.py`'s `needs_deploy`,
`classify_served` and `should_retry_served`.
"""
from __future__ import annotations

#: Overall budget for the whole warm, NOT per wordset. The bug this replaces
#: gave each future 60s counted from the moment the ordered loop REACHED it --
#: but with 2 workers and 9 wordsets most futures are still queued at that
#: point, so a future could exhaust its timeout having never run. Four such
#: timeouts fired exactly 60s apart on every backend start, stretching the warm
#: to ~5 minutes. A deadline over the whole warm charges nothing for queue time.
CACHE_WARM_DEADLINE_S = 300

#: Warm outcomes. `degraded` exists so a partial warm cannot report as a clean
#: one (AC3): the old code set `initialized = True` at the end of the function
#: regardless of how many wordsets warmed, and kept only the LAST error string,
#: so four timed-out wordsets and a perfect warm produced the same externally
#: visible status -- a failure rendering as the success state.
WARM_OK = "ok"
WARM_DEGRADED = "degraded"
WARM_FAILED = "failed"


#: Per-wordset warm outcomes (#106). Three, because the two failure kinds have
#: different causes and want different log lines: an `error_response` tuple is a
#: query/DB failure that `get_words_by_wordset` converted, while a bare `None`
#: is a wordset whose warm did not report anything at all.
WARM_RESULT_OK = "ok"
WARM_RESULT_ERROR_RESPONSE = "error_response"
WARM_RESULT_NONE = "none"


def classify_warm_result(result) -> str:
    """Outcome for ONE wordset's warm, from what its future returned (#106).

    The bug this replaces: the caller counted successes with

        if isinstance(result, tuple):  ...   # error_response -> not counted
        else:                succeeded += 1  # EVERYTHING else -> counted

    which is an `else` adopting every value that is not a tuple — including
    `None`, which is exactly what `init_wordset_cache`'s own `except` returned
    when the warm raised. `isinstance(None, tuple)` is False, so a wordset that
    RAISED was counted as warmed, `warm_verdict` returned `ok`, and
    `/wordsets/cache-status` reported a clean warm over a cache missing entries
    — the failure-renders-as-success shape #97 exists to remove, reappearing on
    the one path that does not signal its own failure.

    So `ok` is now a POSITIVE test rather than the fallthrough. Any future value
    that is neither a recognised success nor a recognised failure lands on a
    failure, not on `ok`: the safe direction for a status field whose whole job
    is to not overstate.

    `None` specifically is treated as a failure rather than mapped onto
    `error_response`. Collapsing them would make the sentinel carry two
    meanings and leave the next reader unable to tell which failure they are
    looking at (#106 AC4) — the same reason the deadline message says in words
    that it is not a per-wordset failure.

    NOTE the deliberate non-guard: an empty list is `ok`. A wordset with no
    words warmed correctly and has nothing to show for it; requiring
    truthiness here would report an empty wordset as a failed warm.
    """
    if isinstance(result, tuple):
        return WARM_RESULT_ERROR_RESPONSE
    if result is None:
        return WARM_RESULT_NONE
    return WARM_RESULT_OK


def warm_verdict(total: int, succeeded: int) -> str:
    """`ok` | `degraded` | `failed` for a completed warm pass.

    A zero-wordset warm is `ok`, not `failed`: nothing was asked of it and
    nothing went wrong. Collapsing that into `failed` would make an empty
    database look like an outage.
    """
    if total <= 0:
        return WARM_OK
    if succeeded >= total:
        return WARM_OK
    if succeeded <= 0:
        return WARM_FAILED
    return WARM_DEGRADED
