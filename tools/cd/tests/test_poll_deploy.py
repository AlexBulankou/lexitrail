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
