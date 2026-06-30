# WS2 increment 3a (my-hermes#905) — cross-project IAM foundation for the
# Lexitrail workloads running on ys-autopilot (D4: COMPUTE moves to ys-autopilot,
# but Artifact Registry + GCS + the `lexitrail-sa` GSA stay in the `lexitrail`
# project, reached cross-project). Both grants land on the `lexitrail` project
# (the google provider's default project — see providers.tf).
#
# This unblocks the workload increments (3b backend, 3c UI): without (1) the ys
# nodes can't PULL the cross-project images (ImagePullBackOff); without (2) the
# backend pod can't reach its GCS bucket / Vertex AI at runtime.

# ys cluster's project number — for the default compute SA the Autopilot nodes
# pull images as (verified: nodeConfig.serviceAccount=default → default compute SA).
data "google_project" "ys" {
  project_id = var.ys_project_id
}

# (1) AR-reader: let the ys Autopilot node SA pull the backend/UI images from
# lexitrail/lexitrail-repo. Autopilot image pulls authenticate as the node SA
# (the claw default compute SA), so the grant is cross-project (claw SA →
# reader on the lexitrail project). Scoped to the SINGLE repo (least-privilege)
# rather than project-wide AR — only lexitrail-repo holds the images.
resource "google_artifact_registry_repository_iam_member" "ys_nodes_ar_reader" {
  project    = var.lexitrail_project_id
  location   = var.ys_region
  repository = "lexitrail-repo"
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${data.google_project.ys.number}-compute@developer.gserviceaccount.com"
}

# The existing `lexitrail-sa` GSA (in the lexitrail project) — the live backend
# already impersonates it for GCS (MYSQL_FILES_BUCKET) + Vertex AI. Read it so we
# can add a cross-project Workload Identity binding (reuse, don't re-create:
# keeps a single GSA owning the bucket/AI grants across the migration).
data "google_service_account" "lexitrail_backend_gsa" {
  account_id = "lexitrail-sa"
  project    = var.lexitrail_project_id
}

# (2) Cross-project Workload Identity: allow the `lexitrail-backend` KSA in the
# ys cluster's `lexitrail` namespace to impersonate the GSA. The identity pool is
# the ys cluster's project (yojowa-claw) — NOT lexitrail — which is the
# cross-project part of this binding.
resource "google_service_account_iam_member" "backend_wi_binding" {
  service_account_id = data.google_service_account.lexitrail_backend_gsa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.ys_project_id}.svc.id.goog[${var.namespace}/lexitrail-backend]"
}

# The backend KSA in the collapsed `lexitrail` ns, annotated to impersonate the
# GSA. A DEDICATED KSA (not the shared `default`) so only the backend pod gets
# the GSA identity — the MySQL StatefulSet in the same ns keeps the default SA.
# The 3b backend Deployment sets serviceAccountName = this KSA.
resource "kubernetes_service_account_v1" "lexitrail_backend" {
  metadata {
    name      = "lexitrail-backend"
    namespace = var.namespace
    annotations = {
      "iam.gke.io/gcp-service-account" = data.google_service_account.lexitrail_backend_gsa.email
    }
  }
}
