"""Tests for the Lexitrail CD poll (issue-77).

The two functions here decide (a) whether to deploy and (b) whether the deploy
actually reached users. Both have a failure direction that is quiet, so each is
pinned in BOTH directions rather than on the happy path alone.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poll_deploy import (  # noqa: E402
    EXPECTED_CONTENT_TYPE_PREFIX,
    EXIT_FAILED,
    EXIT_INDETERMINATE,
    EXIT_OK,
    SERVED_RETRY_WINDOW_S,
    UI_DIR,
    _verdict_exit,
    classify_served,
    needs_deploy,
    should_retry_served,
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


# ── parse_http_response: a status we cannot read is not a status ─────────

from poll_deploy import parse_http_response  # noqa: E402


@pytest.mark.parametrize("raw, status, body", [
    ('{"kind":"Deployment"}200', 200, '{"kind":"Deployment"}'),
    ('{"reason":"Forbidden"}403', 403, '{"reason":"Forbidden"}'),
    ("200", 200, ""),                       # empty body, status only
])
def test_parse_http_response_splits_trailing_status(raw, status, body):
    assert parse_http_response(raw) == (status, body)


def test_a_body_ending_in_digits_does_not_eat_the_status():
    """curl writes the code AFTER the body, always three chars. A body that
    itself ends in digits -- a replica count, a resourceVersion -- must not have
    its own trailing digits read as the status."""
    assert parse_http_response('{"replicas":3}200') == (200, '{"replicas":3}')


@pytest.mark.parametrize("raw", ["", "ab", "no-status-here", '{"a":1}'])
def test_unparseable_response_is_none_not_a_plausible_code(raw):
    """The failure direction that matters: returning 0 or 200 for a reply we
    could not read would let 'the call did not happen' pass as 'the server
    answered'. None says which."""
    assert parse_http_response(raw)[0] is None


# ── newest_successful_build: tab-separated, never space-split ────────────

from poll_deploy import newest_successful_build  # noqa: E402


def test_newest_successful_build_splits_on_tab():
    out = "a47c93d0-9a6d\tsha256:7e6ec8fd\n"
    assert newest_successful_build(out) == ("a47c93d0-9a6d", "sha256:7e6ec8fd")


def test_a_build_with_no_digest_yields_none_not_a_truncated_string():
    """A build that produced no image still has an id. Returning '' for the
    digest would sail past a truthiness check; None gives the caller's
    sha256: guard something real to reject."""
    assert newest_successful_build("a47c93d0-9a6d\t\n") == ("a47c93d0-9a6d", None)
    assert newest_successful_build("a47c93d0-9a6d\n") == ("a47c93d0-9a6d", None)


@pytest.mark.parametrize("out", ["", "   ", "\n"])
def test_no_builds_at_all_is_none_none(out):
    assert newest_successful_build(out) == (None, None)


# ── rollout_complete: the generation guard is the load-bearing half ──────

from poll_deploy import rollout_complete  # noqa: E402


def _deployment(generation=5, observed=5, replicas=2, updated=2, available=2):
    return json.dumps({
        "metadata": {"generation": generation},
        "spec": {"replicas": replicas},
        "status": {"observedGeneration": observed, "replicas": replicas,
                   "updatedReplicas": updated, "availableReplicas": available},
    })


def test_fully_rolled_out_is_true():
    assert rollout_complete(_deployment()) is True


def test_stale_generation_is_false_even_when_every_count_looks_healthy():
    """THE case. Immediately after a patch the status block still describes the
    PREVIOUS generation -- all replicas updated, all available, perfectly
    healthy -- for the deployment we just replaced. Without the
    observedGeneration guard this returns True instantly and the poll reports a
    rollout that has not started."""
    stale = _deployment(generation=6, observed=5, replicas=2, updated=2, available=2)
    assert rollout_complete(stale) is False


def test_mid_rollout_is_false():
    assert rollout_complete(_deployment(updated=1, available=1)) is False
    assert rollout_complete(_deployment(available=1)) is False


