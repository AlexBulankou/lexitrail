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


# ---------------------------------------------------------------------------
# issue-308 follow-up — the repo's belief is baseline PLUS migrations.
#
# Found before shipping the first additive migration (lexitrail#187's timezone
# column). `expected` was `cols_from_baseline()` alone, so the moment a properly
# applied ALTER landed, the new column would be "in LIVE not in baseline" — the
# message this script prints for a HAND-RUN ALTER. The detector would have
# accused us of the exact defect it exists to catch, on its first real use.
#
# 001_strip_trailing_cr.sql never exposed it: DML changes no schema.
# ---------------------------------------------------------------------------

def _mig(tmp_path, **files):
    for name, body in files.items():
        (tmp_path / name).write_text(body)
    return tmp_path


def test_an_added_column_counts_as_expected(tmp_path):
    _mig(tmp_path, **{
        "000_baseline.sql": "CREATE TABLE `users` (\n  `email` varchar(320)\n) ENGINE=InnoDB;",
        "002_add_users_timezone.sql": "ALTER TABLE users ADD COLUMN timezone VARCHAR(64) NULL;",
    })
    cols, unparsed = mod.cols_from_migrations(tmp_path)
    assert cols == {"users.timezone"}
    assert unparsed == []


def test_the_baseline_is_never_read_as_a_migration(tmp_path):
    """000 is the point migrations run FROM. Counting its CREATE TABLE here
    would double-count every column and mask a real drop."""
    _mig(tmp_path, **{
        "000_baseline.sql": "ALTER TABLE users ADD COLUMN nonsense INT;",
    })
    assert mod.cols_from_migrations(tmp_path) == (set(), [])


def test_backticked_and_bare_identifiers_both_parse(tmp_path):
    _mig(tmp_path, **{
        "002_a.sql": "ALTER TABLE `users` ADD COLUMN `tz` VARCHAR(64);",
        "003_b.sql": "alter table userwords add column note text;",
    })
    cols, unparsed = mod.cols_from_migrations(tmp_path)
    assert cols == {"users.tz", "userwords.note"} and unparsed == []


# --- the CANNOT-TELL arm: an unparsed file must never silently contribute ---

def test_ddl_this_parser_does_not_understand_is_REPORTED_not_ignored(tmp_path):
    """🔴 The important one. Silently contributing nothing shrinks `expected`
    and prints a confident FAIL naming a column the repo does know about —
    not-looking rendering as a result, which is what this script exists to
    refuse."""
    _mig(tmp_path, **{"002_rename.sql": "ALTER TABLE users RENAME COLUMN a TO b;"})
    cols, unparsed = mod.cols_from_migrations(tmp_path)
    assert unparsed == ["002_rename.sql"], f"unparsed DDL was swallowed: {cols}"


def test_a_file_MIXING_parsed_and_unparsed_ddl_is_still_reported(tmp_path):
    """The dangerous shape: the ADD COLUMN parses, so `cols` looks right and
    the DROP alongside it is invisible."""
    _mig(tmp_path, **{"002_mixed.sql":
                      "ALTER TABLE users ADD COLUMN tz VARCHAR(64);\n"
                      "DROP TABLE stale_thing;"})
    cols, unparsed = mod.cols_from_migrations(tmp_path)
    assert cols == {"users.tz"}
    assert unparsed == ["002_mixed.sql"], "a mixed file reported clean"


def test_pure_DML_migrations_are_silent_and_not_unparsed(tmp_path):
    """001 is real and is DML. It must contribute nothing AND not trip the
    CANNOT-TELL arm, or every run refuses forever."""
    _mig(tmp_path, **{"001_strip.sql": "UPDATE words SET def1 = TRIM(def1);"})
    assert mod.cols_from_migrations(tmp_path) == (set(), [])


def test_the_REAL_migrations_dir_is_silent_today(tmp_path):
    """Behaviour is unchanged until the first additive migration lands — the
    no-op-today property that makes this safe to ship ahead of #187."""
    assert mod.cols_from_migrations() == (set(), [])


def test_excluded_tables_are_excluded_here_too(tmp_path):
    _mig(tmp_path, **{"002_x.sql":
                      "ALTER TABLE schema_migrations ADD COLUMN note TEXT;"})
    cols, _ = mod.cols_from_migrations(tmp_path)
    assert cols == set(), "an excluded table leaked into expected"


