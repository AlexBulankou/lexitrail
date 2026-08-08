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
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

REPO = "AlexBulankou/lexitrail"
# Anchored to THIS FILE, never to the cwd. The poll runs from a cron whose
# working directory is the *my-hermes* clone (`workspace or project.repo_root`
# in the orchestrator), not this repo -- so a relative "ui/" resolved to a
# directory that does not exist and `builds submit` could never have worked
# from the scheduled path. It worked by hand only because a human happens to
# run it from the repo root. tools/cd/poll_deploy.py -> parents[2] == repo root.
UI_DIR = str(Path(__file__).resolve().parents[2] / "ui")
NAMESPACE = "lexitrail"
DEPLOYMENT = "lexitrail-ui-deployment"
# The cluster this deployment lives on is in a DIFFERENT project than the builds
# (`yojowa-claw`, not `lexitrail`) — which is why "we were granted roles on
# lexitrail" says nothing on its own about whether the patch is authorized. See
# `_k8s` for the credential that actually reaches it.
CLUSTER = "ys-autopilot"
CLUSTER_REGION = "us-central1"
CLUSTER_PROJECT = "yojowa-claw"
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


# --------------------------------------------------------------------------
# Kubernetes access — REST, not kubectl
#
# `kubectl` is NOT installed in the orchestrator pod this runs from, and neither
# is `gke-gcloud-auth-plugin`. That is not a temporary gap to wait out: adding a
# binary to that image is a change to a container this repo does not own.
#
# It is also unnecessary. Measured from the pod, same Deployment object, the two
# credentials available there differ:
#
#     in-cluster SA (system:serviceaccount:orch:orch-sa)  -> HTTP 403 Forbidden
#     GCP identity  (gcloud auth print-access-token)      -> HTTP 200
#
# GKE accepts a Google OAuth token as a bearer token directly, so the three calls
# this module needs (get / patch / await-rollout) are plain REST against the
# cluster endpoint. `curl` is already a hard dependency here (`_fetch_served_asset`),
# so this adds no new tool to the pod at all.
#
# TLS is VERIFIED against the cluster's own CA rather than passed `-k`. This patches
# a public site's production deployment; disabling certificate verification on that
# path to save one API call would be trading a real guarantee for convenience.
# --------------------------------------------------------------------------

_CLUSTER_CACHE: dict[str, str] = {}


def _cluster_endpoint_and_ca() -> Optional[tuple[str, str]]:
    """(endpoint, path-to-CA-file) for the cluster, or None if it cannot be read."""
    if "endpoint" in _CLUSTER_CACHE:
        return _CLUSTER_CACHE["endpoint"], _CLUSTER_CACHE["ca"]
    describe = ["gcloud", "container", "clusters", "describe", CLUSTER,
                "--region", CLUSTER_REGION, "--project", CLUSTER_PROJECT, "--format"]
    ep = _run(describe + ["value(endpoint)"], timeout=120)
    ca = _run(describe + ["value(masterAuth.clusterCaCertificate)"], timeout=120)
    if ep.returncode != 0 or ca.returncode != 0:
        return None
    endpoint, ca_b64 = ep.stdout.strip(), ca.stdout.strip()
    if not endpoint or not ca_b64:
        return None
    fd, ca_path = tempfile.mkstemp(prefix="lexitrail-cluster-ca-", suffix=".crt")
    try:
        os.write(fd, base64.b64decode(ca_b64))
    finally:
        os.close(fd)
    _CLUSTER_CACHE["endpoint"], _CLUSTER_CACHE["ca"] = endpoint, ca_path
    return endpoint, ca_path


def parse_http_response(raw: str) -> tuple[Optional[int], str]:
    """Split `<body><STATUS>` (curl `-w %{http_code}`) into (status, body).

    The status is written LAST, after the body, so a body that itself ends in
    digits cannot be mistaken for it -- curl appends exactly three characters.
    A response we cannot parse yields `(None, raw)`: an unreadable reply is not a
    status we can act on, and returning a plausible-looking 0 or 200 here is the
    exact conflation this module exists to avoid.
    """
    if len(raw) < 3 or not raw[-3:].isdigit():
        return None, raw
    return int(raw[-3:]), raw[:-3]


