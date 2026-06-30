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

## Increment plan (this PR = increment 1, foundation)

1. **Foundation (this PR):** providers (k8s → ys-autopilot cross-project), cluster
   data source, variables, and the `allow-lb-healthcheck` NetworkPolicy. No secrets,
   no workloads — validates the cross-project wiring + ingress-allow.
2. **MySQL** — Deployment/StatefulSet + PVC (Autopilot `standard-rwo`, NOT legacy
   `standard`) into the `lexitrail` ns. Data migrated by dump→restore of the live
   527-day DB (NOT the GCS seed job, which must not clobber live data).
3. **Backend + UI** — deployments/services + GKE ingress; cross-ns service DNS
   rewritten to same-ns (collapsed `lexitrail` ns).
4. **TLS** — Certificate Manager DNS-authorization (one-time TopDNS record) so the
   cert is READY before the DNS A-flip.
5. **Cross-project IAM (D4)** — ys WI/node SA → `artifactregistry.reader` + GCS
   access on the `lexitrail` project (AR images + buckets stay there).
6. **Cutover** — operator updates TopDNS A-records; soak; decommission live root.

## Open dependency — secrets (D5)

The live root reads a local `.env` (dotenv): `DB_ROOT_PASSWORD`, `GOOGLE_CLIENT_ID`,
`DOMAIN_NAME`, `MYSQL_FILES_BUCKET`, … not present in this clone (operator-held).
**Recommendation:** source these from GCP Secret Manager (agent-deployable, no local
`.env`) via the cross-project WI SA, rather than replicating a local `.env`. The
actual secret values are an operator/SM dependency for increment 2+. Tracked on
my-hermes#905.

## Apply (once increments land)

```bash
cd terraform-ys
terraform init
terraform plan -out ys.plan
terraform apply ys.plan
```
Requires the apply host's egress in ys-autopilot `master_authorized_cidrs`.