# ---------------------------------------------------------------------------
# 🔴 WIRING. The tests above pin the helper; a mutation that dropped `| added`
# from main() reddened NOTHING, so the helper could have been correct and
# unused. That is the same shape I flagged on a peer's PR the same evening:
# a guard on one path, and the delegation to it unverified.
# ---------------------------------------------------------------------------

def test_main_ADDS_migration_columns_to_expected(monkeypatch, capsys):
    """A column added by a migration and present live must read PASS, not
    'in LIVE not in baseline' — the message reserved for a hand-run ALTER."""
    monkeypatch.setattr(mod, "cols_from_baseline", lambda *a, **k: {"users.email"})
    monkeypatch.setattr(mod, "cols_from_migrations",
                        lambda *a, **k: ({"users.timezone"}, []))
    monkeypatch.setattr(mod, "_live_cols",
                        lambda *a, **k: ({"users.email", "users.timezone"}, ""))
    assert mod.main([]) == PASS, capsys.readouterr().out


def test_main_still_FAILS_on_a_column_no_migration_explains(monkeypatch, capsys):
    """The negative control. Widening `expected` must not blunt the detector:
    a hand-run ALTER is still a hand-run ALTER."""
    monkeypatch.setattr(mod, "cols_from_baseline", lambda *a, **k: {"users.email"})
    monkeypatch.setattr(mod, "cols_from_migrations", lambda *a, **k: (set(), []))
    monkeypatch.setattr(mod, "_live_cols",
                        lambda *a, **k: ({"users.email", "users.sneaked_in"}, ""))
    assert mod.main([]) == FAIL, capsys.readouterr().out


def test_main_REFUSES_when_a_migration_could_not_be_parsed(monkeypatch, capsys):
    """An unparsed migration means `expected` is unknown, so there is nothing
    honest to compare. Refuse rather than print a confident verdict."""
    monkeypatch.setattr(mod, "cols_from_baseline", lambda *a, **k: {"users.email"})
    monkeypatch.setattr(mod, "cols_from_migrations",
                        lambda *a, **k: (set(), ["002_rename.sql"]))
    monkeypatch.setattr(mod, "_live_cols", lambda *a, **k: ({"users.email"}, ""))
    code = mod.main([])
    out = capsys.readouterr().out
    assert code == CANNOT_TELL, out
    assert "002_rename.sql" in out, "the refusal must name the file to fix"


def test_a_COMMENTED_ddl_statement_is_not_read_as_ddl(tmp_path):
    """🔴 Found by running the parser against the REAL migration, not a fixture.

    Our own convention is to document a migration's reverse next to it:

        -- REVERSIBLE:  ALTER TABLE users DROP COLUMN timezone;

    A regex counting DDL verbs cannot tell that mention from a statement, so the
    file reported as unaccounted-for and the whole check refused. Every fixture
    I had written by hand was a bare one-line ALTER with no prose, so none of
    them could have found it — the convention that makes migrations readable is
    the one that broke the parser reading them."""
    _mig(tmp_path, **{"002_tz.sql":
                      "-- REVERSIBLE: ALTER TABLE users DROP COLUMN timezone;\n"
                      "-- see also: CREATE TABLE notes, DROP TABLE nothing\n"
                      "/* block: ALTER TABLE users ADD COLUMN decoy INT; */\n"
                      "ALTER TABLE `users` ADD COLUMN `timezone` VARCHAR(64) NULL;\n"})
    cols, unparsed = mod.cols_from_migrations(tmp_path)
    assert cols == {"users.timezone"}, f"a commented ALTER leaked in: {cols}"
    assert unparsed == [], "prose about DDL was counted as DDL"


def test_stripping_comments_does_not_hide_REAL_ddl_on_the_same_line(tmp_path):
    """The negative control for the strip: a statement followed by a trailing
    comment must still be seen."""
    _mig(tmp_path, **{"002_x.sql":
                      "ALTER TABLE users ADD COLUMN tz VARCHAR(64);  -- the expand half\n"
                      "DROP TABLE stale;  -- and something we do not parse\n"})
    cols, unparsed = mod.cols_from_migrations(tmp_path)
    assert cols == {"users.tz"}
    assert unparsed == ["002_x.sql"], "a real DROP hid behind comment-stripping"


