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

🔴 AND SINCE #547, IT ASKS THE RIGHT SERVER -- WHICH IT PREVIOUSLY DID NOT
--------------------------------------------------------------------------
Until 2026-09-18 this script exec'd `mysql-0` and queried `mysql-0`. That was
correct until the Cloud SQL cutover repointed `svc/mysql` at `app=cloudsql-proxy`
and left the pod running with a full, valid `lexitraildb` that nothing reads.

It did not error. It returned **30 columns and PASS** -- byte-identical in shape
to the verdict it returns from Cloud SQL, which also has 30 columns. That is why
it went unnoticed: the wrong answer and the right answer look the same.

So the guard is on the SERVER THAT ANSWERED (`@@version`), never on the host we
dialled. #547 was caused by a Service selector moving; no host string changed,
and no host-based assertion could have seen it.


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
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

PASS, FAIL, CANNOT_TELL = 0, 1, 3

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "backend" / "migrations" / "000_baseline.sql"

NAMESPACE = "lexitrail"
# 🔴 `POD` is only the machine the mysql CLIENT runs on -- it is NOT the database.
# Before the Cloud SQL cutover those were the same thing and this script exec'd
# `mysql-0` and queried `mysql-0`. They are now different servers (#547):
#
#     svc/mysql  selector app=cloudsql-proxy  -> the proxies -> Cloud SQL  (PRODUCTION)
#     pod mysql-0  label  app=mysql           -> still Running, full valid
#                                                lexitraildb, read by nothing
#
# So the pod is a vehicle and `HOST` is the target. Querying mysql-0 locally
# succeeds, returns real columns, and compares them cleanly -- against a database
# no application has used since the cutover.
POD = "mysql-0"
# Reached from inside the cluster; this is the name the backend itself dials.
HOST = f"mysql.{NAMESPACE}.svc.cluster.local"
# Cloud SQL's root password lives in a different secret than mysql-0's.
SECRET, SECRET_KEY = "backend-secret", "DB_ROOT_PASSWORD"

# Measured 2026-09-18, both reachable from the same pod:
#     via svc/mysql   @@version 8.0.45-google   @@server_id 441002752
#     mysql-0 local   @@version 8.0.46          @@server_id 1
# Cloud SQL suffixes its version; the in-cluster MySQL does not. If Google ever
# drops the suffix this check degrades to CANNOT-TELL, never to a silent PASS --
# which is the direction a schema check is allowed to fail in.
PRODUCTION_VERSION_MARKER = "-google"
_IDENT = "##IDENT##"
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


def is_production_server(ident: str | None) -> tuple[bool, str]:
    """Pure: does this server identity belong to PRODUCTION? (#547 AC2)

    Kept separate and pure so the wrong-server arm is testable without a cluster
    -- the arm the script lacked is exactly the one that needs a test, because
    a wrong server returns a populated, comparable, entirely wrong answer.

    Deliberately NOT a host-string check. The host is what we asked for; this is
    what answered. A Service selector can be repointed (which is how #547
    happened) without any string in this file changing.
    """
    if not ident:
        return False, "the server did not report @@version/@@server_id"
    if PRODUCTION_VERSION_MARKER not in ident:
        return False, (
            f"the server that answered reports {ident!r}, which lacks "
            f"{PRODUCTION_VERSION_MARKER!r} -- that is the in-cluster MySQL "
            f"(pre-cutover mysql-0), not Cloud SQL"
        )
    return True, ""



# --- kubectl resolution (#547 follow-up) -----------------------------------
#
# 🔴 The scheduled environment is not the operator's shell. This script hand-ran
# green and returned CANNOT-TELL on its very first SCHEDULED run:
#
#     CANNOT-TELL: kubectl could not be run ([Errno 2] ... 'kubectl').
#
# ⚠️ I do NOT know why, and this comment deliberately does not pretend to. On
# this host `kubectl` is at /usr/bin/kubectl (a symlink into google-cloud-sdk),
# so a PATH containing /usr/bin would have found it -- which means the runner's
# environment is narrower than any shell I can open, or is not this host at all.
# My first diagnosis was "snap dirs are off the cron PATH"; that was WRONG, and
# a stripped-PATH reproduction passed on the UNFIXED code, so it proved nothing.
#
# So this resolver does two separable things, and only the second is certain:
#   1. It tries the locations kubectl plausibly lives in, which FIXES the case
#      where the runner is this host with a narrow PATH.
#   2. It reports every location it tried, which makes the NEXT failure name the
#      environment instead of repeating an error that fits several causes.
#
# ⚠️ The snap path carries a VERSION (`/snap/google-cloud-cli/499/bin`). Pinning
# that literal would work today and break at the next snap refresh -- a recorded
# property of a changing thing -- so it is globbed and the newest is taken.
_KUBECTL_CANDIDATES = (
    "/usr/bin/kubectl",
    "/usr/local/bin/kubectl",
    "/snap/bin/kubectl",
)
_KUBECTL_SNAP_GLOB = "/snap/google-cloud-cli/*/bin/kubectl"


def _snap_revision(path: str) -> int:
    """Snap revision from a path, for ordering. Unparseable sorts oldest.

    🔴 Sorting these as STRINGS is wrong and looks right: reverse-sorted,
    '/snap/google-cloud-cli/499/...' beats '/snap/google-cloud-cli/1002/...'
    because '4' > '1' -- so the resolver would pick an OLD revision, and only
    once two revisions are installed, which is exactly when it matters and not
    when anyone is testing. Caught by the test, not by reading this.
    """
    parts = [p for p in path.split("/") if p.isdigit()]
    return int(parts[-1]) if parts else -1


