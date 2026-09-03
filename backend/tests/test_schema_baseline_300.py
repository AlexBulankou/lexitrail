"""issue-300: the baseline and the declarative schema must not drift apart.

`000_baseline.sql` is a capture of the LIVE schema; `terraform/schema-tables.sql`
is the retired root's declarative seed. At capture time they agreed exactly --
28 columns, both sides. This pins that agreement so the realistic near-term
divergence (someone edits one and not the other) surfaces as a failure with a
message saying which, rather than as a schema file that quietly stops describing
anything real.

⚠️ CORRECTION (hc2, #309 review): an earlier version of this note said
"lexitrail's cloudbuild.yaml has no pytest step, so nothing runs this in CI."
The first half is true and the CONCLUSION IS FALSE -- `.github/workflows/
backend-tests.yml` runs pytest on every PR touching backend paths (#269). I
checked Cloud Build, found nothing, and generalised to "no CI", which is the
wrong-population error: I enumerated one CI surface and concluded about all of
them. These tests DO gate merges.

⚠️ This compares column NAMES and object inventory only -- not types,
nullability, indexes, or the view body. A type change passes this test.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "backend" / "migrations"
BASELINE = MIGRATIONS / "000_baseline.sql"
DECLARED = ROOT / "terraform" / "schema-tables.sql"


def _cols_from_baseline() -> set:
    """Columns from the mysqldump-style CREATE TABLE blocks."""
    src = BASELINE.read_text()
    cols = set()
    for m in re.finditer(r"CREATE TABLE `(\w+)` \((.*?)\n\) ENGINE", src, re.S):
        table = m.group(1)
        for line in m.group(2).split("\n"):
            line = line.strip().rstrip(",")
            cm = re.match(r"`(\w+)`\s", line)
            if cm:
                cols.add(f"{table}.{cm.group(1)}")
    return cols


def _cols_added_by_migrations() -> set:
    """Columns the applied migrations ADD on top of the baseline (issue-109).

    🔴 WHY THIS FUNCTION EXISTS. The comparison below used to be
    `baseline == declared`, and that invariant is unsatisfiable the moment any
    migration adds a column: `000_baseline.sql` is a FROZEN capture and is never
    re-taken, while `terraform/schema-tables.sql` has to gain the column or every
    fresh database — CI's own test DB, via `LEXITRAIL_SCHEMA_SQL_PATH` — is built
    without it.

    So the old check actively pushed authors AWAY from updating the mirror, which
    is how `002_add_users_timezone.sql` came to add `users.timezone` to the live
    schema and not to the declared one. That gap was benign only because nothing
    reads that column yet; issue-109's `recall_history.provenance` is read on the
    very next request, and CI failed 9 tests with `(1054) Unknown column` — the
    same gap, load-bearing.

    ⇒ The invariant that is actually true is `baseline + migrations == declared`.

    ⚠️ Deliberately narrow: `ADD COLUMN` only. A DROP or a RENAME would need its
    own handling, and guessing at one now would be a parser for a case that has
    never occurred — if one lands, `test_the_migration_parser_sees_every_add`
    below fails loudly on the count rather than silently mis-modelling it.
    """
    cols = set()
    for f in sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql")):
        if f.name == "000_baseline.sql":
            continue  # never applied; it is the point 001 migrates FROM
        for m in re.finditer(
                r"ALTER\s+TABLE\s+`?(\w+)`?\s+ADD\s+COLUMN\s+`?(\w+)`?",
                f.read_text(), re.I):
            cols.add(f"{m.group(1)}.{m.group(2)}")
    return cols


def _cols_from_declared() -> set:
    """Columns from the hand-written CREATE TABLE IF NOT EXISTS blocks."""
    src = DECLARED.read_text().split("CREATE OR REPLACE VIEW")[0]
    cols = set()
    for m in re.finditer(
        r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\);", src, re.S
    ):
        table = m.group(1)
        for line in m.group(2).split("\n"):
            line = line.strip().rstrip(",")
            if not line or line.upper().startswith(
                ("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "KEY", "INDEX",
                 "CONSTRAINT", "--")
            ):
                continue
            cols.add(f"{table}.{line.split()[0].strip('`')}")
    return cols


@pytest.fixture(scope="module")
def parsed():
    if not (BASELINE.is_file() and DECLARED.is_file()):
        pytest.skip("baseline or declarative schema not in this tree")
    base, decl = _cols_from_baseline(), _cols_from_declared()
    adds = _cols_added_by_migrations()
    # Guard the PARSERS before comparing them: two empty sets are equal, and
    # would report agreement while establishing nothing.
    assert len(base) > 20, f"baseline parser found only {len(base)} columns"
    assert len(decl) > 20, f"declarative parser found only {len(decl)} columns"
    # The migration parser gets the same guard for the same reason: a regex that
    # silently stops matching turns this whole check back into `base == decl`,
    # which is the invariant issue-109 found to be unsatisfiable.
    assert adds, "migration parser found NO ADD COLUMN — it has stopped matching"
    return base, decl, adds


def test_baseline_and_declarative_schema_agree(parsed):
    """issue-300, corrected by issue-109: `baseline + migrations == declared`."""
    base, decl, adds = parsed
    effective = base | adds
    missing_from_declared = sorted(effective - decl)
    only_declared = sorted(decl - effective)
    assert not missing_from_declared and not only_declared, (
        "the live schema (000_baseline.sql + backend/migrations/) and "
        "terraform/schema-tables.sql have drifted.\n"
        "  in live, MISSING from schema-tables.sql: %s\n"
        "     -> a fresh database (CI's test DB, any new environment) is built "
        "without it; a read of it fails (1054) Unknown column\n"
        "  in schema-tables.sql, not in live: %s\n"
        "     -> an edit to the mirror with no migration behind it\n"
        "A schema change needs BOTH: a migration (for the existing database) "
        "and the mirror (for fresh ones)."
        % (missing_from_declared, only_declared)
    )


def test_the_migration_parser_sees_every_add(parsed):
    """Positive control on `_cols_added_by_migrations`, pinned by NAME.

    The test above compares two sets. If the migration parser quietly matched
    nothing, `effective` collapses to `base` and the comparison silently reverts
    to the unsatisfiable pre-issue-109 invariant — passing today only because
    the mirror would then have to be wrong in the matching way. Pinning the
    actual columns means a regex that stops matching fails HERE, naming what it
    lost, rather than changing what the other test means.
    """
    _, _, adds = parsed
    assert adds == {"users.timezone", "recall_history.provenance"}, (
        "migration ADD COLUMN set is %s. If a migration landed, add its column "
        "here AND to terraform/schema-tables.sql." % sorted(adds))


def test_users_still_has_only_email(parsed):
    """The concrete blocker #187 is waiting on -- pinned so its fix is visible."""
    base, _, _ = parsed
    users = {c for c in base if c.startswith("users.")}
    assert users == {"users.email"}, (
        "users columns are now %s. If a timezone column landed, #187 is "
        "unblocked and this pin should move with the migration that added it."
        % sorted(users)
    )
