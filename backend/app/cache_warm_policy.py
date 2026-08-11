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
