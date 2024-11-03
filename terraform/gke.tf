resource "google_container_cluster" "autopilot_cluster" {
  name             = var.cluster_name
  location         = var.region
  project          = var.project_id
  network          = google_compute_network.main.name
  subnetwork       = google_compute_subnetwork.main.name
  enable_autopilot = true
  deletion_protection = false
  ip_allocation_policy {}
  node_pool_auto_config {
    network_tags {
      tags = ["game-server"]
    }
  }
}

data "google_container_cluster" "cluster" {
  name     = google_container_cluster.autopilot_cluster.name
  location = google_container_cluster.autopilot_cluster.location
  project  = google_container_cluster.autopilot_cluster.project
}

# output "cluster_host" {
#   value = "https://${google_container_cluster.autopilot_cluster.endpoint}"
# }

# output "cluster_token" {
#   value = data.google_client_config.default.access_token
# }

# output "cluster_ca_certificate" {
#   value = google_container_cluster.autopilot_cluster.master_auth.0.cluster_ca_certificate
# }