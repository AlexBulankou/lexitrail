terraform {
  required_providers {
    google = {
      source = "hashicorp/google-beta"
      version = "~> 5.42.0"
    }
    kubectl = {
      source  = "alekc/kubectl"
      version = "~> 2.0.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google" {
  alias   = "us-central1"
  project = var.project_id
  region  = "us-central1"
}

provider "kubectl" {
  host                   = google_container_cluster.autopilot_cluster.endpoint
  cluster_ca_certificate = base64decode(google_container_cluster.autopilot_cluster.master_auth.0.cluster_ca_certificate)
  token                  = data.google_client_config.default.access_token
  load_config_file       = false
}

data "google_client_config" "default" {}

data "google_project" "default" {
  project_id = var.project_id
}


# IAM Bindings
resource "google_project_iam_member" "cloudbuild_roles" {
  for_each = toset([
    "roles/storage.admin",
    "roles/logging.logWriter",
    "roles/artifactregistry.admin",
    "roles/reader",
    "roles/storage.objectCreator",
    "roles/serviceusage.serviceUsageConsumer",
    "roles/cloudbuild.builds.editor"
  ])

  project = var.project_id
  member  = "serviceAccount:${data.google_project.default.number}@cloudbuild.gserviceaccount.com"
  role    = each.value
}

resource "google_project_iam_member" "compute_roles" {
  for_each = toset([
    "roles/storage.admin",
    "roles/logging.logWriter",
    "roles/artifactregistry.admin",
    "roles/reader",
    "roles/storage.objectCreator",
    "roles/serviceusage.serviceUsageConsumer",
    "roles/cloudbuild.builds.editor"
  ])

  project = var.project_id
  member  = "serviceAccount:${data.google_project.default.number}-compute@developer.gserviceaccount.com"
  role    = each.value
}

# Artifact Registry

resource "google_artifact_registry_repository" "my_repo" {
  provider          = google
  location          = var.region
  repository_id     = var.repository_id
  description       = "Lexitrail registry"
  format            = "DOCKER"
}

# GKE Autopilot Cluster
resource "google_container_cluster" "autopilot_cluster" {
  name             = var.cluster_name
  location         = var.region
  project          = var.project_id
  enable_autopilot = true

  ip_allocation_policy {
    
  }
}

# Cloud Build Execution

resource "null_resource" "cloud_build" {
  triggers = {
    files_hash    = sha1(join("", [for f in fileset(path.root, "../ui/**") : filesha1(f)]))
  }

  provisioner "local-exec" {
    command = <<EOT
      gcloud builds submit --project ${var.project_id} \
                           --tag ${var.region}-docker.pkg.dev/${var.project_id}/${var.repository_id}/${var.container_name}:latest \
                           ../ui/
    EOT
  }
}


resource "kubectl_manifest" "lexitrail_ui_deployment" {
  yaml_body = templatefile("${path.module}/deploy-deployment.yaml.tpl", {
    project_id     = var.project_id,
    container_name = var.container_name
    repo_name = var.repository_id
    region = var.region
  })
}

resource "kubectl_manifest" "lexitrail_ui_service" {
  yaml_body = templatefile("${path.module}/deploy-service.yaml.tpl", {
  })
}

