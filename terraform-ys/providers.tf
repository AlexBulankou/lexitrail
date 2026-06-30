# google provider defaults to Lexitrail's home project (D4) — AR/GCS/IAM resources
# the workload increments add (cross-project grants to the ys WI/node SA) live here.
provider "google" {
  project = var.lexitrail_project_id
  region  = var.ys_region
}

# k8s providers point at the shared ys-autopilot cluster (cross-project), replacing
# the live root's in-cluster reference. Requires the apply host's egress to be in
# ys-autopilot master_authorized_cidrs.
provider "kubernetes" {
  host                   = "https://${data.google_container_cluster.ys.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(data.google_container_cluster.ys.master_auth[0].cluster_ca_certificate)
}

provider "kubectl" {
  host                   = "https://${data.google_container_cluster.ys.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(data.google_container_cluster.ys.master_auth[0].cluster_ca_certificate)
  load_config_file       = false
}
