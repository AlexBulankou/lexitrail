#!/usr/bin/env bash
# issue-300: apply pending additive migrations to the live lexitraildb.
#
# WHY THIS SHAPE — the two things that constrain it, both measured:
#
#   1. It is NOT a terraform resource. `terraform-ys/` has no apply automation
#      (#299) and a plan there produces 13 actions, 12 of them state-drift
#      creates against objects that already exist, so an apply ABORTS before
#      reaching any real change (gated on the state import, my-hermes#1338).
#      A migration Job declared there would never run.
#
#   2. It runs ONCE per deploy, from the pipeline -- not from the app's
#      entrypoint. The backend runs TWO replicas, so entrypoint migrations
#      race. The usual objection to a pipeline step ("it skips environments
#      the pipeline doesn't touch") was measured away: there is exactly one
#      namespace, one MySQL StatefulSet, and backend/app/config.py connects to
#      it by in-cluster DNS. Reversal condition: if a second environment or a
#      non-cluster database appears, this becomes unsafe on exactly that axis
#      and the runner must move into the image with a lock.
#
# 🔴 000_baseline.sql IS NEVER APPLIED. It is a capture of the schema as it
# already exists -- running it would attempt to CREATE tables holding 2050
# users and 94244 recall rows. It is the point 001 migrates FROM.
#
# Usage:
#   apply.sh --plan     print what WOULD be applied, touch nothing (no cluster
#                       access needed beyond reading this directory)
#   apply.sh            apply pending migrations, in order, then record them
set -euo pipefail

NS="${MIGRATIONS_NS:-lexitrail}"
POD="${MIGRATIONS_POD:-mysql-0}"
DB="${MIGRATIONS_DB:-lexitraildb}"   # NOT `lexitrail` -- see README
DIR="${MIGRATIONS_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
PLAN_ONLY=0
[ "${1:-}" = "--plan" ] && PLAN_ONLY=1

# --- candidate set -----------------------------------------------------------
# Lexical order IS the apply order, so the NNN_ prefix is load-bearing.
# `LC_ALL=C` because a locale-dependent sort is how you get two orderings that
# disagree without either looking wrong.
mapfile -t CANDIDATES < <(
  find "$DIR" -maxdepth 1 -name '[0-9][0-9][0-9]_*.sql' -printf '%f\n' \
    | grep -v '^000_baseline\.sql$' \
    | LC_ALL=C sort
)

if [ "${#CANDIDATES[@]}" -eq 0 ]; then
  echo "no migrations to consider in $DIR (000_baseline.sql is excluded by design)"
  [ "$PLAN_ONLY" -eq 1 ] && exit 0
fi

if [ "$PLAN_ONLY" -eq 1 ]; then
  echo "PLAN — would apply, in this order:"
  for f in "${CANDIDATES[@]}"; do echo "  $f"; done
  exit 0
fi

# --- everything below needs the cluster --------------------------------------
PW="$(kubectl -n "$NS" get secret mysql-root -o jsonpath='{.data.MYSQL_ROOT_PASSWORD}' | base64 -d)"
mysql_q() { kubectl -n "$NS" exec -i "$POD" -- mysql -uroot -p"$PW" -N -B "$DB" -e "$1"; }

# The ledger. Without it a re-run re-applies everything, and "additive" stops
# meaning anything the second time.
mysql_q "CREATE TABLE IF NOT EXISTS schema_migrations (
           version     VARCHAR(255) NOT NULL PRIMARY KEY,
           applied_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
         )" >/dev/null

APPLIED_ANY=0
for f in "${CANDIDATES[@]}"; do
  already="$(mysql_q "SELECT COUNT(*) FROM schema_migrations WHERE version='$f'")"
  if [ "$already" != "0" ]; then
    echo "skip    $f (already applied)"
    continue
  fi
  echo "apply   $f"
  # 🔴 No `|| true`, and the ledger write is AFTER the apply on purpose: a
  # migration that fails must fail the BUILD, not be silently recorded as done.
  # `set -e` plus this ordering is the whole guarantee.
  kubectl -n "$NS" exec -i "$POD" -- mysql -uroot -p"$PW" "$DB" < "$DIR/$f"
  mysql_q "INSERT INTO schema_migrations (version) VALUES ('$f')" >/dev/null
  echo "ok      $f"
  APPLIED_ANY=1
done

[ "$APPLIED_ANY" -eq 0 ] && echo "nothing pending — schema already at head"
echo "migrations: done"
