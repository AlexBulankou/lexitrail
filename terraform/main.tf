terraform {
  required_providers {
    google = {
      source  = "hashicorp/google-beta"
      version = "~> 5.42.0"
    }
    kubectl = {
      source  = "alekc/kubectl"
      version = "~> 2.0.0"
    }
    dotenv = {
      source  = "germanbrew/dotenv"  # Correct provider namespace
      version = "~> 1.0"
    }
  }
}

provider "dotenv" {
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

data "dotenv" "env" {
  filename = "./../.env"
}

locals {
  db_root_password = data.dotenv.env.entries.DB_ROOT_PASSWORD
  google_client_id = data.dotenv.env.entries.GOOGLE_CLIENT_ID
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
  provider      = google
  location      = var.region
  repository_id = var.repository_id
  description   = "Lexitrail registry"
  format        = "DOCKER"
  depends_on = [
    google_project_iam_member.compute_roles,
    google_project_iam_member.cloudbuild_roles
  ]
}

# GKE Autopilot Cluster
resource "google_container_cluster" "autopilot_cluster" {
  name             = var.cluster_name
  location         = var.region
  project          = var.project_id
  enable_autopilot = true

  # Disable deletion protection
  deletion_protection = false

  ip_allocation_policy {

  }
}

resource "google_service_account" "lexitrail_storage_sa" {
  account_id   = "lexitrail-storage-sa"  # Valid account_id format
  display_name = "Lexitrail Storage Service Account"
}


# Cloud Build Execution

resource "null_resource" "cloud_build" {
  triggers = {
    files_hash = sha1(join("", [for f in fileset(path.root, "../ui/**") : filesha1(f)]))
  }

  provisioner "local-exec" {
    command = <<EOT
      gcloud builds submit --project ${var.project_id} \
                           --tag ${var.region}-docker.pkg.dev/${var.project_id}/${var.repository_id}/${var.container_name}:latest \
                           ../ui/
    EOT
  }
  depends_on = [
    google_project_iam_member.compute_roles,
    google_project_iam_member.cloudbuild_roles
  ]
}

# UI manifests

resource "kubectl_manifest" "lexitrail_ui_deployment" {
  yaml_body = templatefile("${path.module}/k8s_templates/deploy-deployment.yaml.tpl", {
    project_id     = var.project_id,
    container_name = var.container_name
    repo_name      = var.repository_id
    region         = var.region
  })
}

resource "kubectl_manifest" "lexitrail_ui_service" {
  yaml_body = templatefile("${path.module}/k8s_templates/deploy-service.yaml.tpl", {
  })
}

# SQL deployment
resource "kubectl_manifest" "mysql_namespace" {
  yaml_body = templatefile("${path.module}/k8s_templates/mysql-namespace.yaml.tpl", {
    sql_namespace = var.sql_namespace,
    gsa_email     = google_service_account.lexitrail_storage_sa.email
  })
}

resource "kubectl_manifest" "default_sa_annotation" {
  yaml_body = templatefile("${path.module}/k8s_templates/mysql-default-service-account.yaml.tpl", {
    sql_namespace = var.sql_namespace,
    gsa_email     = google_service_account.lexitrail_storage_sa.email
  })
}


resource "kubectl_manifest" "mysql_pvc" {
  yaml_body = templatefile("${path.module}/k8s_templates/mysql-pvc.yaml.tpl", {
    sql_namespace = var.sql_namespace
  })
  depends_on = [kubectl_manifest.mysql_namespace]
}

resource "kubectl_manifest" "mysql_service" {
  yaml_body = templatefile("${path.module}/k8s_templates/mysql-service.yaml.tpl", {
    sql_namespace = var.sql_namespace
  })
  depends_on = [kubectl_manifest.mysql_namespace]
}


resource "kubectl_manifest" "mysql_deployment" {
  yaml_body = templatefile("${path.module}/k8s_templates/mysql-deployment.yaml.tpl", {
    sql_namespace         = var.sql_namespace,
    db_root_password      = local.db_root_password,
  })
  depends_on = [kubectl_manifest.mysql_pvc, kubectl_manifest.mysql_service]
}

# Create a Google Cloud Storage bucket

resource "google_storage_bucket" "mysql_files_bucket" {
  name     = "${var.project_id}-lexitrail-mysql-files"
  location = var.region

  # Enable uniform bucket-level access
  uniform_bucket_level_access = true
  depends_on = [
    google_project_iam_member.compute_roles,
    google_project_iam_member.cloudbuild_roles
  ]
}

# Grant the GSA permission to read from the storage bucket
resource "google_project_iam_member" "bucket_access" {
  project = var.project_id
  role   = "roles/storage.admin"
  member = "serviceAccount:${google_service_account.lexitrail_storage_sa.email}"
}


# Use google_project_iam_member for binding instead of google_iam_policy
resource "google_service_account_iam_member" "lexitrail_workload_identity_binding" {
  service_account_id = google_service_account.lexitrail_storage_sa.name
  role    = "roles/iam.workloadIdentityUser"
  member  = "serviceAccount:${var.project_id}.svc.id.goog[mysql/default]"
}

# Upload schema.sql to the bucket
resource "google_storage_bucket_object" "schema_tables_sql" {
  name   = "schema-tables.sql"
  bucket = google_storage_bucket.mysql_files_bucket.name
  source = "${path.module}/schema-tables.sql"  # Path to local schema.sql
}

resource "google_storage_bucket_object" "schema_data_sql" {
  name   = "schema-data.sql"
  bucket = google_storage_bucket.mysql_files_bucket.name
  source = "${path.module}/schema-data.sql"  # Path to local schema.sql
}

# Upload wordsets.csv to the bucket
resource "google_storage_bucket_object" "wordsets_csv" {
  name   = "csv/wordsets.csv"
  bucket = google_storage_bucket.mysql_files_bucket.name
  source = "${path.module}/csv/wordsets.csv"  # Path to local wordsets.csv
}

# Upload words.csv to the bucket
resource "google_storage_bucket_object" "words_csv" {
  name   = "csv/words.csv"
  bucket = google_storage_bucket.mysql_files_bucket.name
  source = "${path.module}/csv/words.csv"  # Path to local words.csv
}

# Output the bucket name for the Kubernetes job to use
output "mysql_files_bucket_name" {
  value = google_storage_bucket.mysql_files_bucket.name
}


resource "kubectl_manifest" "mysql_schema_and_data_job" {
  yaml_body = templatefile("${path.module}/k8s_templates/mysql-schema-and-data-job.yaml.tpl", {
    sql_namespace         = var.sql_namespace,
    db_root_password      = local.db_root_password,
    mysql_files_bucket    = google_storage_bucket.mysql_files_bucket.name  # Pass bucket name
    db_name               = var.db_name
  })
  depends_on = [
    kubectl_manifest.mysql_deployment,
    google_storage_bucket_object.schema_tables_sql,
    google_storage_bucket_object.schema_data_sql,
    google_storage_bucket_object.wordsets_csv,
    google_storage_bucket_object.words_csv,
    google_service_account_iam_member.lexitrail_workload_identity_binding,
    google_project_iam_member.bucket_access
  ]
}


# Python backend

# Cloud Build Execution for Backend Flask service

resource "null_resource" "backend_cloud_build" {
  triggers = {
    files_hash = sha1(join("", [for f in fileset(path.root, "../backend/**") : filesha1(f)]))
  }

  provisioner "local-exec" {
    command = <<EOT
      gcloud builds submit --project ${var.project_id} \
                           --tag ${var.region}-docker.pkg.dev/${var.project_id}/${var.repository_id}/${var.backend_container_name}:latest \
                           ../backend/
    EOT
  }
  depends_on = [
    google_project_iam_member.compute_roles,
    google_project_iam_member.cloudbuild_roles,
    google_artifact_registry_repository.my_repo  # Ensure artifact registry is available
  ]
}

# Backend Namespace in GKE
resource "kubectl_manifest" "backend_namespace" {
  yaml_body = templatefile("${path.module}/k8s_templates/backend-namespace.yaml.tpl", {
    backend_namespace = var.backend_namespace
  })
  depends_on = [
    google_container_cluster.autopilot_cluster  # Ensure GKE cluster is created
  ]
}

# Backend Deployment in GKE
resource "kubectl_manifest" "backend_deployment" {
  yaml_body = templatefile("${path.module}/k8s_templates/backend-deployment.yaml.tpl", {
    project_id        = var.project_id,
    container_name    = var.backend_container_name,
    repo_name         = var.repository_id,
    region            = var.region,
    backend_namespace = var.backend_namespace
  })
  depends_on = [
    kubectl_manifest.backend_namespace,        # Ensure backend namespace exists
    null_resource.backend_cloud_build          # Ensure backend image is built and pushed
  ]
}

# Backend Service in GKE
resource "kubectl_manifest" "backend_service" {
  yaml_body = templatefile("${path.module}/k8s_templates/backend-service.yaml.tpl", {
    backend_namespace = var.backend_namespace
  })
  depends_on = [
    kubectl_manifest.backend_namespace,        # Ensure backend namespace exists
    kubectl_manifest.backend_deployment        # Ensure backend deployment exists
  ]
}

# Backend ConfigMap in GKE
resource "kubectl_manifest" "backend_configmap" {
  yaml_body = templatefile("${path.module}/k8s_templates/backend-configmap.yaml.tpl", {
    backend_namespace = var.backend_namespace,
    mysql_files_bucket = google_storage_bucket.mysql_files_bucket.name,
    sql_namespace = var.sql_namespace,
    database_name = var.db_name
  })
  depends_on = [
    kubectl_manifest.backend_namespace,        # Ensure backend namespace exists
    google_storage_bucket.mysql_files_bucket   # Ensure the storage bucket is created
  ]
}

# Backend Secret in GKE
resource "kubectl_manifest" "backend_secret" {
  yaml_body = templatefile("${path.module}/k8s_templates/backend-secret.yaml.tpl", {
    backend_namespace = var.backend_namespace,
    db_root_password  = base64encode(local.db_root_password)  # Perform the base64 encoding here
  })
  depends_on = [kubectl_manifest.backend_namespace]
}





