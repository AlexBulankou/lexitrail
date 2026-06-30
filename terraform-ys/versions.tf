# WS2 (my-hermes#905) — parallel terraform config that re-homes Lexitrail onto
# the shared ys-autopilot cluster (yojowa-claw). SEPARATE root from ../terraform
# (which manages the live standalone cluster) — this one NEVER touches that state,
# so parallel-run + DNS-flip + rollback stay safe. The live root is decommissioned
# only after cutover + soak.
#
# PREREQ: ys-autopilot exists (my-hermes#901/#902) and the apply host's egress is
# in its master_authorized_cidrs (this root talks to the CP endpoint).
terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
    kubectl = {
      source  = "alekc/kubectl"
      version = "~> 2.0"
    }
  }
}
