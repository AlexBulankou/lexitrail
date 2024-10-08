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

resource "google_project_iam_member" "bucket_access" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.lexitrail_storage_sa.email}"
}

resource "google_service_account_iam_member" "lexitrail_workload_identity_binding" {
  service_account_id = google_service_account.lexitrail_storage_sa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[mysql/default]"
}