@pytest.mark.parametrize("payload", [
    "", "not json", "[]", "null", '"a string"',
    '{"metadata":{},"spec":{},"status":{}}',            # no generation fields
    '{"metadata":{"generation":5},"spec":{}}',           # no status block at all
    '{"metadata":{"generation":"5"},"spec":{},"status":{"observedGeneration":5}}',
])
def test_unreadable_payload_is_none_never_false(payload):
    """None ('cannot tell') must not collapse into False ('not yet'). False keeps
    the poll waiting until timeout and then reports a rollout FAILURE that never
    happened -- an unreadable reply misfiled as a known-bad state."""
    assert rollout_complete(payload) is None


def test_none_and_false_are_distinguishable_by_the_caller():
    """The two are returned as different values precisely so `_await_rollout`'s
    caller can map them to different exit codes."""
    assert rollout_complete("not json") is None
    assert rollout_complete(_deployment(generation=6, observed=5)) is False


# ── build source dir (issue-77) ──────────────────────────────────────────

def test_ui_dir_is_absolute_and_does_not_depend_on_cwd(tmp_path, monkeypatch):
    """The build source must be anchored to THIS FILE, not the caller's cwd.

    This is the regression that killed the scheduled deploy for three fires: the
    cron's cwd is the *my-hermes* clone, not this repo, so a relative "ui/"
    named a directory that does not exist and `gcloud builds submit` could never
    succeed from the scheduled path. It passed by hand only because a human runs
    it from the repo root -- the happy path and the broken path differ ONLY in
    cwd, which is why nothing caught it until production did.

    Asserted on the resolved value rather than on a substring: a relative "ui/"
    also "ends with ui", so an endswith check alone would stay green on the bug.
    """
    monkeypatch.chdir(tmp_path)
    assert pathlib.Path(UI_DIR).is_absolute()
    assert pathlib.Path(UI_DIR).name == "ui"
    # cwd-invariance, measured rather than assumed
    monkeypatch.chdir("/")
    assert pathlib.Path(UI_DIR).is_absolute()
    # and it points at THIS repo's ui/, not wherever we happen to stand
    # parents[3] from THIS file: tests/ -> cd/ -> tools/ -> repo root.
    # (poll_deploy.py itself is one level up, so it uses parents[2].)
    assert UI_DIR == str(pathlib.Path(__file__).resolve().parents[3] / "ui")


# ---------------------------------------------------------------------------
# issue-96: the post-rollout served check retries for the LB window.
#
# A deploy that fully succeeded exited 3 (INDETERMINATE) because the served
# asset was sampled once, immediately after `rollout status`, while GKE was
# still re-registering the pod: 503 for ~70s, then 200. A check that reports
# "could not verify" on the SUCCESS path trains its reader to discount the
# code, and then it carries no information on the day a deploy really breaks.
# ---------------------------------------------------------------------------

def test_ok_never_retries_even_at_zero_elapsed():
    # Once the asset is good the deploy is verified. Continuing to poll could
    # catch an unrelated later blip and downgrade a verdict already earned.
    assert should_retry_served("ok", 0.0) is False
    assert should_retry_served("ok", 5.0) is False


def test_non_ok_retries_inside_the_window():
    # BUG SHAPE: this is the single-sample conclusion that produced the false
    # INDETERMINATE. A 503 at t=0 must NOT be the final answer.
    assert should_retry_served("indeterminate", 0.0) is True
    assert should_retry_served("indeterminate", 60.0) is True
    # `absent` retries too — right after a rollout it is indistinguishable
    # from the LB not having caught up.
    assert should_retry_served("absent", 10.0) is True


def test_the_window_is_bounded():
    # The retry must terminate; an unbounded wait would hang a deploy.
    w = SERVED_RETRY_WINDOW_S
    assert should_retry_served("indeterminate", w) is False
    assert should_retry_served("indeterminate", w + 1) is False


def test_window_covers_the_measured_lb_lag():
    # Measured 2026-08-10: 503 at 22:03:29Z, 200 by 22:04:13Z (~70s after
    # rollout). A window at or under that would re-introduce the defect.
    assert SERVED_RETRY_WINDOW_S >= 120


def test_three_states_still_distinct_after_the_retry():
    # The retry gives classify_served more chances; it must not blur what the
    # verdicts MEAN. A persistent bad state still exits non-zero, and `absent`
    # and `indeterminate` still exit differently.
    assert _verdict_exit("ok") == EXIT_OK
    assert _verdict_exit("absent") == EXIT_FAILED
    assert _verdict_exit("indeterminate") == EXIT_INDETERMINATE
    assert EXIT_FAILED != EXIT_INDETERMINATE
