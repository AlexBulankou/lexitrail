"""#109 (RD-6 slice A) — a bulk "✔️ to all" row must be distinguishable.

Loaded BY PATH for the same reason as `test_recall_policy_111.py`: importing
`app.recall_policy` normally executes `app/__init__.py`, which imports Flask and
reaches for a live MySQL, so the import fails in any environment without a
provisioned backend — which is exactly the situation the pure-policy module was
split out to survive.
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

recall_provenance = _policy.recall_provenance
RECALL_PROVENANCE_VALUES = _policy.RECALL_PROVENANCE_VALUES


# THE BUG SHAPE: `handleMemorizedMultiple` issues N independent PUTs whose
# bodies are byte-identical to a single card tap, so the two are the same call
# and every scheduling decision downstream is computed from data that cannot
# tell knowing from tapping.
def test_a_declared_bulk_recall_is_recorded_as_bulk():
    assert recall_provenance({"recall": True, "provenance": "bulk"}) == "bulk"


def test_a_declared_single_recall_is_recorded_as_single():
    assert recall_provenance({"recall": True, "provenance": "single"}) == "single"


# 🔴 THE LOAD-BEARING DIRECTION. Absent must degrade to UNKNOWN, never to
# "single". An older UI talking to a newer backend sends no flag, and so did
# every one of the ~94k rows written before the column existed; calling those
# "single" would assert they were earned when nothing recorded that they were —
# the exact failure #109 exists to end (acceptance criterion 4).
@pytest.mark.parametrize("data", [
    {},                                   # older UI: no flag at all
    {"recall": True},                     # today's payload, unchanged
    {"provenance": None},                 # explicit null
    {"provenance": ""},                   # empty string
    {"provenance": "single "},            # whitespace — not the allowlist value
    {"provenance": "BULK"},               # case matters; not in the allowlist
    {"provenance": "imported"},           # a value we have not heard of yet
    {"provenance": 1},                    # wrong type
    None,                                 # not a mapping at all
    "single",                             # a bare string body
])
def test_anything_not_explicitly_declared_is_unknown_not_single(data):
    assert recall_provenance(data) is None


def test_an_unrecognised_value_is_not_rejected_it_is_unknown():
    """A recall the learner actually made must never be LOST to an unknown flag.

    The distinction that matters: `recall_provenance` returns None rather than
    raising, so the row is still written — with unknown provenance — instead of
    the whole PUT failing on a value the server has not heard of.
    """
    assert recall_provenance({"provenance": "wat"}) is None


def test_the_allowlist_is_exactly_the_two_declarable_values():
    """Pins the allowlist so a third value cannot be added without a decision.

    A new source (an import, a migration backfill) is a product question about
    what counts as earned, not a spelling change.
    """
    assert RECALL_PROVENANCE_VALUES == frozenset({"single", "bulk"})


def test_provenance_and_inclusion_only_are_independent():
    """#111's flag and #109's must not interfere.

    An inclusion toggle writes no history row at all, so its provenance is
    irrelevant — but a payload carrying both must still answer each question
    with the other's answer unchanged.
    """
    data = {"recall": False, "is_included": True,
            "inclusion_only": True, "provenance": "bulk"}
    assert _policy.is_recall_event(data) is False
    assert recall_provenance(data) == "bulk"
    data2 = {"recall": True, "provenance": "bulk"}
    assert _policy.is_recall_event(data2) is True
