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


# issue-308 follow-up: the baseline alone is not what the repo believes.
# `000_baseline.sql` is a fixed historical capture and is never applied; the
# repo's belief is baseline PLUS every migration since. Before this, the first
# additive migration would have made a correctly-migrated column read as
# "present live and absent from the repo" -- the message this script prints for
# a hand-run ALTER. The detector would have accused us of exactly the defect it
# exists to catch, on the first occasion it was used properly.
#
# `001_strip_trailing_cr.sql` never exposed it: it is DML and changes no schema.
_ADD_COLUMN_RE = re.compile(
    r"ALTER\s+TABLE\s+`?(\w+)`?\s+ADD\s+COLUMN\s+`?(\w+)`?", re.I)
# Any other DDL verb means this parser does not know what the file did.
_DDL_RE = re.compile(
    r"\b(ALTER\s+TABLE|CREATE\s+TABLE|DROP\s+TABLE|RENAME\s+TABLE)\b", re.I)


def _strip_sql_comments(sql: str) -> str:
    """Remove `-- line` and `/* block */` comments before matching DDL verbs.

    🔴 SINGLE PASS, because NEITHER regex ORDER is correct (hc2@, reviewing this
    PR). Two sequential `re.sub`s always eat real DDL on one of two mirrored
    inputs, and which one depends only on which you run first:

        block-then-line   `-- see the /* directory`   the stray `/*` opens a
                          ALTER ...                   block running to the next
                          `/* trailing */`            `*/`, eating the ALTER

        line-then-block   `/* note -- see below */`   the `--` strip removes the
                          ALTER ...                   closing `*/`, so the orphaned
                          `/* another */`             `/*` runs to the NEXT one,
                                                      eating the ALTER

    Both measured. The second needs a LATER `*/` to trigger, which is why a
    minimal two-line fixture makes line-first look correct -- it was the fixture
    that was safe, not the order.

    ⚠️ And the failure is SILENT, not CANNOT-TELL: with the ALTER eaten,
    `len(_DDL_RE.findall(text)) == len(adds) == 0`, so the file is not flagged
    unparsed either. The column vanishes from `expected` and then reports as
    "present live and absent from the repo" -- this script's own message for a
    hand-run ALTER, which is the exact thing it exists to detect.

    So: scan once, and let whichever delimiter opens FIRST win. Inside a line
    comment `/*` is inert; inside a block comment `--` is inert. That is what "a
    comment" means, and no ordering of two independent passes can express it.

    Single-quoted string literals are honoured for the same reason: a `'--'` in a
    DEFAULT would otherwise blank the rest of the line and hide real DDL after
    it. Backtick identifiers need no case of their own -- they cannot carry a
    comment opener in any migration this repo will accept.
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'":                        # string literal -- copy verbatim
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":    # '' escape
                        j += 2
                        continue
                    break
                j += 1
            out.append(sql[i:min(j + 1, n)])
            i = j + 1
        elif sql.startswith("--", i):        # line comment -> end of line
            j = sql.find(chr(10), i)
            j = n if j == -1 else j
            out.append(" ")
            i = j
        elif sql.startswith("/*", i):        # block comment -> closing */
            j = sql.find("*/", i + 2)
            out.append(" ")
            i = n if j == -1 else j + 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def cols_from_migrations(dirpath: Path | None = None
                         ) -> tuple[set[str], list[str]]:
    """(columns added by migrations, files this parser could not account for).

    🔴 The second element is the point. A migration whose DDL this regex does
    not understand must NOT silently contribute nothing -- that would shrink
    `expected` and print a confident FAIL naming a column the repo does know
    about. An unparsed file is a CANNOT-TELL, exactly as an unreadable cluster
    is, and for the same reason: not-looking must never render as a result.

    Scoped to `ADD COLUMN` on purpose. This directory is for ADDITIVE changes
    (see its README), so that is the whole vocabulary today; anything else is
    reported rather than guessed at.
    """
    d = dirpath or (ROOT / "backend" / "migrations")
    cols: set[str] = set()
    unparsed: list[str] = []
    for f in sorted(d.glob("[0-9][0-9][0-9]_*.sql")):
        if f.name.startswith("000_baseline"):
            continue          # the point migrations run FROM; never applied
        text = _strip_sql_comments(f.read_text())
        adds = _ADD_COLUMN_RE.findall(text)
        for table, col in adds:
            if table not in EXCLUDED_TABLES:
                cols.add(f"{table}.{col}")
        # Every DDL statement in the file must be one this parser consumed.
        if len(_DDL_RE.findall(text)) != len(adds):
            unparsed.append(f.name)
    return cols, unparsed


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
    added, unparsed = cols_from_migrations()
    if unparsed:
        print("CANNOT-TELL: these migrations contain DDL this script cannot "
              f"account for, so the repo's expected schema is unknown: {unparsed}. "
              "Teach cols_from_migrations that statement rather than comparing.")
        return CANNOT_TELL
    code, msg = verdict(live, cols_from_baseline() | added, why)
    print(msg)
    return code


if __name__ == "__main__":
    sys.exit(main())
