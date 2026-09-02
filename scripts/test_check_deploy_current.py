"""Pins the THREE-state contract of the deploy-currency check (lexitrail#273).

The instrument was run against the live site before this file existed and
returned the state the world was in: both surfaces 404 on /version, because
nothing carrying the sha has deployed yet.

    exit 3   CANNOT-TELL, "the running artifact predates issue-273"

🔴 That is the assertion this whole file exists to protect. The pre-deploy state
returning CANNOT-TELL rather than PASS is the difference between a detector and a
decoration: a check that reports "current" when it cannot read a sha is blind for
exactly as long as an old image keeps running, which is the failure #273 is about.

The other load-bearing arm is `known: false` -- a hand-built image with no
--build-arg. It is neither a pass nor drift, and both collapses are silent in
opposite directions (into PASS: blind; into FAIL: alarms through every rollout of
a pre-#273 image, gets muted, absent when it matters).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "check_deploy_current", Path(__file__).with_name("check_deploy_current.py"),
)
mod = importlib.util.module_from_spec(_SPEC)
sys.modules["check_deploy_current"] = mod
_SPEC.loader.exec_module(mod)

PASS, FAIL, CANNOT_TELL = mod.PASS, mod.FAIL, mod.CANNOT_TELL
V = mod.verdict_for


def test_matching_sha_passes():
    code, msg = V("ui", "e0986fc", "e0986fc", True, "")
    assert code == PASS, msg


def test_differing_sha_is_the_drift_fail():
    code, msg = V("ui", "e0986fc", "fa8ffbc", True, "")
    assert code == FAIL, msg
    assert "AHEAD of production" in msg, msg


def test_the_fail_names_the_refused_vs_failed_discriminator():
    """The alarm is useless if the reader diagnoses it as a broken build --
    that misreading is the whole reason #273 cost 75 minutes."""
    _, msg = V("ui", "e0986fc", "fa8ffbc", True, "")
    assert "used_before == used_after" in msg, msg


def test_known_false_is_cannot_tell_not_pass():
    """🔴 A hand-built image has no opinion. Not evidence that it is current."""
    code, msg = V("backend", "e0986fc", None, False, "")
    assert code == CANNOT_TELL, msg
    assert "Not a pass" in msg, msg


def test_no_answer_is_cannot_tell_and_carries_the_reason():
    code, msg = V("ui", "e0986fc", None, None, "https://x/version.json is 404")
    assert code == CANNOT_TELL, msg
    assert "404" in msg, msg


def test_unresolvable_path_is_cannot_tell_not_pass():
    code, msg = V("ui", None, "e0986fc", True, "")
    assert code == CANNOT_TELL, msg
    assert "not a pass" in msg, msg


def test_known_true_with_no_sha_is_cannot_tell():
    """A self-contradicting endpoint must not be read as either verdict."""
    for empty in (None, "", "   ", 7):
        code, _ = V("ui", "e0986fc", empty, True, "")
        assert code == CANNOT_TELL, empty


def test_a_shared_prefix_is_NOT_a_match():
    """🔴 The comparison is exact, on full shas resolved by resolve_full().

    hc2 asked on #314 whether the old min-length prefix compare was defensive
    only. It was -- and the defense was the bug: `git log --abbrev=7` is a
    MINIMUM, git extends it when 7 characters are ambiguous, so the two sides
    differ in length exactly when two commits share a 7-char prefix. That is
    precisely when a prefix compare reports a match between different commits.
    Same trigger for the tolerance and for the hazard."""
    a = "e0986fc" + "a" * 33
    b = "e0986fc" + "b" * 33
    assert V("ui", a, b, True, "")[0] == FAIL
    assert V("ui", a, a, True, "")[0] == PASS


def test_resolve_full_rejects_a_sha_it_cannot_resolve_uniquely():
    """Ambiguous or not-fetched must be CANNOT-TELL input, never a comparison."""
    full, why = mod.resolve_full("zzzzzzz")
    assert full is None
    assert "does not resolve" in why, why


def test_a_cannot_tell_surface_is_not_rescued_by_a_passing_sibling():
    """The aggregate must not let one readable surface vouch for an unreadable
    one -- that is how a half-blind check reports all-clear."""
    codes = [PASS, CANNOT_TELL]
    assert (FAIL in codes) is False
    assert CANNOT_TELL in codes  # main() returns CANNOT_TELL for this mix


def test_fail_outranks_cannot_tell_in_the_aggregate():
    codes = [CANNOT_TELL, FAIL]
    assert FAIL in codes


def test_the_three_exit_codes_are_distinct():
    assert (PASS, FAIL, CANNOT_TELL) == (0, 1, 3)


def test_surfaces_compare_against_their_own_path_not_main_head():
    """🔴 Comparing to main's HEAD would report drift forever: most commits here
    touch neither ui/ nor backend/ and trigger no build."""
    assert mod.SURFACES["ui"][1] == "ui/"
    assert mod.SURFACES["backend"][1] == "backend/"


# --- the FAIL message has TWO directions (found by running AC4's control) ----
# The first version said "main is AHEAD of production" unconditionally. AC4 asks
# for a control against a deliberately stale ref, which produces the OTHER
# direction — production newer than the ref — and the message sent the reader
# after a refused deploy that never happened. Both are FAIL; only the cause and
# the remedy differ.

def test_main_ahead_names_the_refusal_check(monkeypatch):
    """The common case: a merge landed, the deploy was refused, main is ahead."""
    monkeypatch.setattr(mod, "_is_ancestor", lambda older, newer: True)
    _, msg = V("ui", "b" * 40, "a" * 40, True, "")
    assert "main is AHEAD of production" in msg, msg
    assert "used_before == used_after" in msg, msg


def test_production_ahead_does_NOT_name_the_refusal_check(monkeypatch):
    """🔴 The direction AC4's control produces. Naming the refusal check here
    sends the reader after a deploy that was never attempted."""
    monkeypatch.setattr(mod, "_is_ancestor", lambda older, newer: False)
    _, msg = V("ui", "a" * 40, "b" * 40, True, "")
    assert "production is running something this ref does not know about" in msg, msg
    assert "NOT the refused-deploy case" in msg, msg
    assert "used_before == used_after" not in msg, (
        "the refusal discriminator is the WRONG advice in this direction"
    )


def test_both_directions_are_still_FAIL():
    """The wording differs; the verdict must not. A mis-detected direction is a
    reader sent the wrong way, never a drift that goes unreported."""
    for anc in (True, False):
        import unittest.mock as _m
        with _m.patch.object(mod, "_is_ancestor", lambda o, n: anc):
            code, _ = V("ui", "a" * 40, "b" * 40, True, "")
            assert code == FAIL, anc


def test_is_ancestor_fails_toward_the_common_wording():
    """A git failure must not produce a third, silent shape."""
    assert mod._is_ancestor("not-a-sha", "also-not-a-sha") in (True, False)
