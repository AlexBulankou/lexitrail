"""Tests for the Lexitrail CD poll (issue-77).

The two functions here decide (a) whether to deploy and (b) whether the deploy
actually reached users. Both have a failure direction that is quiet, so each is
pinned in BOTH directions rather than on the happy path alone.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poll_deploy import (  # noqa: E402
    EXPECTED_CONTENT_TYPE_PREFIX,
    classify_served,
    needs_deploy,
)


# ── needs_deploy ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("head, deployed, expected", [
    ("abc123", "abc123", False),   # up to date
    ("abc123", "def456", True),    # main moved
    ("abc123", None,     True),    # unknown deployed sha -> deploy, don't assume current
    (None,     "abc123", False),   # unknown HEAD -> the QUERY failed; never deploy blind
    (None,     None,     False),
])
def test_needs_deploy(head, deployed, expected):
    assert needs_deploy(head, deployed) is expected


def test_unknown_deployed_sha_deploys_but_unknown_head_does_not():
    """The two unknowns are NOT symmetric, and collapsing them is the bug.

    An unknown *deployed* sha means "I don't know what is running" -> deploy.
    An unknown *HEAD* means the query failed -> deploying would target nothing.
    """
    assert needs_deploy("abc", None) is True
    assert needs_deploy(None, "abc") is False


# ── classify_served ──────────────────────────────────────────────────────

def test_the_63_shape_is_absent_not_ok():
    """THE case this exists for. The og asset returned HTTP 200 for the entire
    3 days it was missing, because the SPA catch-all served index.html. A
    status-only check calls this deployed."""
    assert classify_served(200, "text/html; charset=utf-8", 2853) == "absent"


def test_real_asset_is_ok():
    assert classify_served(200, "image/png", 202155) == "ok"


@pytest.mark.parametrize("status, ctype, size, expected", [
    (404, "text/html", 0,      "absent"),
    (500, "text/html", 0,      "indeterminate"),   # server error != known-absent
    (503, "", 0,               "indeterminate"),
    (200, "image/png", 12,     "indeterminate"),   # 200 image but implausibly small
    (200, "image/jpeg", 50000, "ok"),
])
def test_classify_served_table(status, ctype, size, expected):
    assert classify_served(status, ctype, size) == expected


def test_indeterminate_is_distinct_from_absent():
    """A checker that cannot conclude must not report the known-bad state, and
    vice versa -- they want different responses (investigate vs redeploy)."""
    assert classify_served(500, "text/html", 0) != classify_served(404, "text/html", 0)


def test_content_type_is_the_discriminator_not_status():
    """Same status, same plausible size; only content-type differs -- and that
    alone must flip the verdict."""
    ok = classify_served(200, "image/png", 202155)
    bad = classify_served(200, "text/html", 202155)
    assert ok == "ok" and bad == "absent"
    assert EXPECTED_CONTENT_TYPE_PREFIX == "image/"


# ── extract_source_sha (issue-77 / PR #78 review) ────────────────────────
#
# These exist because the original implementation used a `-o jsonpath=` expression
# with the SLASH escaped, when jsonpath's separator is the DOT. That returns EMPTY
# for an annotation that exists and is set correctly -- so the poll could never
# converge and would rebuild forever.
#
# It survived a live run because `deployed=None` was the EXPECTED output that night
# (the annotation genuinely did not exist yet) and is ALSO what the broken escaping
# produces once it does. The observation could not distinguish the two facts.
#
# The fixture below uses the REAL shape, read off the live deployment
# (`spec.template.metadata.annotations`, confirmed to carry
# `kubectl.kubernetes.io/restartedAt`) rather than an invented one.

from poll_deploy import (  # noqa: E402
    EXIT_FAILED,
    EXIT_INDETERMINATE,
    EXIT_OK,
    SOURCE_ANNOTATION,
    _verdict_exit,
    extract_source_sha,
)

_REAL_SHAPE = """{
  "spec": {"template": {"metadata": {"annotations": {
      "kubectl.kubernetes.io/restartedAt": "2026-07-22T19:58:42Z",
      "%s": "037eb048f3c9ca1d44f963a9ff954224b9c53393"
  }}}}
}""" % SOURCE_ANNOTATION


def test_extracts_the_sha_when_the_annotation_is_present():
    """THE regression. The jsonpath version returned '' here, which the caller mapped
    to None -- indistinguishable from a genuinely absent annotation."""
    assert extract_source_sha(_REAL_SHAPE) == "037eb048f3c9ca1d44f963a9ff954224b9c53393"


def test_absent_annotation_is_none_not_empty_string():
    payload = '{"spec":{"template":{"metadata":{"annotations":{"other/key":"x"}}}}}'
    assert extract_source_sha(payload) is None


@pytest.mark.parametrize("payload", [
    "", "not json", "null", "[]", "{}",
    '{"spec":{}}',
    '{"spec":{"template":{"metadata":{}}}}',
    '{"spec":{"template":{"metadata":{"annotations":null}}}}',
])
def test_malformed_payloads_are_none_never_raise(payload):
    """A parse failure must read as 'unknown' (-> deploy), never crash the poll."""
    assert extract_source_sha(payload) is None


def test_whitespace_only_value_is_none():
    payload = '{"spec":{"template":{"metadata":{"annotations":{"%s":"   "}}}}}' % SOURCE_ANNOTATION
    assert extract_source_sha(payload) is None


# ── _verdict_exit: all three states stay distinct ────────────────────────

def test_verdict_exit_keeps_three_states_distinct():
    """`absent` (redeploy) and `indeterminate` (investigate) want different
    responses, so they must not share a code -- the reason EXIT_INDETERMINATE
    exists at all."""
    assert _verdict_exit("ok") == EXIT_OK
    assert _verdict_exit("absent") == EXIT_FAILED
    assert _verdict_exit("indeterminate") == EXIT_INDETERMINATE
    assert len({_verdict_exit(v) for v in ("ok", "absent", "indeterminate")}) == 3


# ── build_succeeded: exit code alone must not green-light a deploy ────────

from poll_deploy import build_succeeded  # noqa: E402


@pytest.mark.parametrize("rc, out, expected", [
    (0, "Status: SUCCESS", True),
    (0, "... STATUS: SUCCESS ...", True),
    (0, "Status: FAILURE", False),   # THE case: exit 0 with a failed build
    (0, "", False),                  # no status text at all -> not a success
    (0, "TIMEOUT", False),
    (1, "Status: SUCCESS", False),   # succeeded then died in transport -> don't trust
    (1, "Status: FAILURE", False),
])
def test_build_succeeded_requires_both_halves(rc, out, expected):
    assert build_succeeded(rc, out) is expected


def test_exit_zero_with_failure_text_is_not_a_success():
    """A wrapper, a `| tee`, or a retry shim can hand back 0 while the build
    status says FAILURE. Requiring the word SUCCESS means the exit code alone
    cannot authorise a production patch -- the same 'status answered an adjacent
    question' shape as the served-asset 200."""
    assert build_succeeded(0, "Status: FAILURE") is False
    assert build_succeeded(0, "Status: SUCCESS") is True
