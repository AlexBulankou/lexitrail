"""lex#513 — the seed may truncate REFERENCE tables; never the USER tables.

This is the guard for the fix, and it is a guard rather than a comment because
the two lines it forbids looked *deliberate* for the whole life of the file:

    -- Truncate the tables in the right order to remove all data
    TRUNCATE TABLE recall_history;
    TRUNCATE TABLE userwords;

"in the right order" reads as care. It is the ordering you need when a parent is
referenced by a child — except `SET FOREIGN_KEY_CHECKS = 0` two lines above
already makes truncating the parents alone legal, so the guard that would justify
those lines is the same guard that makes them unnecessary. A comment saying
"don't add these back" competes with a comment saying "the right order"; a test
does not.

🔴 THE FAILURE IS UNRECOVERABLE AND SILENT AT THE SOURCE. `recall_history` and
`userwords` appear in no CSV, so nothing below reloads them. There is no restore
path in this repo. 95,141 rows.

The sibling files carry the two traps that make the obvious fixes wrong:
  * `test_seed_path_cascade_513.py`   — REPLACE is DELETE + INSERT, cascades fire
  * `test_word_id_stability_513.py`   — ids were positional, so survival != safety
"""
from __future__ import annotations

import re
from pathlib import Path

SQL = Path(__file__).resolve().parents[1] / "terraform" / "schema-data.sql"

USER_TABLES = ("recall_history", "userwords")
REFERENCE_TABLES = ("words", "wordsets")


def _truncated_tables(text: str) -> set[str]:
    """Tables named by a real TRUNCATE, ignoring commented-out ones.

    The comment filter is load-bearing in BOTH directions. This file documents
    its own history in comments that name the forbidden statements verbatim
    (`TRUNCATE recall_history;` appears in the header as the thing that used to
    happen), so a bare substring search reports the fix as the bug — the exact
    use/mention error that makes a check fire on its own explanation.
    """
    live = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("--")
    )
    return {m.group(1) for m in re.finditer(
        r"TRUNCATE\s+TABLE\s+`?(\w+)`?", live, flags=re.IGNORECASE)}


def test_user_tables_are_never_truncated():
    """The whole point. Both names, asserted separately so the failure says which."""
    truncated = _truncated_tables(SQL.read_text(encoding="utf-8"))
    for table in USER_TABLES:
        assert table not in truncated, (
            f"schema-data.sql truncates `{table}`, which no CSV reloads. "
            "This is the lex#513 data-loss path: 95,141 rows, no restore."
        )


def test_reference_tables_are_still_truncated():
    """The negative control, and it is not decoration.

    Without it, deleting the whole TRUNCATE block passes the test above — and
    that 'fix' breaks reseeding instead, because LOAD DATA would append to a
    populated table and duplicate every row on each run. A guard that only
    forbids is satisfied by doing nothing at all.
    """
    truncated = _truncated_tables(SQL.read_text(encoding="utf-8"))
    for table in REFERENCE_TABLES:
        assert table in truncated, (
            f"schema-data.sql no longer truncates `{table}`; the LOADs below "
            "would append to existing rows on every reseed."
        )


def test_the_comment_filter_does_not_hide_a_real_truncate():
    """Control on the instrument itself: prove the parser still SEES a live
    statement. Without this, a broken regex reports a clean file forever — the
    reassuring direction, on a check whose whole job is to refuse it."""
    assert _truncated_tables("TRUNCATE TABLE recall_history;") == {"recall_history"}
    assert _truncated_tables("-- TRUNCATE TABLE recall_history;") == set()


def test_loads_do_not_use_replace():
    """REPLACE is DELETE + INSERT and both user tables cascade off
    words(word_id), so it destroys the same rows with no TRUNCATE left in the
    file for a reviewer to notice. Pinned in full in the cascade sibling; a
    one-line guard here because this is the file where it would be written."""
    live = "\n".join(
        line for line in SQL.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )
    assert not re.search(r"\bREPLACE\b", live, flags=re.IGNORECASE), (
        "a REPLACE in the seed path cascade-deletes user history"
    )
