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

The two GCP-IAM grants in `iam.tf` (AR-reader on `lexitrail-repo`; WI binding on the
`lexitrail-sa` GSA) target the **lexitrail** project. The apply identity
(`epod-d-sa@yojowa-ensemble`) owns the GKE *clusters* but lacks `setIamPolicy` on the
lexitrail project, so it **cannot apply or drift-correct these two grants** — they
are operator-applied (Path B) and `terraform import`ed so `plan` stays clean.

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

## Apply

```bash
cd terraform-ys
terraform init
export TF_VAR_db_root_password="$(…source from the live MySQL root…)"
terraform plan -out ys.plan
terraform apply ys.plan
```
Requires the apply host's egress in ys-autopilot `master_authorized_cidrs`.
