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

variable "sql_namespace" {
  description = "Kubernetes namespace to deploy the resources"
  type        = string
  default     = "mysql"
}

variable "wordsets_csv_path" {
  description = "Path to the CSV file containing wordsets data"
  type        = string
  default     = "csv/wordsets.csv"
}

variable "words_csv_path" {
  description = "Path to the CSV file containing words data"
  type        = string
  default     = "csv/words.csv"
}