# ---------------------------------------------------------------------------
# hc2@'s review catch: NEITHER regex ORDER is correct, so the strip is a single
# pass. Both fixtures below eat a real ALTER under one of the two orderings —
# and SILENTLY, not as CANNOT-TELL: with the ALTER gone,
# len(_DDL_RE.findall) == len(adds) == 0, so the file is not flagged unparsed
# either. The column vanishes from `expected` and reports as "present live and
# absent from the repo" — this script's message for a hand-run ALTER.
# ---------------------------------------------------------------------------

def test_a_block_opener_inside_a_LINE_comment_does_not_eat_ddl():
    """hc2@'s counterexample. Kills block-then-line."""
    sql = ("-- see the /* directory for migration notes\n"
           "ALTER TABLE users ADD COLUMN real_col INT;\n"
           "/* a genuine trailing block comment */\n")
    assert "ADD COLUMN" in mod._strip_sql_comments(sql)


def test_a_line_opener_inside_a_BLOCK_comment_does_not_eat_ddl():
    """The mirror. Kills line-then-block — and note the SECOND block comment:
    without a later `*/` the orphaned `/*` simply fails to match and the bug
    hides, which is why a minimal two-line fixture makes line-first look
    correct. It was the fixture that was safe, not the ordering."""
    sql = ("/* note -- see below */\n"
           "ALTER TABLE users ADD COLUMN real_col INT;\n"
           "/* a second, genuine block comment */\n")
    assert "ADD COLUMN" in mod._strip_sql_comments(sql)


def test_both_orderings_are_wrong_which_is_why_this_is_a_scanner():
    """Pins the ARGUMENT, not just the fix: each sequential ordering eats the
    ALTER on its own mirrored input, so 'flip the order' is not a repair."""
    import re
    A = ("-- see the /* directory\nALTER TABLE users ADD COLUMN c INT;\n/* t */\n")
    B = ("/* note -- x */\nALTER TABLE users ADD COLUMN c INT;\n/* second */\n")
    block_first = lambda s: re.sub(r"--[^\n]*", " ", re.sub(r"/\*.*?\*/", " ", s, flags=re.S))
    line_first = lambda s: re.sub(r"/\*.*?\*/", " ", re.sub(r"--[^\n]*", " ", s), flags=re.S)
    assert "ADD COLUMN" not in block_first(A), "block-first was expected to eat A"
    assert "ADD COLUMN" not in line_first(B), "line-first was expected to eat B"
    # ...and the scanner survives both.
    assert "ADD COLUMN" in mod._strip_sql_comments(A)
    assert "ADD COLUMN" in mod._strip_sql_comments(B)


def test_a_comment_marker_inside_a_STRING_LITERAL_is_not_a_comment():
    """A `'--'` DEFAULT would otherwise blank the rest of the line and hide the
    DDL after it."""
    sql = ("ALTER TABLE users ADD COLUMN c VARCHAR(8) DEFAULT '--'; "
           "ALTER TABLE t ADD COLUMN d INT;\n")
    out = mod._strip_sql_comments(sql)
    assert out.count("ADD COLUMN") == 2, out


def test_an_unterminated_block_comment_eats_only_to_EOF():
    sql = "ALTER TABLE users ADD COLUMN c INT;\n/* never closed\n"
    assert "ADD COLUMN" in mod._strip_sql_comments(sql)


# --- controls: stripping must still actually STRIP -------------------------

def test_a_decoy_inside_a_block_comment_still_does_not_leak():
    sql = ("/* ALTER TABLE decoy ADD COLUMN d INT; */\n"
           "ALTER TABLE users ADD COLUMN c INT;\n")
    out = mod._strip_sql_comments(sql)
    assert "decoy" not in out and out.count("ADD COLUMN") == 1


def test_real_ddl_after_a_trailing_comment_is_still_seen():
    """The CANNOT-TELL arm depends on unparsed DDL remaining visible."""
    sql = "ALTER TABLE users ADD COLUMN c INT;  -- the expand half\nDROP TABLE stale;\n"
    assert "DROP TABLE" in mod._strip_sql_comments(sql)
