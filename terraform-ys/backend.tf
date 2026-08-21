# Remote state in the shared claw GCS bucket, own
# prefix so it never collides with the cluster (ys-cluster) or tenant (ys-tenants)
# roots. The live ../terraform root uses LOCAL state and is untouched by this.
#
# my-hermes#1338: this said "epod-d-sa has objectAdmin". That routed an owner to a
# credential nobody holds -- there is no epod-d-sa in the hermes seat's set -- and
# a reader used it to decide WHO should run the import. Verified 2026-08-21 by
# write/read/delete on a scratch prefix, with the identity asserted via tokeninfo
# (a bare gcloud on bp runs as Alex, and --account= is a request that silently
# falls back): the principal that reaches this bucket is the project-native
# hermes-automation@yojowa-claw. Naming a capability rather than a seat, because
# the seat is what went stale.
terraform {
  backend "gcs" {
    bucket = "yojowa-claw-tf-state"
    prefix = "lexitrail-ys"
  }
}
