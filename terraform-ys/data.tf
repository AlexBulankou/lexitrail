# Read the shared ys-autopilot cluster cross-project + a short-lived token to
# configure the k8s providers. This config creates NO cluster (unlike ../terraform).
data "google_client_config" "default" {}

data "google_container_cluster" "ys" {
  name     = var.ys_cluster_name
  location = var.ys_region
  project  = var.ys_project_id
}
