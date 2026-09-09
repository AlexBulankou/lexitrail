# terraform-ys — Lexitrail re-home onto ys-autopilot (WS2, my-hermes#905)

Parallel terraform config that re-homes Lexitrail (UI + backend + MySQL) onto the
shared **ys-autopilot** Autopilot cluster in **yojowa-claw**, as part of the YS
consolidation (my-hermes#901).

**Why a separate root from `../terraform`:** the live root manages the standalone
`lexitrail-cluster` (its state owns the `google_container_cluster`). Editing it in
place to retarget would make `terraform apply` try to **destroy the live service**.
This root has its own state (GCS `lexitrail-ys` prefix) and never touches the live
root — enabling parallel-run + DNS-flip + rollback. The live root is decommissioned
only after cutover + soak.

## Increment plan + status

1. ✅ **Foundation** — providers (k8s → ys-autopilot cross-project), cluster data
   source, variables, `allow-lb-healthcheck` NetworkPolicy. (lexitrail PR #13)
2. ✅ **MySQL** — StatefulSet + headless Service + Secret-backed root password +
   PVC (Autopilot `standard-rwo`, NOT legacy `standard`). Brought up on a FRESH
   empty PVC; live 527-day data migrated by dump→restore (step 4), NOT the GCS seed
   job. (lexitrail PR #14)
3. **Backend + UI workloads:**
   - ✅ **3a IAM (D4)** — repo-scoped `artifactregistry.reader` for the ys node SA +
     cross-project Workload Identity binding (`lexitrail-backend` KSA → `lexitrail-sa`
     GSA). Operator-applied (Path B) + imported. (lexitrail PR #15)
   - ✅ **3b/3c workloads** — backend (ConfigMap/Secret/Deployment/Service) + UI
     (Deployment/Service) into the collapsed `lexitrail` ns. `SQL_NAMESPACE`
     rewritten cross-ns→same-ns (`= var.namespace`). Smoke-tested: cross-proj image
     pull ✅, WI identity wired ✅, backend↔MySQL connect + /health 200 ✅, UI 1/1 ✅.
4. **TLS** — Certificate Manager DNS-authorization (one-time TopDNS record) so the
   cert is READY before the DNS A-flip.
5. **(folded into 3a)** Cross-project IAM — done with the workloads.
6. **Cutover** — operator updates TopDNS A-records; soak; decommission live root.

> **Step-4 data note:** the backend app fails to bind `:80` until the `lexitraildb`
> database exists (it connects to MySQL at startup). An EMPTY `lexitraildb` was
> created on the ys MySQL to smoke-test 3b (the app boots + /health passes once the
> DB exists). Step 4's dump→restore of the live `lexitraildb` populates it
> authoritatively — the empty DB is harmless (restore overwrites).

## Secrets (D5 — resolved)

D5 is self-sourceable: the only secret is the MySQL root password (the backend
connects as root — `backend-secret`/`mysql-root` both hold just `DB_ROOT_PASSWORD`).
It's sourced **cluster→cluster** from the live Lexitrail DB at apply time and passed
via `TF_VAR_db_root_password` — never committed, lives only in access-controlled tf
state + the in-cluster Secrets. No local `.env`, no Secret Manager, no Alex handoff.
`GOOGLE_CLIENT_ID` is a public OAuth client id (a plain variable, not a secret).

## Cross-project IAM — ownership + re-apply runbook (Path B)

The **three** GCP-IAM grants targeting the **lexitrail** project — AR-reader on
`lexitrail-repo` and the WI binding on the `lexitrail-sa` GSA (both `iam.tf`), plus
`roles/cloudsql.client` on `lexitrail-sa` (`cloudsql-connector.tf`, added by #416) —
are not appliable from this root. The apply identity (`epod-d-sa@yojowa-ensemble`)
owns the GKE *clusters* but lacks `setIamPolicy` on the lexitrail project, so it
**cannot apply or drift-correct them** — they are operator-applied (Path B) and
`terraform import`ed so `plan` stays clean.

🔴 **The IMPORT needs a different identity than the STATE BACKEND, and that split is
the thing that will stop you.** `backend.tf` correctly names
`hermes-automation@yojowa-claw` as the principal that reaches the state bucket. That
same principal is **403 on `lexitrail:getIamPolicy`**, so `terraform import` of any of
these three fails on the *resource read* — after the state lock is acquired, which is
why it reads as a lock or a state problem rather than a permissions one. Measured
2026-09-08 across all eight accounts on the bp host:

```
bulankou@gmail.com                                    getIamPolicy OK
ensemble-sa · familylore-sa · hermes-automation
sandbox-sa · sbs-agent-ops · sp-k8s-sa · yojowa-site-sa   all DENIED
```

⇒ Run the import with the operator credential:
`GOOGLE_OAUTH_ACCESS_TOKEN="$(gcloud auth print-access-token --account=bulankou@gmail.com)"`.

⚠️ **`--account=` is a REQUEST, not an assertion.** On a seat that cannot honour it,
gcloud falls back to the active account and mints a perfectly valid token for the
*wrong* identity — exit 0, no warning. Assert the realised identity before using it:

```bash
TK=$(gcloud auth print-access-token --account=bulankou@gmail.com)
curl -s "https://oauth2.googleapis.com/tokeninfo?access_token=$TK" | python3 -c 'import json,sys;print(json.load(sys.stdin)["email"])'
# must print bulankou@gmail.com before you proceed
```

If either grant is ever removed/drifts (terraform `plan` would want to "create" it but
`apply` 403s), an **operator** (or anyone with lexitrail-project IAM-admin) re-applies:

```bash
# 1. AR-reader (image pull) — repo-scoped, least-privilege
gcloud artifacts repositories add-iam-policy-binding lexitrail-repo \
  --project=lexitrail --location=us-central1 \
  --member="serviceAccount:360889204939-compute@developer.gserviceaccount.com" \
  --role="roles/artifactregistry.reader"

# 2. Cross-project Workload Identity (runtime GCS/Vertex)
gcloud iam service-accounts add-iam-policy-binding \
  lexitrail-sa@lexitrail.iam.gserviceaccount.com --project=lexitrail \
  --member="serviceAccount:yojowa-claw.svc.id.goog[lexitrail/lexitrail-backend]" \
  --role="roles/iam.workloadIdentityUser"
```

The grants are stable, so this is a break-glass procedure, not routine. (Alternative:
grant `epod-d-sa` standing `artifactregistry.admin` + `iam.serviceAccountAdmin` on
lexitrail to make the stack fully self-applying — declined for least-privilege.)

## Is it applied? (run this before you reason from these files)

```bash
python3 ../scripts/check_terraform_ys_drift.py     # 0 PASS · 1 FAIL · 3 CANNOT-TELL
```

`terraform-ys/` has no apply trigger and no apply automation anywhere in the tree,
so an infra change lands on `main` and stops there. Between 2026-06-30 and
2026-09-02 that swallowed 14 commits, including two live reliability fixes
(#164's `startupProbe`, #301/#304's `/readyz` readiness path). See #299.

🔴 **Reading a file in this directory tells you nothing about the cluster, and
the cases where it happens to be right are the ones that make that hardest to
notice.** On 2026-09-02 the backend's cpu/memory limits matched `workloads.tf`
exactly -- because a human ran `kubectl patch` on 08-29, not because terraform
applied. The check above compares *who last wrote the object* rather than any
field value, which is why a coincidence cannot fool it.

⏳ **RESOLVED 2026-09-08 — kept rather than deleted, because a reader who has seen
the old warning needs to meet its retirement, not its absence.**

> 🔴 ~~`terraform apply` is not a safe no-op today -- ten live Gateway/TLS objects
> are absent from state and plan as `+ create`. Read **my-hermes#1338** first -- the
> import is owned and gated there.~~

**my-hermes#1338 is CLOSED (2026-09-08T15:34Z)** and its closing evidence is a value
the tool computed, not a rendering someone read:

```
terraform plan -detailed-exitcode   ->  0     ("No changes")
   0 = no changes, 2 = changes. Chosen deliberately over reading the plan's DISPLAY.
state list | grep ingress_v1        ->  none  (the 2 ghosts gone)
state now holds 43 resources, 20 of them the kubectl_manifest / PDB / www-TLS
classes the import existed to bring in.
```

✅ **Independently corroborated the same day, from a different direction**: a
`terraform plan` for lexitrail#358's connector slice returned **`2 to add, 0 to
change, 0 to destroy`** — exactly its own two new resources. Had the ten objects
still been absent from state they would have appeared as `+ create` in that same
plan, making it 12+. **A plan run for an unrelated reason is the better witness,
because it was not looking for this.**

⚠️ Two things this does NOT license:
- **Merging is still not applying.** Nothing in CI applies this directory — the
  workflows are `backend-tests.yml` / `ui-tests.yml` only. Apply is the manual
  recipe below, and a merged `.tf` changes nothing until someone runs it.
- **Re-check before a big apply anyway.** The claim above is "state matched config
  on 2026-09-08", not an invariant. `plan -detailed-exitcode` is one command and
  the whole point of this section's history is that a stale safety note is worse
  than none — it either blocks work that is fine, or gets routed around, and the
  routing becomes the habit.

Its reader is manual until lexitrail has a scheduler at all
(`GET /projects/lexitrail/schedules` -> `Unknown project`, ensemble#9032).

## Apply

```bash
cd terraform-ys
terraform init
export TF_VAR_db_root_password="$(…source from the live MySQL root…)"
terraform plan -out ys.plan
terraform apply ys.plan
```
Requires the apply host's egress in ys-autopilot `master_authorized_cidrs`.
