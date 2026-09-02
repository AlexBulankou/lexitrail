#!/usr/bin/env python3
"""Is production built from the newest commit that should have deployed it? (#273)

WHY
---
On lexitrail, merging while the build budget is at margin 0 **does not red main --
it silently does not deploy.** The merge succeeds, the PR closes, the checks are
green, and the artifact never moves. The deploy trigger's quota gate declines
minutes later, in a different system, under the status word `FAILURE`, which
reads like a broken build rather than a declined one.

Alex's P1 #265 fix sat merged-but-not-live for ~75 minutes that way and was found
only because someone happened to look at a pod's image digest for an unrelated
reason. The merges were correct; what was missing was anything that says *main is
ahead of production*.

WHAT IT COMPARES
----------------
    A = newest commit touching ui/** (or backend/**) on the compared ref
    B = the sha the live artifact reports at its own /version endpoint

🔴 A IS NOT `git rev-parse origin/main`. Most commits here touch neither path --
docs, sprint files, scripts -- and trigger no build, so comparing against main's
HEAD would report drift permanently and be muted within a week. An alarm that
fires on its own baseline is worse than no alarm. The right-hand side is the
newest commit on the path that *would have* triggered that surface's deploy.

🔴 AND B IS A REPORTED SHA, NOT A GREP. The rejected alternative was to grep the
served bytes for a string a recent commit introduced. That works only when a
commit happens to add a distinctive literal; a commit that changes a constant,
reorders logic, or edits a template adds nothing greppable and the check returns
"current" for a stale artifact. It fails in the *reassuring* direction, which is
the same shape as the silent no-deploy it exists to catch. `/version` is the
step-1 that makes step 2 trivial, and it is why both Dockerfiles now bake the sha.

EXIT CODES
----------
    0  PASS         every checked surface reports the newest commit for its path
    1  FAIL         a surface is behind -- main is ahead of production
    3  CANNOT-TELL  a surface did not answer, or answered `known: false`

🔴 `known: false` IS CANNOT-TELL, NOT PASS AND NOT FAIL. It means the running
image predates this check or was built by hand with no `--build-arg`, so it has
no opinion about which commit it is. Reading that as PASS makes the detector
blind for exactly as long as an old image keeps running -- which is the whole
failure mode. Reading it as FAIL makes it alarm through every rollout of a
pre-#273 image and get muted. It is a third thing and it says so.

WHY NO CREDENTIALS
------------------
Every credential on bp is `PERMISSION_DENIED` against lexitrail's Artifact
Registry AND its Cloud Build list (#224) -- measured across hermes-automation,
familylore-sa and ensemble-sa. So a detector built on "compare the deployed image
tag to the newest build" is not implementable from any agent seat that exists.
Two unauthenticated HTTP GETs are, from anywhere, CI included.

CONTROL
-------
AC4 asks that this go non-zero on a deliberately stale reference, because an
"all current" reading from an instrument that cannot say otherwise is worthless:

    python3 scripts/check_deploy_current.py --ref <a-sha-from-last-week>

That resolves an older newest-commit-per-path and must FAIL. If it does not, this
script is not reading what it claims to read.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request

PASS, FAIL, CANNOT_TELL = 0, 1, 3

SURFACES = {
    "ui": ("https://lexitrail.com/version.json", "ui/"),
    "backend": ("https://api.lexitrail.com/version", "backend/"),
}


def newest_sha(ref: str, path: str) -> str | None:
    """Short sha of the newest commit touching `path` on `ref`, or None.

    No pipe: a pipeline reports the last stage's status, so `git log ... | head`
    renders a bad ref as an empty string with rc=0 -- indistinguishable from "no
    commits ever touched this path", which is a different fact.
    """
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%h", "--abbrev=7", ref, "--", path],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def resolve_full(sha: str) -> tuple[str | None, str]:
    """Full 40-char sha for an abbreviation, or (None, why).

    🔴 Why not compare abbreviations directly. `git log --abbrev=7` is a MINIMUM,
    not a width: git extends the abbreviation when 7 characters are ambiguous in
    the repo. So the two sides can legitimately differ in length -- and the case
    where they differ is exactly the case where two commits share the first 7
    characters, which is the case where a prefix comparison silently reports a
    match between different commits. The tolerance and the hazard have the same
    trigger, so tolerating the length is the wrong move.

    `git rev-parse --verify <sha>^{commit}` resolves it and FAILS on ambiguity,
    which is the honest third answer rather than a coin flip. Raised by hc2 in
    review on #314, who read the prefix compare as defensive-only; it was, and
    the defense was the bug.

    Measured here first rather than assumed: at 445 objects this repo returns
    exactly 7 for --abbrev=7 today, so this is about the mechanism, not a
    reproduction.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git could not be run ({exc})"
    if out.returncode != 0 or not out.stdout.strip():
        return None, (
            f"{sha!r} does not resolve to a unique commit in this clone -- it is "
            f"either ambiguous or not fetched here"
        )
    return out.stdout.strip(), ""


