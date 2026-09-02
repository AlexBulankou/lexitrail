"""Pins the THREE-state contract of the live schema-drift check (lexitrail#308).

Run against the real cluster before this file existed, and all four arms
discriminated:

    real schema                 exit 0  PASS "production matches the baseline (28 columns)"
    --schema lexitrail          exit 3  CANNOT-TELL, and it names the wrong-schema cause
    --pod mysql-nope            exit 3  CANNOT-TELL "the query did not run (pods not found)"
    --namespace nope            exit 3  CANNOT-TELL "could not read the mysql-root secret"

🔴 `test_an_empty_live_set_refuses_to_be_compared` is the load-bearing assertion,
and the second arm above is why. A wrong schema name is a VALID QUERY AGAINST
NOTHING: no error, no warning, an empty result. Compared either way it yields a
confident wrong answer -- 28 "columns missing from production" one way, "no
drift" the other -- and the second is a drift check reporting clean because it
looked at nothing. That is the exact failure #308 was filed about, and it would
be reintroduced inside the fix for it.

I made that mistake by hand on 2026-09-02 and got as far as writing up a defect
in a README that had been right all along. Every other test here would still
pass if the empty case were allowed through as PASS.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "check_schema_drift", Path(__file__).with_name("check_schema_drift.py"),
)
mod = importlib.util.module_from_spec(_SPEC)
sys.modules["check_schema_drift"] = mod
_SPEC.loader.exec_module(mod)

PASS, FAIL, CANNOT_TELL = mod.PASS, mod.FAIL, mod.CANNOT_TELL
BASE = {"users.user_id", "users.email", "words.word_id"}


def test_matching_sets_pass():
    code, msg = mod.verdict(set(BASE), set(BASE))
    assert code == PASS, msg


def test_an_empty_live_set_refuses_to_be_compared():
    """🔴 The wrong-schema case. NOT pass, and NOT drift."""
    code, msg = mod.verdict(set(), set(BASE))
    assert code == CANNOT_TELL, msg
    assert "lexitraildb" in msg and "namespace" in msg, (
        "the message must name the cause -- a bare CANNOT-TELL sends the reader "
        "looking at the database instead of at their own query"
    )


def test_none_is_cannot_tell_and_carries_the_reason():
    code, msg = mod.verdict(None, set(BASE), "pods 'mysql-nope' not found")
    assert code == CANNOT_TELL, msg
    assert "mysql-nope" in msg, msg


def test_a_column_present_live_and_absent_from_the_repo_is_a_fail():
    """The hand-run ALTER this check exists for."""
    code, msg = mod.verdict(BASE | {"users.created_at"}, set(BASE))
    assert code == FAIL, msg
    assert "users.created_at" in msg, msg
    assert "hand-run ALTER" in msg, msg


def test_a_column_in_the_repo_and_absent_live_is_also_a_fail():
    """The other direction: a migration that has not reached production."""
    code, msg = mod.verdict(BASE - {"words.word_id"}, set(BASE))
    assert code == FAIL, msg
    assert "words.word_id" in msg, msg


def test_both_directions_are_reported_not_just_the_first():
    live = (BASE - {"words.word_id"}) | {"users.created_at"}
    _, msg = mod.verdict(live, set(BASE))
    assert "users.created_at" in msg and "words.word_id" in msg, msg


def test_an_unparseable_baseline_blames_the_parser_not_the_database():
    """An empty EXPECTED set is our bug. Saying 'production has 28 extra
    columns' would send someone to the cluster to fix a regex."""
    code, msg = mod.verdict(set(BASE), set())
    assert code == CANNOT_TELL, msg
    assert "parser" in msg, msg


def test_the_exclusions_cannot_hide_a_real_column():
    """Both exclusions are objects whose absence from the baseline is CORRECT --
    a VIEW the baseline parser does not read, and the migration runner's own
    ledger. Nothing is excluded because it was inconvenient, and the list must
    not grow without that justification."""
    assert set(mod.EXCLUDED_TABLES) == {"daily_recall_stats", "schema_migrations"}


def test_the_schema_is_not_the_namespace():
    """Three characters apart, and only one of them is typed all day."""
    assert mod.SCHEMA == "lexitraildb"
    assert mod.NAMESPACE == "lexitrail"
    assert mod.SCHEMA != mod.NAMESPACE


def test_the_baseline_parser_reads_the_real_file():
    """A parser that silently returns nothing would make every run CANNOT-TELL
    -- honest, but permanently uninformative."""
    cols = mod.cols_from_baseline()
    assert len(cols) > 20, f"parsed only {len(cols)}"
    assert all("." in c for c in cols)
    assert not any(c.startswith(t + ".") for c in cols for t in mod.EXCLUDED_TABLES)


def test_the_three_exit_codes_are_distinct():
    assert (PASS, FAIL, CANNOT_TELL) == (0, 1, 3)
