# Lexitrail Cloud SQL cutover runbook (lexitrail#358)

Cut `lexitraildb` from the in-cluster `mysql-0` StatefulSet (spot GKE) to the managed
Cloud SQL instance `lexitrail:us-central1:lexitrail-mysql`, with a short write-freeze
and a config-only rollback.

✅ **EXECUTED 2026-09-09T03:57:23Z.** LexiTrail serves from Cloud SQL; verified by zz1's
close-check plus an independent discriminator (§6). `mysql-0` is deliberately NOT retired —
it is the rollback path (§7). Everything below is the as-run procedure, corrected against
what actually happened; three defects in the pre-run version are marked 🔴 CORRECTED.

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
| verified by exact `COUNT(*)` | all 6 tables + the view identical source↔target — ⚠️ **but `COUNT(*)` cannot see blob corruption**; see §6 for the CRC32 check that can |
| Auth Proxy reachability | `cloud_sql_proxy 2.8.0` → `127.0.0.1:3307`, connected as `root@%` |
| the guest-token probe | headless, no browser session needed (see §6) |

✅ **Connector wiring — DONE** (lexitrail#415 applied 2026-09-09T02:0xZ; the
`roles/cloudsql.client` grant is lexitrail#416). `cloudsql-proxy` runs 2/2 in `lexitrail`
and its own log shows `Authorizing with ADC` -> `Listening on 3306` -> `ready for new
connections`, so the grant is proven **at the wire**, not merely read from the IAM policy.

*(Historical: this section previously read "NOT done — the cutover is BLOCKED on this."
Nothing in the cluster could reach the instance — the designed security property
`ipv4_enabled` with empty `authorized_networks`, not a gap.)*

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

✅ **VERIFIED 2026-09-09T03:45Z** — a scratch `Service` selecting `app=cloudsql-proxy` on
3306, probed from a throwaway `mysql:8` pod, **with the control arm run**:

| path | `@@hostname` | `@@version_comment` | users |
|---|---|---|---|
| scratch -> proxy | `localhost` | **`(Google)`** | 2533 |
| `Service/mysql` -> mysql-0 (CONTROL) | `mysql-0` | `MySQL Community Server - GPL` | 2533 |

🔑 **`users` is 2533 on BOTH — a row count could never have discriminated.** The
discriminator is `@@version_comment`, and it is only a verdict because the control arm was
run. Do not verify a repoint with a row count.

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

🔴 **This is a brief API OUTAGE, not a reads-keep-serving freeze.** The freeze is
`--replicas=0` on the backend, and the backend serves reads as well as writes — so
`api/wordsets` returns nothing for the ~2 minutes below. The static UI stays up; the API
does not. An earlier version of this line said *"Reads keep serving; only writes stop"*,
which is wrong and understates the cost in the reassuring direction — kept visible rather
than silently corrected, because anyone who read it once will otherwise carry it into the
switch and mis-read a 200-less window as a fault.

### 🔴 CORRECTED — THE FREEZE MUST BE CRASH-SAFE. ARM A DEADMAN FIRST.

**A freeze whose undo depends on the freezer surviving is not an acceptable design for a
live site.** On 2026-09-08 an agent scaled the backend to 0 and its process exited
mid-cutover; the backend stayed at zero and the API was down **5.3 minutes** until a peer
noticed and scaled it back. That is not hypothetical — it happened, and it is why this step
is mandatory (zz1 ruling, 2026-09-08 20:43 PT).

Arm a detached deadman **before** scaling to 0. Cancel-file based, not PID-based: killing a
PID can leave an orphaned `sleep`, and `setsid` is what makes it outlive your session.

```bash
cat > /tmp/deadman.sh <<'EOS'
#!/bin/bash
T=$1; CANCEL=$2
for i in $(seq 1 "$T"); do sleep 1; [ -f "$CANCEL" ] && { echo CANCELLED; exit 0; }; done
echo "DEADMAN FIRING"; kubectl -n lexitrail scale deploy/lexitrail-backend --replicas=2
EOS
chmod +x /tmp/deadman.sh
setsid /tmp/deadman.sh 300 /tmp/cutover.cancel > /tmp/deadman.log 2>&1 < /dev/null &

kubectl -n lexitrail scale deploy/lexitrail-backend --replicas=0
kubectl -n lexitrail rollout status deploy/lexitrail-backend --timeout=60s
# ... window ...  then, after unfreezing:  touch /tmp/cutover.cancel
```

🔴 **Control-test the deadman before you trust it — a deadman that cannot fire is worse than
none.** All three arms, verified 2026-09-09: cancelled -> did NOT scale; not cancelled ->
scaled; **parent shell exits -> still fired** (that last one is the actual failure mode).

> 🔴 **CORRECTED BUDGET — the freeze is NOT the outage.** The as-run freeze was **85s**
> (03:55:58 -> 03:57:23Z), but scaling back to 2 adds **~60-90s of pod startup** before the
> API answers again. Real API downtime was **~2.7 minutes**. The old "~2 minutes including
> verification — not an outage" was wrong twice over: it ignored the read path *and* pod
> startup. **Budget ~3 minutes of API downtime, and tell stakeholders that number.**

## 4. FINAL dump → import (inside the freeze)

🔴 **The 18:49Z seed import is NOT the migration.** `mysql-0` kept taking writes after
it. Re-run inside the freeze or every write since is silently lost — and it would be
lost in `recall_history`, the table users would notice.

### 🔴 CORRECTED — TWO INDEPENDENT DEFECTS BROKE THIS STEP. Both fixes are required.

The pre-run command below failed twice on 2026-09-08/09. **Two separate causes stacked, and
fixing the first made the second look fixed** — a single green run is not evidence when the
second failure is intermittent.

**Defect 1 — raw binary blobs break the parse. Fix: `--hex-blob`.**
`words.hint_img` and `userwords.hint_img` are BLOB columns holding JPEGs (106 MB across 360
lines). The import died with `ERROR 1064 ... near ''?\??\?\0JFIF...'`. ⚠️ Two hypotheses
tested and **disproved** before fixing anything: `sed` is byte-clean (md5 of the failing line
identical through `sed`, `LC_ALL=C sed`, and no sed), and `max_allowed_packet` is not it
(longest line 1.0 MB vs Cloud SQL's 33 MB).

**Defect 2 — `docker run -i` silently truncates a large stdin stream. Fix: mount the file.**
With `--hex-blob` in place the import still failed intermittently:
`ERROR 1064 at line 358 ... near ''` — an **empty** statement 84% through. "near ''" is a
**truncated stream, not a syntax error**, and the cut position moved between runs (line 288,
then 358). Stage isolation: `kubectl exec` produced 177,935,283 B / 426 lines with the
`Dump completed` marker, byte-identical across two runs; `sed` removed exactly 18 bytes.
**The pipeline still exited 0 at the docker stage while delivering short input.**

⇒ **Dump to a file, check the marker, then import with the file MOUNTED** (`-v`), never piped.

**The commands below are the as-run 2026-09-09 versions; nothing here is adapted.**

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

# (c) DUMP TO A FILE  (note --hex-blob).  Took 5s as-run.
kubectl -n lexitrail exec mysql-0 -- sh -c \
  'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --set-gtid-purged=OFF \
     --hex-blob --routines --triggers --databases lexitraildb 2>/dev/null' \
 | LC_ALL=C sed -E 's/DEFINER=`[^`]+`@`[^`]+`//g' > /tmp/final.sql
echo "PIPESTATUS: ${PIPESTATUS[@]}"   # BOTH must be 0

# (d) GATE ON THE MARKER -- this is what catches a truncated stream.
tail -c 200 /tmp/final.sql | LC_ALL=C grep -q 'Dump completed on' \
  || { echo "TRUNCATED -- ABORT, do not import"; }

# (e) IMPORT FROM THE MOUNTED FILE, never piped stdin.  Took 67s as-run.
docker run --rm --network=host -v /tmp:/d:ro -e MYSQL_PWD="$PW" mysql:8 \
  sh -c 'mysql -h127.0.0.1 -P3307 -uroot < /d/final.sql'
echo "import rc=$?"   # must be 0
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

### 🔴 Row counts are NOT sufficient on their own — add the blob check

`COUNT(*)` cannot see blob corruption, and this database is ~83 MB of JPEGs in
`words.hint_img` / `userwords.hint_img`. Compare **byte totals and CRC32 sums** on both
sides. As-run 2026-09-09, identical source↔target:

```sql
SELECT COUNT(hint_img), SUM(LENGTH(hint_img)), SUM(CRC32(hint_img)) FROM words;
--   2223   35664463   4816591608870
SELECT COUNT(hint_img), SUM(LENGTH(hint_img)), SUM(CRC32(hint_img)) FROM userwords;
--   4044   47910294   8504667140746
```

🔑 **Gate the selector flip on this comparison, computed WHILE FROZEN.** The as-run script
flipped only on an exact source==target match of all counts plus both CRC32 sums; on any
mismatch it unfreezes and does not flip.

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
# ⚠️ Use /wordsets, NOT /users/me. A guest token is correctly REFUSED by /users/me with
#    403 "You can only access your own data" -- that is the endpoint working, not a fault.
#    Probing the wrong endpoint here reads as a broken cutover.
# guest path, with BOTH controls so a 200 is a verdict:
#   no Authorization header                    -> 401
#   Bearer UNAUTH_USER:x@notlexitrail.example  -> 401 invalid guest token
#   Bearer UNAUTH_USER:<x>@lexitrail.demo      -> 200 with user_id + wordset_id
```

Then one write (a recall) and re-read it, to confirm read **and** write on the new DB.

### 🔑 THE CLOSE DISCRIMINATOR — 200s prove NOTHING here

A repoint that silently fails leaves the site perfectly healthy **on mysql-0**. So health
checks cannot close this. Two discriminators, both run as-run:

1. **mysql-0's own `Questions` counter** (zz1's `zz1-tools/zz1-lexitrail-cutover-verify.sh`):
   read it, drive real traffic through the public endpoint, read it again. Control taken
   while demonstrably on mysql-0: **delta 45 under 12 API reads**. After cutover: **delta 3**
   — and an idle control showed **+3 per 30s with zero API calls**, with `processlist`
   holding only `event_scheduler` and the probe's own connection. So the residual is not app
   traffic.
2. **Ask the app's own hostname what it is.** `mysql.lexitrail.svc.cluster.local` now answers
   `@@version_comment = (Google)`; mysql-0 answers `MySQL Community Server - GPL`.

Use both — they are independent, and the second does not depend on traffic shape.

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
