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
kubectl --context="$CTX" -n "$NS" set image "deployment/$DEPLOY" "$CONTAINER=$REF" || die "set image failed"
kubectl --context="$CTX" -n "$NS" rollout status "deployment/$DEPLOY" --timeout=300s || \
  die "rollout did not complete"

# Assert the cluster ended up with EXACTLY what we pushed. cloudbuild-ui.yaml checks this and it is
# the difference between "the command succeeded" and "the right thing is running".
LIVE="$(kubectl --context="$CTX" -n "$NS" get deploy "$DEPLOY" \
        -o jsonpath='{.spec.template.spec.containers[0].image}')"
[ "$LIVE" = "$REF" ] || die "DEPLOY-FAIL: live spec is $LIVE, we pushed $REF"
echo "   live spec matches"

step "smoke (served content, 3 attempts)"
for i in 1 2 3; do
  if python3 scripts/smoke_served_content.py; then echo "✅ deployed $SHA and smoke passed"; exit 0; fi
  echo "   smoke attempt $i failed" >&2
  [ "$i" = 3 ] || sleep 10
done
die "smoke FAILED after 3 attempts — the rollout landed but the site is not serving what we expect"
