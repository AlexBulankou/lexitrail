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