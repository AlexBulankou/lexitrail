# --- Target cluster (ys-autopilot in the claw project; read via data source) ---
variable "ys_project_id" {
  description = "Project hosting the shared ys-autopilot cluster."
  type        = string
  default     = "yojowa-claw"
}

variable "ys_region" {
  description = "Region of the ys-autopilot cluster."
  type        = string
  default     = "us-central1"
}

variable "ys_cluster_name" {
  description = "Name of the shared cluster to deploy into."
  type        = string
  default     = "ys-autopilot"
}

# --- Lexitrail home project (D4: AR images + GCS buckets + IAM stay here; only
#     compute moves to ys-autopilot, reached cross-project) ---
variable "lexitrail_project_id" {
  description = "Lexitrail's home project — Artifact Registry, GCS, service accounts stay here (issue-905 D4)."
  type        = string
  default     = "lexitrail"
}

variable "lexitrail_repo_location" {
  description = "Location of the lexitrail-repo Artifact Registry repo. A lexitrail-side fact fixed at the repo's creation — kept separate from ys_region so a future ys cluster-region move can't break the cross-project AR-reader grant (HC2 #15 catch). Verified live: us-central1."
  type        = string
  default     = "us-central1"
}

# --- Backend non-secret config (mirrors the live backend-config ConfigMap;
#     SQL_NAMESPACE is the one D1-collapse adaptation and is derived from
#     var.namespace, not hardcoded here) ---
variable "image_tag" {
  description = "Image tag for the backend + UI images in lexitrail-repo (live uses :latest)."
  type        = string
  default     = "latest"
}

variable "database_name" {
  description = "App database name (live backend-config DATABASE_NAME)."
  type        = string
  default     = "lexitraildb"
}

variable "google_client_id" {
  description = "OAuth client ID (live backend-config GOOGLE_CLIENT_ID; public, not a secret)."
  type        = string
  default     = "323289939168-p7nv7pp1smqa46ck3uqigapkq9hslth3.apps.googleusercontent.com"
}

variable "mysql_files_bucket" {
  description = "GCS bucket the backend reads MySQL/seed files from (stays in the lexitrail project, D4)."
  type        = string
  default     = "lexitrail-lexitrail-mysql-files"
}

variable "location" {
  description = "Region the backend targets for Vertex AI / GCP API calls (backend-config LOCATION). An app/AI-region choice independent of the ys COMPUTE region (var.ys_region) — decoupled per HC2 #16 nb so a future ys cluster-region move doesn't silently retarget Vertex. us-central1 today (= ys region)."
  type        = string
  default     = "us-central1"
}

# --- Tenant namespace (D1: single collapsed ns; owned by my-hermes tenants root,
#     referenced here — NOT created here) ---
variable "namespace" {
  description = "The lexitrail tenant namespace on ys-autopilot (created + isolated by the my-hermes terraform/tenants root; this config deploys INTO it)."
  type        = string
  default     = "lexitrail"
}

# --- Secrets (D5: sourced cluster→cluster from the live lexitrail DB, NOT a local
#     .env and NOT an Alex handoff — I own both clusters). No default: provided at
#     apply via TF_VAR_db_root_password (e.g. read from the live StatefulSet env),
#     so the value never lands in git — only in access-controlled tf state + the
#     in-cluster Secret. ---
variable "db_root_password" {
  description = "MySQL root password — must match the live DB so dump→restore (exec step 4) and the backend connection keep working. Sourced from the live cluster at apply time; never committed."
  type        = string
  sensitive   = true
}
