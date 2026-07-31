#!/usr/bin/env python3
"""Poll-based CD for the Lexitrail UI (issue-77).

## Why a poll rather than a push trigger

This project has **no Cloud Build triggers** — none, in either region. Nothing has
ever auto-deployed; every deploy has been a hand-run `gcloud builds submit`. That
is what stranded #63's demo-account leak in production for 3 days with the fix
merged, and it is what re-stranded it after #43 was closed on a manual deploy
without touching the cause.

A GitHub push trigger is the tidier end state, but creating one requires a
**browser OAuth flow** to install the Cloud Build GitHub App (the non-interactive
route needs that App's installation id plus a GitHub *user* token — an App
installation token is a different credential). A poll needs none of that, and
every step of it has been executed by an agent already.

## The failure mode this is designed against

A poll that silently no-ops is worse than no poll, because a green check nobody
questions replaces a gap somebody might have noticed. That is not hypothetical:
`ensemble#7768` had a digest cron report `exit_code=0` for ~2 months while posting
nothing, because its no-op path returned 0.

So this asserts **the served content changed**, never merely that it ran, and it
**exits non-zero when it cannot tell the difference**. `EXIT_INDETERMINATE` exists
specifically so "I could not verify" can never be mistaken for "verified fine" —
they are different facts and they must not share an exit code.

## The 200-that-isn't trap

`GET /images/og/generated/og-landscape.png` returned **HTTP 200** the whole time it
was broken: the SPA catch-all serves `index.html` for unknown paths. Status code
cannot distinguish deployed from missing here. Only content-type and size can, so
`verify_served` keys on those and treats a 200 with the wrong content-type as a
FAILURE rather than a pass.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Optional

REPO = "AlexBulankou/lexitrail"
NAMESPACE = "lexitrail"
DEPLOYMENT = "lexitrail-ui-deployment"
CONTEXT = "gke_yojowa-claw_us-central1_ys-autopilot"
IMAGE = "us-central1-docker.pkg.dev/lexitrail/lexitrail-repo/lexitrail-ui"
# The deployment carries the source commit it was built from, so the poll needs no
# external state file (which could drift from the cluster it describes).
SOURCE_ANNOTATION = "lexitrail.dev/source-sha"

SITE = "https://lexitrail.com"
PROJECT = "lexitrail"
REGION = "us-central1"
CONTAINER = "lexitrail-ui"

EXIT_OK = 0             # nothing to do, or deployed AND verified
EXIT_FAILED = 1         # a step failed outright
EXIT_INDETERMINATE = 3  # could not establish whether the served content is correct

# The asset must be an image. A 200 of text/html is the SPA catch-all, i.e. ABSENT.
EXPECTED_CONTENT_TYPE_PREFIX = "image/"
MIN_PLAUSIBLE_ASSET_BYTES = 10_000


def needs_deploy(head_sha: Optional[str], deployed_sha: Optional[str]) -> bool:
    """True when main has moved past what is deployed.

    An UNKNOWN deployed sha means deploy: the annotation is absent on a deployment
    that predates this tooling, and the safe reading of "I don't know what is
    running" is not "assume it is current". An unknown HEAD is the opposite — it
    means the *query* failed, and deploying on an unknown target is never right.
    """
    if not head_sha:
        return False
    if not deployed_sha:
        return True
    return head_sha != deployed_sha


def classify_served(status: int, content_type: str, size: int) -> str:
    """`ok` | `absent` | `indeterminate` for a fetched asset.

    `absent` is the #63 shape: HTTP 200 carrying `text/html` because the SPA
    catch-all answered for a path that does not exist. Keying on status alone
    reports that as deployed, which is how the leak survived 3 days.
    """
    if status != 200:
        return "absent" if status == 404 else "indeterminate"
    if not content_type.startswith(EXPECTED_CONTENT_TYPE_PREFIX):
        return "absent"
    if size < MIN_PLAUSIBLE_ASSET_BYTES:
        return "indeterminate"
    return "ok"


def _run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def head_sha() -> Optional[str]:
    r = _run(["gh", "api", f"repos/{REPO}/commits/main", "--jq", ".sha"], timeout=120)
    return r.stdout.strip() or None if r.returncode == 0 else None


def extract_source_sha(deployment_json: str) -> Optional[str]:
    r"""Pull the source-sha annotation out of `kubectl get deploy -o json`.

    Deliberately NOT a `-o jsonpath=` expression (hc2@'s review of PR #78). The
    annotation key contains BOTH a dot and a slash, and jsonpath's separator is the
    **dot** -- so the dot needs escaping and the slash does not. I had escaped the
    slash, which silently returns EMPTY for an annotation that exists and is set:

        key.replace('/', r'\/')   -> ''                     (what I shipped)
        key.replace('.', r'\.')   -> '2026-07-22T19:58:42Z'  (correct)

    Verified live against this deployment's own `kubectl.kubernetes.io/restartedAt`,
    same shape. Parsing JSON in Python has no escaping surface at all, so the class
    cannot come back for a future key shape -- and, unlike the jsonpath form, it is a
    pure function this file can actually test.

    Why the bug survived a live run: `deployed=None` was the EXPECTED output that night
    (the annotation genuinely did not exist yet) and is ALSO what the broken escaping
    produces once it does. The check could not distinguish the two facts -- the same
    defect class this module is written against, one layer up in its own tooling.
    """
    try:
        doc = json.loads(deployment_json)
    except (ValueError, TypeError):
        return None
    if not isinstance(doc, dict):
        return None
    annotations = (
        doc.get("spec", {}).get("template", {}).get("metadata", {}).get("annotations")
    )
    if not isinstance(annotations, dict):
        return None
    value = annotations.get(SOURCE_ANNOTATION)
    return value.strip() or None if isinstance(value, str) else None


def deployed_source_sha() -> Optional[str]:
    r = _run([
        "kubectl", "--context", CONTEXT, "-n", NAMESPACE, "get", "deploy", DEPLOYMENT,
        "-o", "json",
    ], timeout=120)
    return extract_source_sha(r.stdout) if r.returncode == 0 else None


def _verdict_exit(verdict: str) -> int:
    """Map a served-asset verdict to an exit code, preserving all three states.

    `absent` is a known-bad state (redeploy); `indeterminate` means the check itself
    could not conclude (investigate). They want different responses, so they must not
    share a code -- that is the whole reason EXIT_INDETERMINATE exists.
    """
    if verdict == "ok":
        return EXIT_OK
    return EXIT_FAILED if verdict == "absent" else EXIT_INDETERMINATE


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Poll-based CD for the Lexitrail UI (issue-77)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would happen; never builds, patches, or mutates")
    ap.add_argument("--verify-only", action="store_true",
                    help="skip build/patch; only assert the served asset is real")
    args = ap.parse_args(argv)

    served = _fetch_served_asset()
    verdict = classify_served(*served) if served else "indeterminate"
    print(f"[verify] served asset -> {verdict} (status/type/size: {served})")

    if args.verify_only:
        return _verdict_exit(verdict)

    head = head_sha()
    deployed = deployed_source_sha()
    print(f"[poll] main={head} deployed={deployed}")
    if head is None:
        print("[poll] could not read main's HEAD -- refusing to act on an unknown target",
              file=sys.stderr)
        return EXIT_INDETERMINATE

    if not needs_deploy(head, deployed):
        print("[poll] up to date; nothing to build")
        # Even with nothing to build, a bad SERVED state is still a failure -- the
        # #63 state was exactly "nothing to deploy" plus "the asset is not there".
        # But keep the three states distinct here too (hc2@'s Q2): collapsing
        # `indeterminate` into FAILED on this branch would contradict the whole point
        # of having a third code, and it is the branch that runs on almost every poll.
        return _verdict_exit(verdict)

    print(f"[poll] main has moved -> deploy needed{' (DRY RUN, stopping here)' if args.dry_run else ''}")
    return EXIT_OK if args.dry_run else _deploy_and_verify(head, dry_run=False)


def _fetch_served_asset():
    """(status, content_type, size) for the og asset, or None if unfetchable."""
    url = f"{SITE}/images/og/generated/og-landscape.png"
    r = _run(["curl", "-s", "-o", "/dev/null",
              "-w", "%{http_code} %{content_type} %{size_download}", url], timeout=120)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    parts = r.stdout.split()
    try:
        return int(parts[0]), parts[1], int(parts[2])
    except (ValueError, IndexError):
        return None


def build_succeeded(returncode: int, stdout: str) -> bool:
    """A build is successful only if gcloud says SUCCESS *and* exits 0.

    Both halves, because they fail independently: `gcloud builds submit` can exit
    non-zero on a transport error after a build that actually succeeded, and --
    the direction that matters -- a wrapper or a `| tee` can hand back 0 while the
    build status text says FAILURE. Requiring the word SUCCESS in the output means
    the exit code alone cannot green-light a deploy.
    """
    return returncode == 0 and "SUCCESS" in stdout.upper()


def _deploy_and_verify(head: str, dry_run: bool = False) -> int:
    """Build from main, patch the deployment to the new digest, verify what SERVED.

    Ordering is deliberate and not interchangeable: build -> resolve digest -> patch
    -> re-verify the SERVED asset. The final step is the only one that speaks to
    users; every earlier step can succeed while the site stays broken, which is the
    entire history of #63.
    """
    print(f"[deploy] building {IMAGE}:latest from main ({head[:8]})")
    b = _run(["gcloud", "builds", "submit", "--project", PROJECT, "--region", REGION,
              "--tag", f"{IMAGE}:latest", "ui/"], timeout=1800)
    if not build_succeeded(b.returncode, b.stdout + b.stderr):
        print(f"[deploy] build FAILED (rc={b.returncode}) -- not patching", file=sys.stderr)
        return EXIT_FAILED

    digest = _run(["gcloud", "artifacts", "docker", "images", "list", IMAGE,
                   "--include-tags", "--filter", "tags:latest",
                   "--format", "value(version)", "--limit", "1"], timeout=300)
    sha = digest.stdout.strip().splitlines()[0].strip() if digest.stdout.strip() else ""
    if not sha.startswith("sha256:"):
        # Refuse rather than patch `:latest` -- a tag can move under a running
        # deployment, so a digest is the only reference that means one artifact.
        print(f"[deploy] could not resolve a digest for :latest (got {sha!r})", file=sys.stderr)
        return EXIT_INDETERMINATE

    print(f"[deploy] patching {DEPLOYMENT} -> {sha[:19]}… (+source-sha annotation)")
    patch = json.dumps({"spec": {"template": {
        "metadata": {"annotations": {SOURCE_ANNOTATION: head}},
        "spec": {"containers": [{"name": CONTAINER, "image": f"{IMAGE}@{sha}"}]},
    }}})
    pr = _run(["kubectl", "--context", CONTEXT, "-n", NAMESPACE, "patch", "deploy",
               DEPLOYMENT, "--type", "strategic", "-p", patch], timeout=300)
    if pr.returncode != 0:
        print(f"[deploy] patch FAILED: {pr.stderr.strip()[:200]}", file=sys.stderr)
        return EXIT_FAILED

    ro = _run(["kubectl", "--context", CONTEXT, "-n", NAMESPACE, "rollout", "status",
               f"deploy/{DEPLOYMENT}", "--timeout=300s"], timeout=400)
    if ro.returncode != 0:
        print(f"[deploy] rollout did not complete: {ro.stderr.strip()[:200]}", file=sys.stderr)
        return EXIT_FAILED

    # ⚠️ `rollout status` reporting success is NOT evidence users see the change --
    # it says pods rolled, which is true even when the image never changed. The
    # served re-check below is the only step that speaks to what shipped.
    served = _fetch_served_asset()
    verdict = classify_served(*served) if served else "indeterminate"
    print(f"[deploy] post-rollout served asset -> {verdict} {served}")
    return _verdict_exit(verdict)


if __name__ == "__main__":
    sys.exit(main())
