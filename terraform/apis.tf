resource "google_project_service" "required_apis" {
  for_each = toset([
    "compute.googleapis.com",
    "cloudbuild.googleapis.com",
    "iam.googleapis.com",
    "artifactregistry.googleapis.com",
    "container.googleapis.com",
    "serviceusage.googleapis.com",
    "aiplatform.googleapis.com"
  ])

  project = local.project_id
  service = each.value

  disable_dependent_services = false
  disable_on_destroy        = false
} 