def resolve_kubectl() -> str | None:
    """Absolute path to a runnable kubectl, or None. Never raises.

    None is a CANNOT-TELL input, never a FAIL: "I could not find the tool" and
    "the schema has drifted" are different facts, and keeping them apart is this
    script's whole three-state discipline. A missing tool reported as drift
    would send someone hunting for schema damage that does not exist.
    """
    found = shutil.which("kubectl")
    if found:
        return found
    for cand in _KUBECTL_CANDIDATES:
        if os.access(cand, os.X_OK):
            return cand
    for cand in sorted(glob.glob(_KUBECTL_SNAP_GLOB),
                       key=_snap_revision, reverse=True):
        if os.access(cand, os.X_OK):
            return cand
    return None


def _kubectl_not_found_msg() -> str:
    """Name what was tried. An error that fits several causes is not evidence."""
    tried = ", ".join(("PATH",) + _KUBECTL_CANDIDATES + (_KUBECTL_SNAP_GLOB,))
    return (f"kubectl was not found (tried: {tried}). This is a MISSING TOOL in "
            "the environment this ran in, NOT a schema finding -- the comparison "
            "did not happen.")


def _live_cols(namespace: str, pod: str, schema: str,
               host: str = HOST) -> tuple[set[str] | None, str, str | None]:
    """(columns, why_not, server_ident). Never raises; an unreadable cluster is not an empty one.

    Identity and columns come back from ONE mysql invocation on purpose: asking
    twice would permit the two answers to come from different servers (svc/mysql
    load-balances across two proxy pods), and an identity check that does not
    cover the measurement it vouches for is decoration.
    """
    kubectl = resolve_kubectl()
    if kubectl is None:
        return None, _kubectl_not_found_msg(), None
    try:
        pw = subprocess.run(
            [kubectl, "-n", namespace, "get", "secret", SECRET,
             "-o", f"jsonpath={{.data.{SECRET_KEY}}}"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"kubectl could not be run ({exc})", None
    if pw.returncode != 0 or not pw.stdout.strip():
        return None, f"could not read the {SECRET} secret ({pw.stderr.strip()[:160]})", None
    import base64
    try:
        password = base64.b64decode(pw.stdout.strip()).decode()
    except Exception as exc:  # noqa: BLE001
        return None, f"the {SECRET} secret did not decode ({exc})", None

    excl = " ".join(f"AND TABLE_NAME<>'{t}'" for t in EXCLUDED_TABLES)
    # Identity first, in the SAME -e batch as the columns (see docstring).
    sql = (
        f"SELECT CONCAT('{_IDENT}',@@version,'|',@@server_id); "
        f"SELECT CONCAT(TABLE_NAME,'.',COLUMN_NAME) FROM information_schema.COLUMNS "
        f"WHERE TABLE_SCHEMA='{schema}' {excl}"
    )
    try:
        out = subprocess.run(
            [kubectl, "-n", namespace, "exec", pod, "--",
             "sh", "-c",
             f"mysql -h {host} -uroot -p'{password}' -N -B -e \"{sql}\""],
            capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"kubectl exec failed ({exc})", None
    if out.returncode != 0:
        return None, f"the query did not run ({out.stderr.strip()[:200]})", None
    # stderr carries mysql's password-on-the-command-line warning; that is
    # expected and is NOT suppressed at the call site, so a real error above
    # still reaches the reason string.
    ident = None
    cols = set()
    for ln in out.stdout.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if ln.startswith(_IDENT):
            ident = ln[len(_IDENT):]
        else:
            cols.add(ln)
    return cols, "", ident


def verdict(live: set[str] | None, expected: set[str], why: str = "",
            ident: str | None = None) -> tuple[int, str]:
    """The whole decision, pure, so every arm is testable without a cluster."""
    if live is None:
        return CANNOT_TELL, f"CANNOT-TELL: {why or 'the cluster did not answer'}."
    # 🔴 #547: BEFORE any comparison. The pre-cutover mysql-0 answers with a
    # populated, well-formed, entirely comparable column set -- so every arm
    # below would produce a confident verdict about the wrong database. This is
    # the one failure the empty-set guard cannot catch, because nothing is empty.
    ok, why_not = is_production_server(ident)
    if not ok:
        return CANNOT_TELL, (
            f"CANNOT-TELL: refusing to compare -- {why_not}. Got "
            f"{len(live)} columns, and they may well be internally consistent; "
            f"that is precisely the problem. Since the Cloud SQL cutover, "
            f"`kubectl exec mysql-0 -- mysql` reaches a live, valid, "
            f"DECOMMISSIONED database (#547)."
        )
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
    ap.add_argument("--host", default=HOST,
                    help="what the mysql client CONNECTS TO (not where it runs)")
    args = ap.parse_args(argv)

    live, why, ident = _live_cols(args.namespace, args.pod, args.schema, args.host)
    added, unparsed = cols_from_migrations()
    if unparsed:
        print("CANNOT-TELL: these migrations contain DDL this script cannot "
              f"account for, so the repo's expected schema is unknown: {unparsed}. "
              "Teach cols_from_migrations that statement rather than comparing.")
        return CANNOT_TELL
    code, msg = verdict(live, cols_from_baseline() | added, why, ident)
    if ident:
        print(f"[server] {ident}")
    print(msg)
    return code


if __name__ == "__main__":
    sys.exit(main())
