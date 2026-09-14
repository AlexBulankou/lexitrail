"""lex#513 — `REPLACE` in the seed path would cascade-delete the user data it is meant to save.

The issue's ORIGINAL acceptance criterion proposed:

    "LOAD DATA ... REPLACE into words/wordsets instead of truncating four
     tables, so reloading reference data cannot touch user tables at all."

**That is false, and it fails in the quiet direction.** `REPLACE` is not an
upsert: MySQL tries the INSERT, hits the duplicate key, **DELETES the conflicting
row**, then inserts again. The delete is a real delete, so `ON DELETE CASCADE`
fires — and both user tables cascade off `words(word_id)`:

    userwords       FOREIGN KEY (word_id) REFERENCES words(word_id) ON DELETE CASCADE
    recall_history  FOREIGN KEY (word_id) REFERENCES words(word_id) ON DELETE CASCADE

Ordering in `schema-data.sql` decides whether the cascade is armed, and today it is:

    SET FOREIGN_KEY_CHECKS = 0;   <- truncates happen under this
    TRUNCATE ...
    SET FOREIGN_KEY_CHECKS = 1;   <- RE-ENABLED here
    LOAD DATA ... wordsets.csv    <- both LOADs run with CASCADES ARMED
    LOAD DATA ... words.csv

So swapping TRUNCATE for REPLACE and leaving the file's shape alone — the obvious
reading of that AC — destroys the same 95,141 `recall_history` rows, **with no
TRUNCATE left in the file to notice.** Strictly worse than today's bug in one
respect: the destructive statement disappears from the place a reviewer looks.

🔴 WHY THIS IS A TEST AND NOT A PARAGRAPH: the correction lives in an issue
comment and an issue body, and neither is executable. The AC was written down as
a thing to implement; a prose retraction does not stop someone implementing it.

WHAT THIS PINS — a CONJUNCTION, deliberately, not a blanket ban on REPLACE:

    NOT (user tables cascade off words.word_id  AND  the seed path REPLACEs words)

Either half alone is fine. If someone later removes `ON DELETE CASCADE` — making
the user rows survive a word delete — then REPLACE becomes discussable and this
test stops objecting on its own, because the hazard it names is genuinely gone.
A blanket ban would forbid a safe future state and would eventually be deleted
wholesale, taking the live half with it.

⚠️ The correct shape is an UPDATE, so no DELETE ever happens: LOAD into a staging
table, then `INSERT ... SELECT ... ON DUPLICATE KEY UPDATE`. Nothing cascades.
"""
from __future__ import annotations

import re
from pathlib import Path

TF = Path(__file__).resolve().parent.parent / "terraform"
SCHEMA = TF / "schema-tables.sql"
SEED = TF / "schema-data.sql"

# The two tables whose rows are USER data: present in no CSV, unrecoverable.
USER_TABLES = ("userwords", "recall_history")


def _cascades_off_words(table: str, schema_sql: str) -> bool:
    """True when `table` deletes its rows when a `words` row is deleted."""
    m = re.search(rf"CREATE TABLE IF NOT EXISTS {table}\s*\((.*?)\n\);",
                  schema_sql, re.S | re.I)
    assert m, f"could not locate CREATE TABLE for {table} — schema shape changed"
    body = m.group(1)
    fk = re.search(r"FOREIGN KEY\s*\(\s*word_id\s*\)\s*REFERENCES\s+words\s*\(\s*word_id\s*\)"
                   r"([^,\n]*)", body, re.I)
    return bool(fk and "ON DELETE CASCADE" in fk.group(1).upper())


def test_the_hazard_precondition_still_holds():
    """Both user tables cascade off `words`. This is WHY REPLACE is unsafe.

    Not decoration: if this ever goes False the conjunction below stops binding,
    and that must be a visible, deliberate change rather than a silent one.
    """
    schema = SCHEMA.read_text(encoding="utf-8")
    for t in USER_TABLES:
        assert _cascades_off_words(t, schema), (
            f"lex#513: {t} no longer cascades off words(word_id). That may be "
            f"correct — but it changes the seed-path hazard, so re-read #513 "
            f"rather than assuming REPLACE is now safe."
        )


def test_seed_path_does_not_REPLACE_while_the_cascade_exists():
    """The conjunction. Fails if someone implements #513's original AC2."""
    schema = SCHEMA.read_text(encoding="utf-8")
    seed = SEED.read_text(encoding="utf-8")

    cascading = [t for t in USER_TABLES if _cascades_off_words(t, schema)]
    if not cascading:
        return  # hazard genuinely gone; nothing to object to

    # REPLACE targeting the reference tables, in either LOAD DATA or INSERT form.
    offending = re.findall(
        r"^(?!\s*--).*\bREPLACE\b(?!\s+VIEW)[^\n;]*\b(?:INTO\s+)?(words|wordsets)\b",
        seed, re.I | re.M)
    assert not offending, (
        f"lex#513: schema-data.sql uses REPLACE on {sorted(set(offending))} while "
        f"{cascading} still cascade off words(word_id). REPLACE is DELETE+INSERT, "
        f"so this deletes user rows — the exact data loss #513 exists to stop, and "
        f"with no TRUNCATE left in the file to notice. Use a staging table + "
        f"INSERT ... ON DUPLICATE KEY UPDATE (an UPDATE cascades nothing)."
    )


def test_the_replace_detector_can_actually_fire():
    """NEGATIVE CONTROL — a guard that cannot fail is not a guard.

    Without this, a typo in the regex above yields a permanently-green test that
    reads exactly like a clean seed path.
    """
    pat = re.compile(
        r"^(?!\s*--).*\bREPLACE\b(?!\s+VIEW)[^\n;]*\b(?:INTO\s+)?(words|wordsets)\b",
        re.I | re.M)
    assert pat.findall("LOAD DATA LOCAL INFILE '/mnt/csv/words.csv' REPLACE INTO TABLE words"), \
        "detector missed the canonical harmful line — it would never fire in CI"
    assert pat.findall("REPLACE INTO words (word_id) VALUES (1)"), \
        "detector missed the plain INSERT-form REPLACE"
    # ...and stays silent on the things it must NOT flag:
    assert not pat.findall("CREATE OR REPLACE VIEW daily_recall_stats AS"), \
        "detector flags CREATE OR REPLACE VIEW — unrelated, would FP on schema-tables.sql"
    assert not pat.findall("-- REPLACE INTO words would cascade; do not"), \
        "detector flags a COMMENT explaining the hazard — it would fire on its own docs"
