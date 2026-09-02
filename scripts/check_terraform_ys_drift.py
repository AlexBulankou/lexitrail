#!/usr/bin/env python3
"""Has `terraform-ys/` been applied since it was last changed? (lexitrail#299 AC4)

WHY THIS EXISTS
---------------
`terraform-ys/` is merged but not applied. No trigger in this repo covers those
paths and there is no apply automation anywhere in the tree, so an infra change
lands on `main` and stops there. Between 2026-06-30 and 2026-09-02 that swallowed
14 commits, including #164's `startupProbe` and #301/#304's `/readyz` readiness
path -- both live reliability fixes, both merged, neither on the cluster.

Nobody *chose* not to apply. Nobody knew. So the thing to automate is the
noticing, not the applying -- see #299 AC3 for why an unattended apply trigger is
the worst of the available options today (#312: ten live objects are absent from
state and would plan as CREATE).

🔴 THE HARD PART IS THAT THE SOURCE AND THE CLUSTER CAN AGREE BY COINCIDENCE.
On 2026-09-02 the backend's cpu/memory limits in `workloads.tf` matched the
cluster exactly -- not because terraform applied, but because a human ran
`kubectl patch` on 08-29. A spot-check of any field can therefore read clean
while the stack is two months stale. That is why this compares *timestamps of
writes* and never field values: `managedFields` records which manager last wrote
the object, and it cannot be fooled by a coincidence.

WHAT IT COMPARES
----------------
    A = the newest commit touching terraform-ys/ on the compared git ref
    B = the `HashiCorp` field manager's last write to a known live object

    B >= A  -> PASS         terraform has written since the newest source change
    B <  A  -> FAIL         N commits have landed with no apply behind them
    either input unobtainable -> CANNOT-TELL, exit 3, NEVER a pass

EXIT CODES
----------
    0  PASS         applied at or after the newest terraform-ys commit
    1  FAIL         source is ahead of the last apply -- drift is live
    3  CANNOT-TELL  git or the cluster did not answer; the check did not run

🔴 `managedFields` IS STRIPPED FROM `kubectl get -o json` BY DEFAULT. The flag
`--show-managed-fields` is not optional here, and forgetting it produces a
response with no `managedFields` key at all -- which reads exactly like "no
manager has ever written this". Those are opposite facts, so they get opposite
verdicts: an ABSENT `managedFields` key is CANNOT-TELL (the query was wrong),
while a PRESENT list with no `HashiCorp` entry is a genuine FAIL (terraform has
never touched this object). Collapsing the first into the second would make this
alarm on every healthy cluster; collapsing it into PASS would make it blind.

KNOWN LIMIT, STATED SO IT IS NOT REDISCOVERED
---------------------------------------------
`managedFields` records a manager's last *write*. A terraform apply that was a
genuine no-op does not bump the timestamp, so B is a LOWER BOUND on freshness:
this check can report FAIL for a stack that is actually applied and unchanged.
It fails toward alarming, which is the recoverable direction -- a false FAIL gets
chased, a false PASS is what let 14 commits pile up.

WHO RUNS IT
-----------
Manually, today, and that is a real gap rather than a design choice.
`GET /projects/lexitrail/schedules` returns `Unknown project: lexitrail`: the
repo has no ProjectState in the orchestrator and therefore no scheduler at all
(ensemble#9032). The moment that lands this belongs on a daily cron. Until then
it is a lead-cadence step, and this paragraph is here so the next reader knows
the difference between "chose not to schedule it" and "could not".
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime

PASS, FAIL, CANNOT_TELL = 0, 1, 3

TF_MANAGER = "HashiCorp"
DEFAULT_PATH = "terraform-ys/"
DEFAULT_REF = "origin/main"
DEFAULT_NAMESPACE = "lexitrail"
DEFAULT_OBJECT = "deploy/lexitrail-backend"


def _parse_ts(raw: str | None) -> datetime | None:
    """RFC3339 -> aware datetime, or None. Never raises."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def verdict(
    newest_commit_ts: datetime | None,
    manager_ts: datetime | None,
    *,
    commits_behind: int = 0,
    manager_field_present: bool = True,
    cannot_tell_reason: str = "",
) -> tuple[int, str]:
    """The whole decision, as a pure function of two timestamps.

    Split out from the I/O deliberately: every branch below is reachable in a
    test without a cluster, which is the only way the CANNOT-TELL arms get
    exercised at all. An instrument whose failure arms are untestable is one
    whose failure arms are untested.
    """
    if newest_commit_ts is None:
        return (
            CANNOT_TELL,
            f"CANNOT-TELL: could not read the newest commit touching "
            f"{DEFAULT_PATH} -- the check did not run, this is not a pass.",
        )
    if not manager_field_present:
        why = cannot_tell_reason or "the cluster did not answer"
        return (
            CANNOT_TELL,
            f"CANNOT-TELL: {why}. This is NOT the manager being absent -- "
            f"that is a FAIL and reads differently. The check did not run.",
        )
    if manager_ts is None:
        return (
            FAIL,
            f"FAIL: no `{TF_MANAGER}` manager has ever written this object. "
            f"terraform has not applied it -- newest {DEFAULT_PATH} commit is "
            f"{newest_commit_ts.isoformat()}.",
        )
    if manager_ts >= newest_commit_ts:
        return (
            PASS,
            f"PASS: last terraform write {manager_ts.isoformat()} is at or "
            f"after the newest {DEFAULT_PATH} commit "
            f"{newest_commit_ts.isoformat()}.",
        )
    gap_days = (newest_commit_ts - manager_ts).total_seconds() / 86400.0
    return (
        FAIL,
        f"FAIL: {DEFAULT_PATH} is {gap_days:.1f} days ahead of the last "
        f"terraform apply ({commits_behind} commit(s) unapplied). "
        f"last apply {manager_ts.isoformat()}, newest commit "
        f"{newest_commit_ts.isoformat()}. See lexitrail#299 -- and read #312 "
        f"before running `terraform apply`, it is not a safe no-op today.",
    )