def _k8s(method: str, path: str, body: Optional[str] = None,
         content_type: Optional[str] = None, timeout: int = 300):
    """One authenticated REST call to the cluster. Returns (status, body-text).

    (None, "") means the call could not be MADE -- no endpoint, no token, curl
    failed -- which is a different fact from "the server said no", and callers
    must not collapse the two.
    """
    target = _cluster_endpoint_and_ca()
    if target is None:
        return None, ""
    endpoint, ca_path = target
    token = _run(["gcloud", "auth", "print-access-token"], timeout=120)
    if token.returncode != 0 or not token.stdout.strip():
        return None, ""
    cmd = ["curl", "-s", "-w", "%{http_code}", "--cacert", ca_path,
           "-X", method,
           "-H", f"Authorization: Bearer {token.stdout.strip()}"]
    if content_type:
        cmd += ["-H", f"Content-Type: {content_type}"]
    if body is not None:
        cmd += ["-d", body]
    cmd.append(f"https://{endpoint}{path}")
    r = _run(cmd, timeout=timeout)
    if r.returncode != 0:
        return None, ""
    return parse_http_response(r.stdout)


def _deployment_path() -> str:
    return f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments/{DEPLOYMENT}"


def head_sha() -> Optional[str]:
    r = _run(["gh", "api", f"repos/{REPO}/commits/main", "--jq", ".sha"], timeout=120)
    return r.stdout.strip() or None if r.returncode == 0 else None


