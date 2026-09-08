# Lexitrail Cloud SQL cutover runbook (lexitrail#358)

Cut `lexitraildb` from the in-cluster `mysql-0` StatefulSet (spot GKE) to the managed
Cloud SQL instance `lexitrail:us-central1:lexitrail-mysql`, with a short write-freeze
and a config-only rollback.

**Why:** lexitrail#331 — on 2026-09-03 the site was functionally down ~8h because
`mysql-0` was evicted from a spot node with nowhere to reschedule. A stateful DB on
spot capacity is the root cause.

**Sibling:** `CUTOVER-RUNBOOK.md` (my-hermes#905) is the *cluster* re-home. This is a
different cutover and reuses its write-freeze shape deliberately — that runbook is the
proven template, not a coincidence.

🔴 **Rollback here is better than #905's.** Nothing is decommissioned at cutover and
`mysql-0` keeps serving its own data, so rollback is reverting `DATABASE_URL` — a config
change, not a DNS propagation wait.

---

## 0. Roles

- **HCL (agent):** all of it. No operator step — there is no DNS change in this cutover
  (the app keeps its hostnames; only its DB endpoint moves).

## 1. State — what is DONE vs NOT

✅ **Done and verified 2026-09-08:**

| | |
|---|---|
| instance provisioned | `lexitrail-mysql`, `db-f1-micro`, MYSQL_8_0, single-zone, 10GB, `RUNNABLE` (lexitrail#409) |
| `lexitraildb` + `root@%` | created; the root password is the **same value** as the in-cluster `mysql-root` secret, by design (`cloudsql.tf`) |
| seed dump → import | **63 seconds**, `PIPESTATUS: dump=0 sed=0 import=0` |
| verified by exact `COUNT(*)` | all 6 tables + the view identical source↔target |
| Auth Proxy reachability | `cloud_sql_proxy 2.8.0` → `127.0.0.1:3307`, connected as `root@%` |
| the guest-token probe | headless, no browser session needed (see §6) |

🔴 **NOT done — the cutover is BLOCKED on this and it is a separate slice:**

**Connector wiring.** The backend Deployment has `containers = ['lexitrail-backend']` —
no `cloud-sql-proxy` sidecar — and there is no app-scoped DB user. `cloudsql.tf`
deliberately omits the app user ("creating it now would leave an unused grant"). Until
that slice lands, **nothing in the cluster can reach the instance**, which is the
designed security property (`ipv4_enabled` with empty `authorized_networks`), not a gap.

⚠️ **This runbook does not cover writing that slice, and its steps below assume it has
landed.** Do not start §3 before then.

## 2. Pre-flight (same day, before the window)

- [ ] Connector slice merged **and applied**; backend pods show 2 containers.
- [ ] `gcloud sql instances describe lexitrail-mysql --project=lexitrail` → `RUNNABLE`.
- [ ] Re-read the current row counts on **both** sides (they will have moved — see §4).
- [ ] Confirm `mysql-0` is `Running` and not mid-eviction.

## 3. WRITE-FREEZE (start of the window)

Reads keep serving; only writes stop. The UI is static and stays up.

```bash
kubectl -n lexitrail scale deploy/lexitrail-backend --replicas=0
kubectl -n lexitrail rollout status deploy/lexitrail-backend --timeout=60s
```

> Budget: the dump→import measured **63s**, so the freeze is ~2 minutes including
> verification — not an outage. That number is why this shape is affordable; it was
> measured on real data rather than estimated.

## 4. FINAL dump → import (inside the freeze)

🔴 **The 18:49Z seed import is NOT the migration.** `mysql-0` kept taking writes after
it. Re-run inside the freeze or every write since is silently lost — and it would be
lost in `recall_history`, the table users would notice.

```bash
# proxy up (local), then:
kubectl -n lexitrail exec mysql-0 -- sh -c \
  'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --set-gtid-purged=OFF \
     --routines --triggers --databases lexitraildb 2>/dev/null' \
 | sed -E 's/DEFINER=`[^`]+`@`[^`]+`//g' \
 | docker run --rm -i --network=host -e MYSQL_PWD="$PW" mysql:8 \
     mysql -h127.0.0.1 -P3307 -uroot
echo "PIPESTATUS: ${PIPESTATUS[@]}"   # ALL THREE must be 0
```

⚠️ **Check all three exit codes, not `$?`.** A pipeline reports only its last stage, so a
failed `mysqldump` feeding a successful `mysql` looks like success.

🔴 **The `sed` is load-bearing.** `daily_recall_stats` is a VIEW with
`DEFINER=root@%, SECURITY_TYPE=DEFINER`. On Cloud SQL `root` is not SUPER, and a DEFINER
clause is the standard cause of an import that fails **at the very end, after all the
table data has loaded** — so it looks like it mostly worked. It may pass (cloudsql.tf
creates `root@%`), but "may pass" is not something to discover inside a freeze window.

⚠️ Drop and recreate `lexitraildb` first if re-importing over the seed, or the table
data will collide.

## 5. Repoint and unfreeze

```bash
# repoint DATABASE_URL to the proxy endpoint, then:
kubectl -n lexitrail scale deploy/lexitrail-backend --replicas=<original>
kubectl -n lexitrail rollout status deploy/lexitrail-backend --timeout=180s
```

## 6. Verify (end of the freeze)

**Row counts, exact — not `information_schema`:**

```sql
SELECT 'users',COUNT(*) FROM users UNION ALL SELECT 'words',COUNT(*) FROM words
UNION ALL SELECT 'wordsets',COUNT(*) FROM wordsets
UNION ALL SELECT 'userwords',COUNT(*) FROM userwords
UNION ALL SELECT 'recall_history',COUNT(*) FROM recall_history
UNION ALL SELECT 'schema_migrations',COUNT(*) FROM schema_migrations
UNION ALL SELECT 'daily_recall_stats',COUNT(*) FROM daily_recall_stats;
```

🔴 **`information_schema.table_rows` is an InnoDB ESTIMATE and is materially wrong here**
— measured 2026-09-08: `users` estimate 2276 vs actual **2533**, `words` 4472 vs 5628,
`userwords` 29355 vs 27064. Wrong in both directions, so no fudge factor repairs it.
Anything quoting a user count should say **2,533**.

**Functional, headless — no Google session required:**

```bash
curl -s https://api.lexitrail.com/wordsets | head -c 200        # expect wordset_id
# guest path, with BOTH controls so a 200 is a verdict:
#   no Authorization header                    -> 401
#   Bearer UNAUTH_USER:x@notlexitrail.example  -> 401 invalid guest token
#   Bearer UNAUTH_USER:<x>@lexitrail.demo      -> 200 with user_id + wordset_id
```

Then one write (a recall) and re-read it, to confirm read **and** write on the new DB.

## 7. Rollback

Revert `DATABASE_URL` and scale back up. `mysql-0` was never stopped and still holds
everything up to the freeze, so no data is lost by rolling back. **Do not decommission
anything in the cutover window** — that is what keeps this reversible.

## 8. Decommission — only after 48h clean

Delete the `mysql-0` StatefulSet + PVC, keeping a PVC snapshot until then (lexitrail#358
step 5).

⚠️ Inherited from `CUTOVER-RUNBOOK.md` §4: do not let any GCS seed job point at the new
instance. None does today, but `cloudsql.tf` is a new root and anything added there later
inherits the hazard.

---

**Provenance:** every number above (63s, the exact counts, the DEFINER shape, the proxy
connectivity, the guest-token 401/401/200 triple) was measured on 2026-09-08 and is
recorded on lexitrail#358. The connector-wiring slice in §1 is the one part that is
design, not measurement, and it is marked as such.
