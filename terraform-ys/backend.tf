# Remote state in the shared claw GCS bucket (epod-d-sa has objectAdmin), own
# prefix so it never collides with the cluster (ys-cluster) or tenant (ys-tenants)
# roots. The live ../terraform root uses LOCAL state and is untouched by this.
terraform {
  backend "gcs" {
    bucket = "yojowa-claw-tf-state"
    prefix = "lexitrail-ys"
  }
}