def extract_source_sha(deployment_json: str) -> Optional[str]:
    r"""Pull the source-sha annotation out of a Deployment JSON payload.

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
    status, body = _k8s("GET", _deployment_path(), timeout=120)
    return extract_source_sha(body) if status == 200 else None


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
    # `--dry-run` returns HERE, before any mutation -- there is deliberately no
    # second dry-run gate inside `_deploy_and_verify` (hc2@ Q1 on PR #79). A
    # `dry_run` parameter that the body never reads is worse than none: the name
    # promises the mutations are skipped, and in a function that runs
    # `gcloud builds submit` + a live Deployment patch against production, that promise
    # would be believed by whoever next wires this to a cron or a CLI flag.
    return EXIT_OK if args.dry_run else _deploy_and_verify(head)


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


def newest_successful_build(stdout: str) -> tuple[Optional[str], Optional[str]]:
    """Parse `value(id,results.images[0].digest)` into (build_id, digest).

    Split on TAB, not whitespace: gcloud's `value()` format is tab-separated, and a
    space-split would silently merge or mis-slice a field that ever contains one.
    A row missing either half returns None for that half rather than a truncated
    string, so the caller's `startswith("sha256:")` guard has something real to reject.
    """
    line = stdout.strip().splitlines()[0].strip() if stdout.strip() else ""
    if not line:
        return None, None
    parts = line.split("\t")
    build_id = parts[0].strip() or None
    digest = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    return build_id, digest


def _query_newest_successful_build() -> tuple[Optional[str], Optional[str]]:
    """(build_id, digest) for the most recent SUCCESS build in this project.

    This replaces an `artifacts docker images list` tag->digest lookup, which the
    orchestrator's identity is NOT permitted to make (`artifactregistry.repositories.get`
    is denied) — while Cloud Build, which it IS permitted to read, already records the
    digest of the image it produced. Same fact, from the surface we can reach.
    """
    r = _run(["gcloud", "builds", "list", "--project", PROJECT, "--region", REGION,
              "--filter", "status=SUCCESS", "--sort-by", "~createTime", "--limit", "1",
              "--format", "value(id,results.images[0].digest)"], timeout=300)
    if r.returncode != 0:
        return None, None
    return newest_successful_build(r.stdout)


def rollout_complete(deployment_json: str) -> Optional[bool]:
    """Has the CURRENT generation finished rolling out? None = cannot tell.

    Three states on purpose, mirroring the rest of this module. `None` means the
    payload was unreadable or did not carry the fields, which is NOT "not yet" —
    treating an unparseable reply as "still rolling" would spin until timeout and
    then report a rollout failure that never happened.

    `observedGeneration < generation` is checked FIRST and separately: immediately
    after a patch the status block still describes the PREVIOUS generation, and every
    replica count in it will look perfectly healthy. Reading those counts without the
    generation guard reports success for the deployment we just replaced.
    """
    try:
        doc = json.loads(deployment_json)
    except (ValueError, TypeError):
        return None
    if not isinstance(doc, dict):
        return None
    meta, spec, status = doc.get("metadata"), doc.get("spec"), doc.get("status")
    if not all(isinstance(x, dict) for x in (meta, spec, status)):
        return None
    generation, observed = meta.get("generation"), status.get("observedGeneration")
    if not isinstance(generation, int) or not isinstance(observed, int):
        return None
    if observed < generation:
        return False
    desired = spec.get("replicas", 1)
    return (status.get("updatedReplicas") == desired
            and status.get("availableReplicas") == desired
            and status.get("replicas") == desired)


def _await_rollout(timeout_s: int = 300, interval_s: int = 5) -> Optional[bool]:
    """Poll until the current generation is rolled out. None = never established."""
    deadline = time.monotonic() + timeout_s
    last: Optional[bool] = None
    while time.monotonic() < deadline:
        code, body = _k8s("GET", _deployment_path(), timeout=60)
        last = rollout_complete(body) if code == 200 else None
        if last is True:
            return True
        time.sleep(interval_s)
    # False (still rolling at the deadline) and None (never got a readable answer)
    # are different failures and are returned as different values.
    return last


def _deploy_and_verify(head: str) -> int:
    """Build from main, patch the deployment to the new digest, verify what SERVED.

    Ordering is deliberate and not interchangeable: build -> resolve digest -> patch
    -> re-verify the SERVED asset. The final step is the only one that speaks to
    users; every earlier step can succeed while the site stays broken, which is the
    entire history of #63.
    """
    # Recorded BEFORE the build so the digest lookup below can tell our build's
    # result from the previous one. A timestamp comparison would work most of the
    # time and depends on this pod's clock agreeing with Cloud Build's; an id that
    # changed is a direct observation and depends on nothing.
    before_id, _ = _query_newest_successful_build()

    print(f"[deploy] building {IMAGE}:latest from main ({head[:8]})")
    b = _run(["gcloud", "builds", "submit", "--project", PROJECT, "--region", REGION,
              "--tag", f"{IMAGE}:latest", UI_DIR], timeout=1800)
    if not build_succeeded(b.returncode, b.stdout + b.stderr):
        print(f"[deploy] build FAILED (rc={b.returncode}) -- not patching", file=sys.stderr)
        return EXIT_FAILED

    after_id, sha = _query_newest_successful_build()
    if after_id is None or after_id == before_id:
        # The build reported SUCCESS but the newest success on record is still the
        # one from before it. We cannot say which artifact we would be shipping, so
        # we ship none -- INDETERMINATE, because this is "could not establish",
        # not "known bad".
        print(f"[deploy] newest successful build did not advance (still {before_id!r})"
              " -- refusing to patch", file=sys.stderr)
        return EXIT_INDETERMINATE
    if not (sha or "").startswith("sha256:"):
        # Refuse rather than patch `:latest` -- a tag can move under a running
        # deployment, so a digest is the only reference that means one artifact.
        print(f"[deploy] could not resolve a digest for build {after_id} (got {sha!r})",
              file=sys.stderr)
        return EXIT_INDETERMINATE

    print(f"[deploy] patching {DEPLOYMENT} -> {sha[:19]}… (+source-sha annotation)")
    patch = json.dumps({"spec": {"template": {
        "metadata": {"annotations": {SOURCE_ANNOTATION: head}},
        "spec": {"containers": [{"name": CONTAINER, "image": f"{IMAGE}@{sha}"}]},
    }}})
    code, body = _k8s("PATCH", _deployment_path(), body=patch,
                      content_type="application/strategic-merge-patch+json", timeout=300)
    if code != 200:
        print(f"[deploy] patch FAILED (http={code}): {body.strip()[:200]}", file=sys.stderr)
        return EXIT_FAILED

    rolled = _await_rollout(timeout_s=300)
    if rolled is not True:
        # None means we never got a readable answer -- that is "could not tell",
        # not "it failed", and the exit code has to say which.
        print(f"[deploy] rollout not confirmed (rollout_complete={rolled})", file=sys.stderr)
        return EXIT_FAILED if rolled is False else EXIT_INDETERMINATE

    # ⚠️ `rollout status` reporting success is NOT evidence users see the change --
    # it says pods rolled, which is true even when the image never changed. The
    # served re-check below is the only step that speaks to what shipped.
    served = _fetch_served_asset()
    verdict = classify_served(*served) if served else "indeterminate"
    print(f"[deploy] post-rollout served asset -> {verdict} {served}")
    return _verdict_exit(verdict)


if __name__ == "__main__":
    sys.exit(main())
