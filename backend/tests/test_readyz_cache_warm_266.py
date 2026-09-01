"""issue-266: readiness must mean "can serve WELL", not merely "can serve".

Measured on a live pod: Flask serves from t+0 (the warm is a background daemon
thread), readiness marks Ready at ~t+30s, warm completes at ~t+55s -> ~25s per
pod start where the replica is in the Service and every request takes the
expensive cache-MISS path. Both replicas hit it during a rollout.

🔴 The tests that matter most here are the ones asserting the pod IS ready in a
bad state. A naive `if not complete: 503` wedges every replica NotReady forever
on a hung warm -- turning a partial degradation into a total outage. The
deadline and failed-warm arms are the escape hatch, and they are pinned in the
direction where "tightening" the check breaks production.

⚠️ CORRECTION (hc2, #309 review): an earlier version of this note said
"lexitrail's cloudbuild.yaml has no pytest step, so nothing runs this in CI."
The first half is true and the CONCLUSION IS FALSE -- .github/workflows/
backend-tests.yml runs pytest on every PR touching backend paths (#269). I
checked Cloud Build, found nothing, and generalised to "no CI" -- enumerating
one CI surface and concluding about all of them. These tests DO gate merges.
"""
import importlib.util
import pathlib

import pytest

# Load the policy module BY PATH -- a plain `from app.cache_warm_policy import`
# executes `app/__init__.py`, which imports Flask, so it would fail in any
# environment without the backend deps. That is the very situation the module
# was split out to survive, and the convention test_cache_warm_97.py follows.
_spec = importlib.util.spec_from_file_location(
    "cache_warm_policy",
    pathlib.Path(__file__).resolve().parents[1] / "app" / "cache_warm_policy.py")
_policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_policy)

CACHE_WARM_DEADLINE_S = _policy.CACHE_WARM_DEADLINE_S
WARM_FAILED = _policy.WARM_FAILED
WARM_READY = _policy.WARM_READY
WARM_NOT_READY = _policy.WARM_NOT_READY


def _status(**kw):
    """A cache_status-shaped dict. Defaults are the COLD, just-started state."""
    base = {"complete": False, "state": "cold", "progress": 0, "total": 9,
            "started_at": None}
    base.update(kw)
    return base


def cache_warm_readiness(status, now):
    return _policy.cache_warm_readiness(status, now)


# --- hold traffic while genuinely warming ------------------------------------

def test_not_ready_while_warming_within_the_deadline():
    verdict, reason = cache_warm_readiness(_status(complete=False, state="cold", started_at=1000.0, progress=3, total=9), 1000.0 + 20)
    assert verdict == WARM_NOT_READY, reason
    assert "3/9" in reason


def test_not_ready_before_the_warm_thread_has_stamped_a_start():
    """First instants of process life -- a hold, not a hang."""
    verdict, _ = cache_warm_readiness(_status(complete=False, state="cold", started_at=None), 1000.0)
    assert verdict == WARM_NOT_READY


# --- the escape hatches: READY in a bad state, on purpose --------------------

def test_ready_once_the_deadline_passes_even_though_still_warming():
    """🔴 The line between a slow warm and a fleet-wide outage.

    If this ever returns not-ready, a warm that hangs holds EVERY replica out
    of the Service and nothing serves at all.
    """
    verdict, reason = cache_warm_readiness(_status(complete=False, state="cold", started_at=1000.0, progress=1, total=9), 1000.0 + CACHE_WARM_DEADLINE_S + 1)
    assert verdict == WARM_READY, (
        "issue-266: past the deadline the pod must serve DEGRADED rather than "
        "stay NotReady. A hung warm would otherwise wedge every replica."
    )
    assert "deadline" in reason


def test_ready_when_the_warm_outright_FAILED():
    """A failed warm is not going to finish; serving slowly beats not serving."""
    verdict, reason = cache_warm_readiness(_status(complete=False, state=WARM_FAILED, started_at=1000.0), 1000.0 + 5)
    assert verdict == WARM_READY, reason


def test_boundary_exactly_at_the_deadline_is_ready():
    """Pinned because `>` vs `>=` here decides an outage, and both look fine."""
    verdict, _ = cache_warm_readiness(_status(complete=False, state="cold", started_at=1000.0), 1000.0 + CACHE_WARM_DEADLINE_S)
    assert verdict == WARM_READY


# --- the normal case ---------------------------------------------------------

def test_ready_once_warm_is_complete():
    verdict, reason = cache_warm_readiness(_status(complete=True, state="ok", started_at=1000.0), 1000.0 + 60)
    assert verdict == WARM_READY and reason == "warm"


def test_complete_wins_even_if_started_at_is_missing():
    """Order matters: a complete warm must not depend on the timestamp."""
    assert cache_warm_readiness(_status(complete=True, state="ok", started_at=None), 1.0)[0] == WARM_READY
