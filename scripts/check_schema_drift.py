#!/usr/bin/env python3
"""Does PRODUCTION's schema match what the repo believes? (lexitrail#308)

WHY THIS IS NOT test_schema_baseline_300.py
-------------------------------------------
That test compares `backend/migrations/000_baseline.sql` against
`terraform/schema-tables.sql`. **Both are static files in the repo.** Neither
moves when the database moves, so it catches exactly one thing -- someone
editing one file and not the other -- and is structurally blind to the failure
#300 exists for: a hand-run `ALTER TABLE` on `mysql-0`, which succeeds, leaves
no artifact, and makes both files describe a database that no longer exists.
They go on agreeing with each other, cleanly, forever.

This one asks production.

🔴 WHY IT IS A SCRIPT RATHER THAN THE PROSE RECIPE IT REPLACES
--------------------------------------------------------------
`backend/migrations/README.md` already carries this query, correctly, with a
warning about the exact way it goes wrong. It protected nobody: on 2026-09-02 I
ran it from memory against schema `lexitrail` (the *namespace* name), got zero
rows, and started writing up a defect in the README -- which had said
`lexitraildb` all along, two lines above a warning saying precisely that.

I had the ISSUE open, not the README. **A warning only fires for someone who
opens the file it is in**, and the person about to make this mistake is the one
reconstructing the command from somewhere else.

🔴 ZERO LIVE COLUMNS IS `CANNOT-TELL`, NEVER A COMPARISON
---------------------------------------------------------
This is the whole reason the script exists rather than the recipe. A wrong
schema name is a *valid query against nothing*: no error, no warning, an empty
result. Compared either way it produces a confident wrong answer --

    baseline - live  ->  28 "columns missing from production"   false POSITIVE
    live - baseline  ->  0  "no drift"                          false ALL-CLEAR

-- and the second is a drift check reporting clean because it looked at
nothing, which is the failure this file exists to prevent, reproduced inside
the fix for it. So an empty live set refuses to be compared at all.

EXIT CODES
----------
    0  PASS         live base-table columns == the repo's baseline
    1  FAIL         they differ -- the difference is enumerated, both directions
    3  CANNOT-TELL  the cluster did not answer, or answered with nothing

WHAT IS DELIBERATELY EXCLUDED
-----------------------------
- `daily_recall_stats` -- a VIEW. The baseline parser reads base tables only, so
  including it would report 5 permanent false extras.
- `schema_migrations` -- the migration runner's own ledger, created live by
  `apply.sh` (`CREATE TABLE IF NOT EXISTS`) and correctly absent from the repo's
  schema files. It is infrastructure, not app schema.

Both exclusions are for objects whose absence from the baseline is CORRECT.
Nothing is excluded because it was inconvenient -- see
`test_the_exclusions_cannot_hide_a_real_column`.

⚠️ Column NAMES and inventory only, like the sister test -- not types,
nullability, indexes, or the view body. A type change passes this.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PASS, FAIL, CANNOT_TELL = 0, 1, 3

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "backend" / "migrations" / "000_baseline.sql"

NAMESPACE = "lexitrail"
POD = "mysql-0"
# 🔴 The SCHEMA is `lexitraildb`; the NAMESPACE is `lexitrail`. They differ by
# three characters and only one of them is the one you type all day.
SCHEMA = "lexitraildb"

EXCLUDED_TABLES = ("daily_recall_stats", "schema_migrations")


def cols_from_baseline(path: Path = BASELINE) -> set[str]:
    """Columns from the mysqldump-style CREATE TABLE blocks.

    Same shape as `backend/tests/test_schema_baseline_300.py::_cols_from_baseline`.
    Deliberately duplicated rather than imported: that module is a pytest file
    under `backend/`, and importing it here would drag in the collection-order
    fragility documented in #232 for no benefit.
    """
    cols: set[str] = set()
    for m in re.finditer(r"CREATE TABLE `(\w+)` \((.*?)\n\) ENGINE", path.read_text(), re.S):
        table = m.group(1)
        if table in EXCLUDED_TABLES:
            continue
        for line in m.group(2).split("\n"):
            cm = re.match(r"`(\w+)`\s", line.strip().rstrip(","))
            if cm:
                cols.add(f"{table}.{cm.group(1)}")
    return cols


def _live_cols(namespace: str, pod: str, schema: str) -> tuple[set[str] | None, str]:
    """(columns, why_not). Never raises; an unreadable cluster is not an empty one."""
    try:
        pw = subprocess.run(
            ["kubectl", "-n", namespace, "get", "secret", "mysql-root",
             "-o", "jsonpath={.data.MYSQL_ROOT_PASSWORD}"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"kubectl could not be run ({exc})"
    if pw.returncode != 0 or not pw.stdout.strip():
        return None, f"could not read the mysql-root secret ({pw.stderr.strip()[:160]})"
    import base64
    try:
        password = base64.b64decode(pw.stdout.strip()).decode()
    except Exception as exc:  # noqa: BLE001
        return None, f"the mysql-root secret did not decode ({exc})"

    excl = " ".join(f"AND TABLE_NAME<>'{t}'" for t in EXCLUDED_TABLES)
    sql = (
        f"SELECT CONCAT(TABLE_NAME,'.',COLUMN_NAME) FROM information_schema.COLUMNS "
        f"WHERE TABLE_SCHEMA='{schema}' {excl}"
    )
    try:
        out = subprocess.run(
            ["kubectl", "-n", namespace, "exec", pod, "--",
             "sh", "-c", f"mysql -uroot -p'{password}' -N -B -e \"{sql}\""],
            capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"kubectl exec failed ({exc})"
    if out.returncode != 0:
        return None, f"the query did not run ({out.stderr.strip()[:200]})"
    # stderr carries mysql's password-on-the-command-line warning; that is
    # expected and is NOT suppressed at the call site, so a real error above
    # still reaches the reason string.
    return {ln.strip() for ln in out.stdout.splitlines() if ln.strip()}, ""


def verdict(live: set[str] | None, expected: set[str], why: str = "") -> tuple[int, str]:
    """The whole decision, pure, so every arm is testable without a cluster."""
    if live is None:
        return CANNOT_TELL, f"CANNOT-TELL: {why or 'the cluster did not answer'}."
    if not live:
        return CANNOT_TELL, (
            "CANNOT-TELL: the query succeeded and returned ZERO columns. That is "
            f"a valid query against nothing -- almost certainly the wrong schema "
            f"name (it is '{SCHEMA}', not the namespace '{NAMESPACE}'). Refusing "
            "to compare: an empty live set reads as 'everything is missing' one "
            "way and 'no drift' the other, and both are confidently wrong."
        )
    if not expected:
        return CANNOT_TELL, (
            "CANNOT-TELL: parsed zero columns out of the baseline file -- the "
            "parser, not the database, is the thing that failed."
        )
    only_live = sorted(live - expected)
    only_repo = sorted(expected - live)
    if not only_live and not only_repo:
        return PASS, f"PASS: production matches the baseline ({len(live)} columns)."
    return FAIL, (
        f"FAIL: production and the repo's baseline disagree.\n"
        f"  in LIVE not in baseline ({len(only_live)}): {only_live}\n"
        f"  in baseline not in LIVE ({len(only_repo)}): {only_repo}\n"
        f"A column present live and absent from the repo is the hand-run ALTER "
        f"this check exists for (#308). The reverse means a migration has not "
        f"reached production."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--namespace", default=NAMESPACE)
    ap.add_argument("--pod", default=POD)
    ap.add_argument("--schema", default=SCHEMA)
    args = ap.parse_args(argv)

    live, why = _live_cols(args.namespace, args.pod, args.schema)
    code, msg = verdict(live, cols_from_baseline(), why)
    print(msg)
    return code


if __name__ == "__main__":
    sys.exit(main())
