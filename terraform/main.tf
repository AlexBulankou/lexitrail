terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.6.0"
    }
    kubectl = {
      source  = "alekc/kubectl"
      version = "~> 2.0.4"
    }
    dotenv = {
      source  = "germanbrew/dotenv"
      version = "~> 1.1.4"
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

provider "dotenv" {}

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
  ui_files_hash = sha1(join("", [for f in fileset(path.root, "../ui/**") : filesha1(f)]))
  backend_files_hash = sha1(join("", [for f in fileset(path.root, "../backend/**") : filesha1(f)]))
}

resource "google_service_account" "lexitrail_storage_sa" {
  account_id   = "lexitrail-storage-sa"
  display_name = "Lexitrail Storage Service Account"
}