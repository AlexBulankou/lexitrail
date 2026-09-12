#!/usr/bin/env bash
# Deploy the LexiTrail UI from bp, with no Cloud Build.
#
# WHY (Alex, 2026-09-11): validation already left Cloud Build for this repo — zero PR-validation
# triggers remain. What stayed was the DEPLOY, and on 2026-09-11 that cost us: the repo's build
# budget is 12/day, two merges (#477, #481) each triggered a deploy, and BOTH were refused on quota
# seconds apart. The PRs read as merged while the live site served 0 of 6 of the pages they added.
# Nothing pages when a deploy is refused, so the work simply sat off production until someone looked.
#
# This is a faithful port of cloudbuild-ui.yaml steps 1-5, minus the quota gate. Same image, same
# tags, same digest-pinned rollout, same smoke test. Modelled on market-mind's
# scripts/deploy_portal_ui.sh, which has deployed that product with zero Cloud Build minutes.
#
#   usage: scripts/deploy_ui_local.sh [--skip-build]
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${LT_UI_IMAGE:-us-central1-docker.pkg.dev/lexitrail/lexitrail-repo/lexitrail-ui}"
CLUSTER="${LT_CLUSTER:-ys-autopilot}"; CLUSTER_REGION="${LT_CLUSTER_REGION:-us-central1}"
CLUSTER_PROJECT="${LT_CLUSTER_PROJECT:-yojowa-claw}"
NS="${LT_NAMESPACE:-lexitrail}"; DEPLOY="${LT_DEPLOYMENT:-lexitrail-ui-deployment}"
CONTAINER="${LT_CONTAINER:-lexitrail-ui}"
MAX_LOAD="${LT_DEPLOY_MAX_LOAD:-20}"
SKIP_BUILD=false; [ "${1:-}" = "--skip-build" ] && SKIP_BUILD=true

die(){ echo "❌ $*" >&2; exit 1; }
step(){ echo "▶ $*"; }

cd "$REPO_ROOT"
SHA="$(git rev-parse --short HEAD)" || die "not a git checkout"
[ -n "$(git status --porcelain)" ] && echo "⚠️  working tree is dirty — deploying $SHA plus uncommitted changes" >&2

load="$(cut -d' ' -f1 /proc/loadavg)"
awk -v l="$load" -v m="$MAX_LOAD" 'BEGIN{exit !(l>m)}' && \
  die "load ${load} over ${MAX_LOAD} — bp is busy; re-run when it settles"
command -v docker >/dev/null && docker info >/dev/null 2>&1 || die "docker not reachable"

if ! $SKIP_BUILD; then
  step "pull cache (best effort)"; docker pull -q "${IMAGE}:latest" >/dev/null 2>&1 || true
  step "build ./ui  (tags: latest, ${SHA})"
  t0=$(date +%s)
  docker build --cache-from "${IMAGE}:latest" -t "${IMAGE}:latest" -t "${IMAGE}:${SHA}" \
    --build-arg "BUILD_SHA=${SHA}" ./ui || die "docker build failed"
  echo "   built in $(( $(date +%s) - t0 ))s"
  step "push"
  docker push -q "${IMAGE}:latest"  || die "push :latest failed"
  docker push -q "${IMAGE}:${SHA}"  || die "push :${SHA} failed"
fi

# Pin the rollout to the DIGEST, not a tag. cloudbuild-ui.yaml does this and it is load-bearing:
# :latest is mutable, so a tag-based rollout can silently deploy something other than what was just
# built if anything else pushes between the two steps.
step "resolve digest"
# Read the digest the REGISTRY reports for what we just pushed. No fallback: if this cannot be
# resolved the correct action is to stop, because the only alternative is rolling out a mutable tag.
# (An earlier draft had a "fallback" here that could only ever evaluate to empty — it failed safe by
# accident, which is not the same as being right, and it would have misled the next reader.)
DIGEST="$(docker inspect --format='{{index .RepoDigests 0}}' "${IMAGE}:${SHA}" 2>/dev/null | cut -d@ -f2)"
[ -n "${DIGEST:-}" ] || die "could not resolve the pushed digest for ${IMAGE}:${SHA} — refusing to roll out on a mutable tag"
REF="${IMAGE}@${DIGEST}"
echo "   $REF"

step "rollout"
CTX="gke_${CLUSTER_PROJECT}_${CLUSTER_REGION}_${CLUSTER}"
kubectl config get-contexts -o name 2>/dev/null | grep -qx "$CTX" || \
  gcloud container clusters get-credentials "$CLUSTER" --region "$CLUSTER_REGION" \
    --project "$CLUSTER_PROJECT" >/dev/null 2>&1 || die "no kube context $CTX and get-credentials failed"
# issue-494 AC3: capture the digest BEFORE `set image`, same as cloudbuild-ui.yaml (#493) and
# cloudbuild.yaml (#494). #494 proposed leaving this file alone on the grounds that it is "a
# hand-run operator path, so the concurrency race is far less likely". BOTH HALVES OF THAT PREMISE
# ARE FALSE, measured:
#
#   1. It is not hand-run. `p/local-ci/lt-deploy-poller.sh:103` invokes it, on every merge (#486).
#   2. It is not the only writer of this deployment. `lexitrail-ui-deploy-main` is ENABLED and
#      fires on `ui/**` + `cloudbuild-ui.yaml`, and it also `set image`s lexitrail-ui-deployment.
#
# The poller's own `flock -n 9` serialises poller-vs-poller and does nothing about poller-vs-Cloud
# Build. So a `ui/**` merge fires BOTH writers and the race is live here exactly as it was there.
PREV="$(kubectl --context="$CTX" -n "$NS" get deploy "$DEPLOY" \
        -o jsonpath='{.spec.template.spec.containers[0].image}')"
kubectl --context="$CTX" -n "$NS" set image "deployment/$DEPLOY" "$CONTAINER=$REF" || die "set image failed"
kubectl --context="$CTX" -n "$NS" rollout status "deployment/$DEPLOY" --timeout=300s || \
  die "rollout did not complete"

# Three facts, three outcomes. The old two-outcome form reported a concurrent build legitimately
# overwriting us as DEPLOY-FAIL, which is a false alarm on a path the poller runs unattended.
LIVE="$(kubectl --context="$CTX" -n "$NS" get deploy "$DEPLOY" \
        -o jsonpath='{.spec.template.spec.containers[0].image}')"
if [ "$LIVE" = "$REF" ]; then
  echo "   live spec matches"
elif [ "$LIVE" = "$PREV" ]; then
  die "DEPLOY-FAIL: live spec is still the PREVIOUS digest ($PREV) -- set image did not take"
else
  # Ours lost a race we did not need to win: the winner is a LATER digest of this same
  # deployment, so main is AHEAD of us, not behind. Dying here would fail an unattended poller
  # run carrying no information about the code.
  echo "   DEPLOY-SUPERSEDED: live spec is $LIVE -- neither what we pushed ($REF) nor the digest"
  echo "   we replaced ($PREV), so a NEWER deploy set it. Superseded, not lost; nothing to re-run."
fi

step "smoke (served content, 3 attempts)"
for i in 1 2 3; do
  if python3 scripts/smoke_served_content.py; then echo "✅ deployed $SHA and smoke passed"; exit 0; fi
  echo "   smoke attempt $i failed" >&2
  [ "$i" = 3 ] || sleep 10
done
die "smoke FAILED after 3 attempts — the rollout landed but the site is not serving what we expect"
