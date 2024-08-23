variable "project_id" {
  type = string
  default = "alexbu-gke-dev-d"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "fe_bucket_name" {
  type    = string
  default = "lexitrail-ui"
}

variable "cluster_name" {
  type    = string
  default = "lexitrail-cluster"
}

variable "container_name" {
  type    = string
  default = "lexitrail-ui"
}

variable "repository_id" {
  type = string
  default = "lexitrail-repo"
}