def fetch_version(url: str, timeout: int = 15) -> tuple[str | None, bool | None, str]:
    """(sha, known, why_not). `known is None` means the surface did not answer."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            if r.status != 200:
                return None, None, f"{url} returned HTTP {r.status}"
            body = r.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None, None, (
                f"{url} is 404 -- the running artifact predates issue-273 and "
                f"carries no /version at all"
            )
        return None, None, f"{url} returned HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 -- any transport failure is cannot-tell
        return None, None, f"{url} did not answer ({exc})"
    try:
        doc = json.loads(body)
    except ValueError:
        return None, None, f"{url} did not return JSON"
    if not isinstance(doc, dict):
        return None, None, f"{url} returned JSON that is not an object"
    return doc.get("sha"), bool(doc.get("known")), ""


def _is_ancestor(older: str, newer: str) -> bool:
    """True if `older` is an ancestor of `newer` — i.e. main really is ahead.

    Used only to pick which FAIL message to print. Both branches are a FAIL;
    getting this wrong sends the reader after the wrong cause, not after
    nothing. On any git failure it returns True, which selects the
    main-is-ahead wording — the overwhelmingly common case in practice, and
    the one whose remedy (check for a refusal) is harmless if wrong.
    """
    try:
        out = subprocess.run(
            ["git", "merge-base", "--is-ancestor", older, newer],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    return out.returncode == 0


def verdict_for(
    name: str, expected: str | None, sha: str | None, known: bool | None, why: str,
) -> tuple[int, str]:
    if expected is None:
        return CANNOT_TELL, (
            f"CANNOT-TELL [{name}]: could not resolve the newest commit for its "
            f"path -- the check did not run, this is not a pass."
        )
    if known is None:
        return CANNOT_TELL, f"CANNOT-TELL [{name}]: {why}."
    if not known:
        return CANNOT_TELL, (
            f"CANNOT-TELL [{name}]: the live artifact reports known=false -- it "
            f"was built without a BUILD_SHA and has no opinion about which "
            f"commit it is. Not a pass: it cannot confirm it is current."
        )
    if not isinstance(sha, str) or not sha.strip():
        return CANNOT_TELL, (
            f"CANNOT-TELL [{name}]: known=true but no sha came back -- the "
            f"endpoint contradicts itself."
        )
    live = sha.strip()
    # Full shas by the time they get here -- see resolve_full(). No prefix
    # comparison: it would report a match between two commits sharing a prefix,
    # in exactly the situation that makes the lengths differ in the first place.
    if live == expected:
        return PASS, (
            f"PASS [{name}]: live {live[:8]} == newest commit {expected[:8]}."
        )
    # 🔴 TWO DIRECTIONS, and they have different causes and different fixes.
    # The first version of this message said "main is AHEAD of production"
    # unconditionally -- found by running AC4's control, which deliberately
    # compares against an OLDER ref and therefore produces the other direction.
    # A reader told "main is ahead" when production is ahead goes looking for a
    # refused deploy that never happened.
    if _is_ancestor(live, expected):
        return FAIL, (
            f"FAIL [{name}]: main is AHEAD of production. live {live[:8]}, "
            f"newest commit for its path {expected[:8]}. A merge at "
            f"build-budget margin 0 does not red main -- check whether the "
            f"deploy trigger was REFUSED (used_before == used_after in the "
            f"gate's JSON) rather than failed. See #273."
        )
    return FAIL, (
        f"FAIL [{name}]: production is running something this ref does not "
        f"know about. live {live[:8]}, newest commit for its path "
        f"{expected[:8]}. Most likely your clone is behind origin (fetch and "
        f"re-run) or --ref points at an older commit; a deploy from a branch "
        f"would also land here. This is NOT the refused-deploy case."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", default="origin/main",
                    help="git ref to resolve the newest commit against; pass an "
                         "older sha to run the AC4 control")
    ap.add_argument("--surface", choices=sorted(SURFACES), action="append",
                    help="limit to one surface (repeatable); default: all")
    args = ap.parse_args(argv)

    wanted = args.surface or sorted(SURFACES)
    codes: list[int] = []
    for name in wanted:
        url, path = SURFACES[name]
        expected = newest_sha(args.ref, path)
        if expected is not None:
            expected, why_exp = resolve_full(expected)
            if expected is None:
                print(f"CANNOT-TELL [{name}]: newest commit {why_exp}.")
                codes.append(CANNOT_TELL)
                continue
        sha, known, why = fetch_version(url)
        if known and isinstance(sha, str) and sha.strip():
            full, why_live = resolve_full(sha.strip())
            if full is None:
                print(f"CANNOT-TELL [{name}]: the live sha {why_live}.")
                codes.append(CANNOT_TELL)
                continue
            sha = full
        code, msg = verdict_for(name, expected, sha, known, why)
        print(msg)
        codes.append(code)

    # A FAIL anywhere is a FAIL. Otherwise a CANNOT-TELL anywhere is CANNOT-TELL:
    # a surface we could not read must never be rescued by a sibling that passed.
    if FAIL in codes:
        return FAIL
    if CANNOT_TELL in codes:
        return CANNOT_TELL
    return PASS


if __name__ == "__main__":
    sys.exit(main())