def _git_newest(ref: str, path: str) -> tuple[datetime | None, int]:
    """Newest commit time touching `path` on `ref`, and how many are unapplied.

    Returns (None, 0) on any git failure. Deliberately does NOT pipe: a pipeline
    reports the last stage's status, so `git ... | head` would render a dead repo
    as an empty string with rc=0 -- indistinguishable from "no commits".
    """
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cI", ref, "--", path],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None, 0
    if out.returncode != 0:
        return None, 0
    return _parse_ts(out.stdout.strip()), 0


def _git_count_since(ref: str, path: str, since: datetime) -> int:
    try:
        out = subprocess.run(
            ["git", "log", "--format=%H", f"--since={since.isoformat()}",
             ref, "--", path],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    if out.returncode != 0:
        return 0
    return len([ln for ln in out.stdout.splitlines() if ln.strip()])


def _manager_ts(
    namespace: str, obj: str,
) -> tuple[datetime | None, bool, str]:
    """(timestamp, managed_fields_key_present, why_not). See module docstring."""
    try:
        out = subprocess.run(
            ["kubectl", "-n", namespace, "get", obj,
             "--show-managed-fields", "-o", "json"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, False, f"kubectl could not be run ({exc})"
    if out.returncode != 0:
        return None, False, (
            f"kubectl exited {out.returncode} for {namespace}/{obj} "
            f"({(out.stderr or '').strip()[:160]})"
        )
    try:
        meta = json.loads(out.stdout).get("metadata", {})
    except (ValueError, AttributeError):
        return None, False, "kubectl output was not the expected JSON shape"
    if "managedFields" not in meta:
        return None, False, (
            "the response carried no `managedFields` key at all, which is the "
            "query being wrong (--show-managed-fields) rather than the object "
            "being unmanaged"
        )
    times = [
        _parse_ts(f.get("time"))
        for f in meta.get("managedFields") or []
        if isinstance(f, dict) and f.get("manager") == TF_MANAGER
    ]
    times = [t for t in times if t is not None]
    return (max(times) if times else None), True, ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", default=DEFAULT_REF)
    ap.add_argument("--path", default=DEFAULT_PATH)
    ap.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    ap.add_argument("--object", default=DEFAULT_OBJECT)
    args = ap.parse_args(argv)

    newest, _ = _git_newest(args.ref, args.path)
    mts, present, why = _manager_ts(args.namespace, args.object)
    behind = _git_count_since(args.ref, args.path, mts) if (mts and newest) else 0

    code, msg = verdict(
        newest, mts, commits_behind=behind, manager_field_present=present,
        cannot_tell_reason=why,
    )
    print(msg)
    return code


if __name__ == "__main__":
    sys.exit(main())
