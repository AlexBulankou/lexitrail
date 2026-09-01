"""issue-300: the baseline and the declarative schema must not drift apart.

`000_baseline.sql` is a capture of the LIVE schema; `terraform/schema-tables.sql`
is the retired root's declarative seed. At capture time they agreed exactly --
28 columns, both sides. This pins that agreement so the realistic near-term
divergence (someone edits one and not the other) surfaces as a failure with a
message saying which, rather than as a schema file that quietly stops describing
anything real.

⚠️ Scope, so nobody inherits a guard that does not run: lexitrail's
`cloudbuild.yaml` has NO pytest step, so nothing executes this in CI. It is a
local/manual gate. Wiring a test step is #235's lane.

⚠️ This compares column NAMES and object inventory only -- not types,
nullability, indexes, or the view body. A type change passes this test.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "backend" / "migrations" / "000_baseline.sql"
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
    # Guard the PARSERS before comparing them: two empty sets are equal, and
    # would report agreement while establishing nothing.
    assert len(base) > 20, f"baseline parser found only {len(base)} columns"
    assert len(decl) > 20, f"declarative parser found only {len(decl)} columns"
    return base, decl


def test_baseline_and_declarative_schema_agree(parsed):
    base, decl = parsed
    only_baseline = sorted(base - decl)
    only_declared = sorted(decl - base)
    assert not only_baseline and not only_declared, (
        "issue-300: the captured baseline and terraform/schema-tables.sql have "
        "drifted.\n  only in 000_baseline.sql (i.e. live): %s\n  only in "
        "schema-tables.sql (i.e. declared): %s\nIf this is an intended schema "
        "change it needs a migration in backend/migrations/, not an edit to one "
        "side." % (only_baseline, only_declared)
    )


def test_users_still_has_only_email(parsed):
    """The concrete blocker #187 is waiting on -- pinned so its fix is visible."""
    base, _ = parsed
    users = {c for c in base if c.startswith("users.")}
    assert users == {"users.email"}, (
        "users columns are now %s. If a timezone column landed, #187 is "
        "unblocked and this pin should move with the migration that added it."
        % sorted(users)
    )
