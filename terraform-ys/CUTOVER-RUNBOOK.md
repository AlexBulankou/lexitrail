# Lexitrail WS2 cutover runbook (my-hermes#905)

Step-by-step to cut Lexitrail from the standalone `lexitrail-cluster` to the
re-homed stack on **ys-autopilot** (`lexitrail` ns), with **near-zero write
downtime** and a clean rollback. The new stack (MySQL + backend + UI + ingresses
+ TLS) is already applied + smoke-tested (increments 1-4); this runbook covers
the data move + DNS cutover + decommission, which are deliberately LAST.

**Guiding safety property:** the live `../terraform` root + its cluster stay
**fully running + untouched** until the final decommission step. Until then,
rollback = re-point DNS at the old IPs (the old stack never went away).

---

## 0. Roles
- **HCL (agent):** everything except the TopDNS record changes (I own both GKE
  clusters + the ys GCP resources, but **not** the TopDNS registrar).
- **Alex (operator):** the TopDNS record changes (steps marked **[ALEX]**).
  lexitrail.com DNS is at the **TopDNS registrar** (`ns-*.topdns.com`), NOT Cloud
  DNS — so A/CNAME changes are operator-only.

## 1. Prerequisites (verify before scheduling the cutover window)
- [ ] PR #17 (increment 4) merged.
- [ ] **TLS certs ACTIVE** — gated on **[ALEX]** adding the two `_acme-challenge`
      CNAMEs at TopDNS (already sent, my-hermes#905). Verify:
      `gcloud certificate-manager certificates list --project yojowa-claw`
      → both `lexitrail-ys-ui-cert` + `lexitrail-ys-backend-cert` == `ACTIVE`.
- [ ] **Ingress LBs provisioned + bound to the reserved IPs:**
      `kubectl get ingress -n lexitrail` → ADDRESS == `34.149.198.93` (UI) /
      `8.233.184.38` (backend); backends `HEALTHY`.
- [ ] **HTTP/HTTPS smoke-test on the new LB IPs** with a Host header (before any
      DNS change — proves the new stack serves end-to-end):
      ```
      curl -sky -H 'Host: lexitrail.com'     https://34.149.198.93/  -o /dev/null -w '%{http_code}\n'
      curl -sky -H 'Host: api.lexitrail.com' https://8.233.184.38/health -w '\n%{http_code}\n'
      ```
- [ ] **[ALEX] lower the TopDNS A-record TTL to 300s** for `lexitrail.com` +
      `api.lexitrail.com` at least one old-TTL-period **before** the cutover
      window — so the step-5 flip propagates in minutes, shrinking the
      write-freeze window. (Do this a day ahead; it's safe + invisible.)

## 2. Capture old-state for rollback (HCL)
Record the CURRENT live A-records so rollback is exact:
```
# api.lexitrail.com → 34.54.184.9 (live backend LB)   [confirm at cutover time]
# lexitrail.com     → 34.36.186.108 (live UI LB)       [confirm at cutover time]
dig +short api.lexitrail.com A; dig +short lexitrail.com A
```
Snapshot the live PD (belt-and-braces, off-cluster):
```
gcloud compute disks snapshot <live-mysql-pd> --project lexitrail \
  --snapshot-names lexitrail-precutover-$(date +%Y%m%d) --zone <zone>
```

## 3. WRITE-FREEZE on live (HCL) — start of the near-zero-write window
Freeze writes (reads keep serving on the old stack until DNS flips). Simplest =
scale the live backend to 0 so no new writes hit live MySQL:
```
kubectl --context gke_lexitrail_us-central1_lexitrail-cluster -n backend \
  scale deploy/lexitrail-backend --replicas=0
```
> The UI stays up (static); the site is read-degraded (no writes) but not down.
> The freeze holds until step 6 confirms the new stack serves.

## 4. DUMP → RESTORE the live data (HCL)
`lexitraildb` is small (~6 tables; `recall_history` ~43K rows the largest), so
this is seconds-to-a-minute. Dump live, restore into the ys MySQL:
```
LX=gke_lexitrail_us-central1_lexitrail-cluster
# Dump the FULL app DB (data + schema + routines/triggers). Backend connects as
# root (no app user → no separate grants to carry).
kubectl --context $LX -n mysql exec mysql-0 -- sh -c \
  'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --routines --triggers --single-transaction \
   --databases lexitraildb' > /tmp/lexitraildb-cutover.sql

# Restore into the ys MySQL (context = ys; the empty lexitraildb created during
# incr-3 smoke-test is overwritten by --databases which DROP/CREATEs it).
kubectl --context gke_yojowa-claw_us-central1_ys-autopilot -n lexitrail \
  exec -i mysql-0 -- sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD"' < /tmp/lexitraildb-cutover.sql
```
**Verify the restore (row counts match live):**
```
for db in live ys; do ...compare SELECT COUNT(*) on recall_history/users/userwords...; done
```
Then **restart the ys backend** so it reconnects to the now-populated DB + confirm
`/health` 200 and a real query works **with the backend's own creds** (HC2 #14
nb — verify with the app's credentials, not just a root check):
```
kubectl --context ...ys... -n lexitrail rollout restart deploy/lexitrail-backend
kubectl --context ...ys... -n lexitrail exec deploy/lexitrail-backend -- <app-level data check>
```

## 5. DNS cutover [ALEX] — flip the A-records at TopDNS
Once step-4 verify passes, **[ALEX]** changes the two A-records at TopDNS:
| Host | OLD → | NEW |
|---|---|---|
| `lexitrail.com` | 34.36.186.108 → | **34.149.198.93** |
| `api.lexitrail.com` | 34.54.184.9 → | **8.233.184.38** |
(With the 300s TTL from step 1, propagation is ~minutes.)

## 6. Verify the new stack serves (HCL) — end of the write-freeze window
```
dig +short lexitrail.com A          # → 34.149.198.93 (propagated)
dig +short api.lexitrail.com A      # → 8.233.184.38
curl -s https://api.lexitrail.com/health         # 200
curl -s https://lexitrail.com/ -o /dev/null -w '%{http_code}\n'  # 200, valid cert
# App-level: log in, read a wordset, do a write (recall) → confirms read+write on new.
```
When confirmed, the write-freeze is over (writes now land on the new stack). The
live backend stays at 0 replicas (it's being decommissioned).

> **If anything fails here → ROLLBACK:** [ALEX] revert the two A-records to the
> step-2 old IPs; HCL scales the live backend back to 1. The old stack is intact
> + has all writes up to the freeze (no data lost — writes were frozen, not
> dropped). Investigate, retry later.

## 7. Soak (HCL) — gate decommission on OBSERVED zero-traffic, not a timer
Monitor the OLD LB for residual traffic (stragglers on cached DNS) for **≥24-48h**
(HC2 #905 catch 1 — decommission on observed zero-traffic, not a clock):
```
# old UI + backend LB request counts via Cloud Monitoring (lexitrail project)
# loadbalancing.googleapis.com/https/request_count → confirm → 0 sustained
```
Also watch the new stack: error rate, latency, MySQL health, no preemption-driven
DB blips (Spot — same posture as live, HC2 #14 nb).

## 8. Decommission (HCL) — only after soak shows sustained zero old-traffic
1. **Final off-cluster backup** (authoritative end-state): one more
   `mysqldump lexitraildb` from the **new** ys MySQL → GCS + a PD snapshot.
2. **Tear down the live root:** `cd ../terraform && terraform destroy` (this
   removes the standalone `lexitrail-cluster` + its LBs + old static IPs +
   ManagedCertificates). **Double-check** `terraform plan -destroy` targets ONLY
   the live root's resources before applying.
3. **[ALEX] remove the now-stale `_acme-challenge` CNAMEs** at TopDNS (optional
   cleanup; harmless if left).
4. Close my-hermes#905; update [[project-lexitrail-ownership]].

---

## Rollback summary (any step before 8)
The live stack is untouched until step 8, so rollback is always: **[ALEX]** point
the two A-records back at the old IPs + **HCL** scale the live backend to 1. No
data loss (writes were frozen during the window, not dropped). This is why
decommission is gated on observed zero-traffic + a final backup — not a timer.
