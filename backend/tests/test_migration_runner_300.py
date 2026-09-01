"""issue-300 AC1: the runner's SELECTION and ORDERING, without needing a database.

What is pinned here is the part that can be wrong silently: which files are
chosen and in what order. The apply path itself needs a live MySQL and is
covered by the cloudbuild step failing the build (`set -euo pipefail`, and the
ledger write ordered AFTER the apply so a failed migration is never recorded as
done).

🔴 The load-bearing exclusion is `000_baseline.sql`. It is a capture of the
schema as it ALREADY exists -- applying it would attempt to CREATE tables
holding 2050 users and 94244 recall rows. A regression that lets it into the
plan is the most destructive thing this directory can do, so it gets its own
test rather than riding along in an ordering assertion.

⚠️ lexitrail's cloudbuild.yaml has no pytest step, so nothing runs this in CI.
Local/manual gate; wiring a test step is #235's lane.
"""
import subprocess
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[2] / "backend" / "migrations" / "apply.sh"


def _planned_files(tmp_path) -> list:
    """The files the runner would APPLY -- parsed from the plan block only.

    Deliberately not a substring check on the whole output: the runner's
    "nothing to do" message NAMES 000_baseline.sql ("excluded by design"), so
    `"000_baseline" in out` is satisfied by the message SAYING it is excluded.
    That is a use/mention collapse, and it failed exactly that way when this
    test was first written -- the reassuring sentence matched the check for the
    dangerous behaviour.
    """
    out = _plan(tmp_path)
    if "PLAN" not in out:
        return []
    block = out.split("PLAN", 1)[1]
    return [ln.strip() for ln in block.splitlines() if ln.strip().endswith(".sql")]


def _plan(tmp_path) -> str:
    if not RUNNER.is_file():
        pytest.skip(f"runner not in this tree ({RUNNER})")
    r = subprocess.run(
        ["bash", str(RUNNER), "--plan"],
        env={"MIGRATIONS_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"--plan exited {r.returncode}: {r.stderr}"
    return r.stdout


def test_baseline_is_never_planned(tmp_path):
    (tmp_path / "000_baseline.sql").write_text("CREATE TABLE users (email varchar(320));")
    planned = _planned_files(tmp_path)
    assert "000_baseline.sql" not in planned, (
        "issue-300: 000_baseline.sql entered the plan. It is a capture of the "
        "EXISTING schema -- applying it targets tables holding live rows. It "
        "must never be applied.\nplanned: %s" % planned
    )


def test_migrations_are_planned_in_lexical_order(tmp_path):
    (tmp_path / "000_baseline.sql").write_text("-- baseline\n")
    for name in ("010_third.sql", "002_second.sql", "001_first.sql"):
        (tmp_path / name).write_text("SELECT 1;\n")
    order = _planned_files(tmp_path)
    assert order == ["001_first.sql", "002_second.sql", "010_third.sql"], (
        "issue-300: plan order is %s. Lexical order IS apply order, so a "
        "mis-sort applies migrations against a schema that does not yet have "
        "what they assume." % order
    )


def test_non_conforming_filenames_are_ignored(tmp_path):
    """A stray .sql must not be applied just for sharing the directory."""
    (tmp_path / "000_baseline.sql").write_text("-- baseline\n")
    (tmp_path / "001_real.sql").write_text("SELECT 1;\n")
    (tmp_path / "scratch.sql").write_text("DROP TABLE users;\n")
    (tmp_path / "README.md").write_text("not sql\n")
    planned = _planned_files(tmp_path)
    assert "scratch.sql" not in planned, "a non-NNN_ file entered the plan: %s" % planned
    assert "001_real.sql" in planned, "the conforming migration was dropped: %s" % planned


def test_empty_directory_plans_nothing_and_succeeds(tmp_path):
    """The negative control: no migrations is a normal state, not an error."""
    (tmp_path / "000_baseline.sql").write_text("-- baseline\n")
    assert _planned_files(tmp_path) == [], _plan(tmp_path)
