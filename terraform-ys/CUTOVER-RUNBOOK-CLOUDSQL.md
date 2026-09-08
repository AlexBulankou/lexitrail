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
`mysql-0` keeps serving its own data, so rollback is flipping the `Service/mysql` selector
back — seconds, no rebuild, not a DNS propagation wait.

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

**Connector wiring.** Nothing in the cluster can reach the instance today — the designed
security property (`ipv4_enabled` with empty `authorized_networks`), not a gap.

🔴 **And it is NOT a sidecar. There is no `DATABASE_URL` to repoint.** The connection
string is built in code and the host is a template:

```python
# backend/app/config.py — the in-cluster branch
'mysql+pymysql://root:{}@mysql.{}.svc.cluster.local:3306/{}'.format(
    DB_ROOT_PASSWORD, os.getenv('SQL_NAMESPACE'), DATABASE_NAME)
```

`SQL_NAMESPACE` fills the **namespace** slot, so it cannot produce any host but
`mysql.<ns>.svc.cluster.local`. ⚠️ The `else` branch dials `localhost` and looks like
sidecar support already exists — it is not: its gate is `KUBERNETES_SERVICE_HOST`, which
Kubernetes injects into every pod, so in-cluster that branch is unreachable. It is the
local-dev path.

⇒ **Prefer the Service swap over a sidecar.** A sidecar listens on `127.0.0.1` and would
need a `backend/**` code change, an image rebuild, a build unit, and an app redeploy
*inside the DB window* — two variables moving at once, rollback = redeploy. Instead run
`cloud-sql-proxy` as a Deployment in `lexitrail` and point the existing headless
`Service/mysql` (`selector={app: mysql}`, 3306→3306) at it. The app keeps dialling the
same hostname and never learns anything changed; **rollback is flipping the selector
back, in seconds, with no build.**

⏳ NOT yet verified: that a headless Service re-pointed at a proxy Deployment serves
end-to-end. Prove it in a scratch Service before any window — not by editing `mysql`.

⚠️ The app connects as **`root`**. The app-scoped user `cloudsql.tf` defers is still
right, but adopting it is a SECOND change; do not also do it in the cutover window.

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

**Both commands below were run verbatim on 2026-09-08; nothing here is adapted.**

```bash
# (a) START THE PROXY. Needs a gcloud identity with cloudsql.instances.connect;
#     it uses ADC, so pin the account rather than trusting whichever is active.
export CLOUDSDK_CORE_ACCOUNT=hermes-automation@yojowa-claw.iam.gserviceaccount.com
nohup /usr/local/bin/cloud_sql_proxy --port 3307 \
  lexitrail:us-central1:lexitrail-mysql > /tmp/csqlproxy.log 2>&1 &
PROXY_PID=$!                 # <- capture it NOW; see the teardown note below
grep -q "ready for new connections" /tmp/csqlproxy.log   # wait for this line

# (b) THE PASSWORD. The key is MYSQL_ROOT_PASSWORD -- NOT `password`.
PW=$(kubectl -n lexitrail get secret mysql-root \
       -o jsonpath='{.data.MYSQL_ROOT_PASSWORD}' | base64 -d)

# (c) dump -> import
kubectl -n lexitrail exec mysql-0 -- sh -c \
  'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --set-gtid-purged=OFF \
     --routines --triggers --databases lexitraildb 2>/dev/null' \
 | sed -E 's/DEFINER=`[^`]+`@`[^`]+`//g' \
 | docker run --rm -i --network=host -e MYSQL_PWD="$PW" mysql:8 \
     mysql -h127.0.0.1 -P3307 -uroot
echo "PIPESTATUS: ${PIPESTATUS[@]}"   # ALL THREE must be 0
```

🔴 **Tear the proxy down by the PID you captured — never `pkill -f`.** A pattern
specific enough to name the proxy (`cloud_sql_proxy`, `port 3307`, the instance name)
also matches the shell command that contains it, so `pkill -f`/`pgrep -f` kills your own
command. That happened **twice in one session** while writing this runbook, the second
time minutes after naming it. Use `kill "$PROXY_PID"`, and check with `ps -p "$PROXY_PID"`.

⚠️ There are other `cloud_sql_proxy` processes on bp serving unrelated instances
(`ensemble-db`, `marketmind-postgres`). A broad pattern reaches those too.

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

Repoint by **flipping the `Service/mysql` selector** at the proxy Deployment (see §1) —
not by editing any app config, because there is none to edit.

```bash
# after the selector points at the proxy:
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

**Rollback is ONE action, not two** (hc2's review Q on PR #412 — worth stating because
the sidecar shape it would have been is a two-field revert):

```bash
kubectl -n lexitrail patch svc mysql -p '{"spec":{"selector":{"app":"mysql"}}}'
```

The `cloud-sql-proxy` Deployment can **stay**. Once nothing selects it, it is inert — it
holds no app state and costs one small pod. Deleting it is cleanup for a later day, not a
rollback step, and doing it during a rollback adds a second thing that can fail while you
are already recovering.

`mysql-0` was never stopped and still holds everything up to the freeze, so no data is
lost by rolling back. **Do not decommission anything in the cutover window** — that is
what keeps this reversible.

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
