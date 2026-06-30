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
