"""#111 — an exclusion toggle must not be recorded as a failed recall.

Loaded BY PATH, the same way `test_cache_warm_97.py` loads `cache_warm_policy`:
a plain `from app.recall_policy import ...` executes `app/__init__.py`, which
imports Flask and reaches for a live MySQL — so the import would fail in any
environment without a provisioned backend, which is the very situation the
module was split out to survive. (Verified here: the pre-existing
`tests/test_userwords.py` errors identically on `MYSQL_FILES_BUCKET` and a
refused MySQL connection, and lexitrail has no CI, #77.)
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "recall_policy",
    pathlib.Path(__file__).resolve().parents[1] / "app" / "recall_policy.py")
_policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_policy)

is_recall_event = _policy.is_recall_event


# THE BUG SHAPE: `toggleExclusion` reuses the recall endpoint with
# `recall=False`, the row was written unconditionally, and historyTiles renders
# every row as `correct: Boolean(r.recall)` — so excluding a word drew a RED
# tile the learner never earned.
def test_inclusion_only_is_not_a_recall_event():
    assert is_recall_event({"recall_state": 0, "recall": False,
                            "is_included": False, "inclusion_only": True}) is False


# BACK-COMPAT, and the direction is load-bearing. An older UI sends no flag,
# and a backend deployed ahead of the frontend must behave exactly as today —
# the absent case degrades to the CURRENT bug, never to dropping real recalls.
# Inverting this default would turn a cosmetic defect into data loss.
@pytest.mark.parametrize("data", [
    {"recall_state": 1, "recall": True, "is_included": True},   # no flag at all
    {"recall_state": 1, "recall": True, "inclusion_only": False},
    {},                                                          # empty body
])
def test_absent_or_false_flag_still_records(data):
    assert is_recall_event(data) is True


def test_a_non_dict_body_still_records():
    """Fail toward recording. A malformed body must not silently drop a
    recall — the safe direction for a write we cannot reconstruct."""
    assert is_recall_event(None) is True
    assert is_recall_event("not a dict") is True


@pytest.mark.parametrize("truthy", [True, 1, "yes", ["x"]])
def test_truthy_flag_values_suppress(truthy):
    """`bool()` coercion is deliberate: a JSON client sending 1 rather than
    true means the same thing, and reading it strictly would silently keep
    writing the bad rows."""
    assert is_recall_event({"inclusion_only": truthy}) is False


@pytest.mark.parametrize("falsy", [False, 0, "", None, []])
def test_falsy_flag_values_do_not_suppress(falsy):
    assert is_recall_event({"inclusion_only": falsy}) is True


def test_the_two_cases_are_distinguishable():
    """The whole point: a recall and an inclusion toggle must not produce the
    same answer. Asserting each separately would still pass if the function
    collapsed to a constant."""
    recall = {"recall_state": 0, "recall": True, "is_included": True}
    toggle = {"recall_state": 0, "recall": False, "is_included": False,
              "inclusion_only": True}
    assert is_recall_event(recall) != is_recall_event(toggle)
