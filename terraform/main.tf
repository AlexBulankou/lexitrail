terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "4.38.0"
    }
    kubectl = {
      source  = "alekc/kubectl"
      version = ">= 2.0.0"
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

data "google_client_config" "default" {}

data "google_project" "default" {
  project_id = var.project_id
}

/*
provider "kubectl" {
  host                   = google_container_cluster.autopilot_cluster.endpoint
  cluster_ca_certificate = base64decode(google_container_cluster.autopilot_cluster.master_auth.0.cluster_ca_certificate)
  token                  = data.google_client_config.default.access_token
  load_config_file       = false
}
*/

/*
# Storage Bucket
resource "google_storage_bucket" "frontend_bucket" {
  name     = var.fe_bucket_name
  location = var.region

  uniform_bucket_level_access = true # Enable uniform bucket-level access
}

resource "google_storage_bucket_iam_binding" "frontend_bucket_binding" {
  bucket = google_storage_bucket.frontend_bucket.name

  role = "roles/storage.admin"
  members = [
    "serviceAccount:${data.google_project.default.number}@cloudbuild.gserviceaccount.com",
    "serviceAccount:${data.google_project.default.number}-compute@developer.gserviceaccount.com",
  ]
}
*/

# IAM Bindings
resource "google_project_iam_member" "cloudbuild_roles" {
  for_each = toset([
    "roles/storage.admin",
    "roles/logging.logWriter",
    "roles/artifactregistry.admin",
    "roles/viewer",
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
    "roles/viewer",
    "roles/storage.objectCreator",
    "roles/serviceusage.serviceUsageConsumer",
    "roles/cloudbuild.builds.editor"
  ])

  project = var.project_id
  member  = "serviceAccount:${data.google_project.default.number}-compute@developer.gserviceaccount.com"
  role    = each.value
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
    always_run = "${timestamp()}"
    files_hash = md5(join("", fileset("../ui/", "**")))
  }

  provisioner "local-exec" {
    command = <<EOT
      gcloud builds submit --project ${var.project_id} --tag gcr.io/${var.project_id}/${var.container_name}:latest ../ui/
    EOT
  }
}

# this configuration ensures that build only runs when files under ui/ change
/*
resource "null_resource" "cloud_build" {
  triggers = {
    always_run = "${timestamp()}"
    files_hash = md5(join("", fileset("../ui/", "**")))
  }

  provisioner "local-exec" {
    command = <<EOT
      gcloud builds submit --project ${var.project_id} --tag gcr.io/${var.project_id}/${var.container_name}:latest ../ui/
    EOT
  }
}

# also consider this: to use artifact registry

/*

gcloud artifacts repositories create my-repo \
--repository-format=docker \
--location=us-central1 \
--description="Docker repository"

and then using: 

 provisioner "local-exec" {
    command = <<EOT
      # Set variables
      REGION="us-central1"
      REPO="my-repo"
      IMAGE_NAME="gcr.io/${var.project_id}/${var.container_name}:latest"

      # Submit the build to Cloud Build and push to Artifact Registry
      gcloud builds submit --project ${var.project_id} --tag ${REGION}-docker.pkg.dev/${var.project_id}/${REPO}/${var.container_name}:latest ../ui/
    EOT
  }

*/

/*
resource "kubectl_manifest" "lexitrail_ui_deployment" {
  yaml_body = templatefile("${path.module}/deploy.yaml.tpl", {
    project_id     = var.project_id,
    container_name = var.container_name
  })
}
*/

