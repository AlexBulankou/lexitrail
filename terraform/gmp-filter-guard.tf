# AC1 (#7) — durable guard for the GMP cadvisor metric-drop filter.
#
# Issue #5 ask #1 trims Cloud Monitoring cost (~$15-18/mo) by dropping
# high-cardinality container_* cadvisor series from Google Managed Prometheus,
# keeping only 5 essentials. The trim lives in collection.filter of the
# gmp-public OperatorConfig named "config" — an addon-owned resource a
# managed-prometheus addon upgrade can silently reset to defaults.
#
# AC2 (verify_gmp_filter.sh) + AC3 (docs/runbooks/gmp-cadvisor-filter.md) gave
# us detection + a documented one-command recovery. This file is AC1: the
# in-cluster CronJob that re-applies the patch automatically, closing the loop
# to zero-touch.
#
# Design (Option A from the runbook): a minimal ServiceAccount + namespaced
# Role/RoleBinding (get/patch on operatorconfig "config" only) + a CronJob that
# issues the idempotent merge-patch. Patching is a pure Kubernetes API call, so
# no GCP service account / Workload Identity is needed. It is additive — it does
# NOT adopt the OperatorConfig into terraform state (which would fight the addon
# controller; that is the rejected Option B).

variable "gmp_guard_image" {
  description = "kubectl image for the gmp-filter-guard CronJob. Defaults to the official, version-pinned Kubernetes kubectl image (registry.k8s.io — no Docker Hub / bitnami dependency, which is being deprecated). v1.35.0 matches the cluster's GKE 1.35 control plane; a stable `patch` tolerates skew regardless. Pin to a digest for further supply-chain hardening."
  type        = string
  default     = "registry.k8s.io/kubectl:v1.35.0"
}

variable "gmp_guard_schedule" {
  description = "Cron schedule for the filter re-apply guard (every 6h by default)."
  type        = string
  default     = "0 */6 * * *"
}

locals {
  gmp_guard_namespace = "gmp-public"
  gmp_guard_sa_name   = "gmp-filter-guard"
  gmp_guard_role_name = "gmp-filter-guard"

  # Keep-list — MUST stay identical to docs/runbooks/gmp-cadvisor-filter.md and
  # verify_gmp_filter.sh. Rule 1 drops every container_* series; rule 2
  # re-admits the 5 essentials. jsonencode produces exactly the runbook's
  # merge-patch payload.
  gmp_filter_matchoneof = [
    "{__name__!~\"container_.*\"}",
    "{__name__=~\"container_(cpu_usage_seconds_total|memory_working_set_bytes|memory_usage_bytes|network_receive_bytes_total|network_transmit_bytes_total)\"}",
  ]
  gmp_filter_patch = jsonencode({
    collection = {
      filter = {
        matchOneOf = local.gmp_filter_matchoneof
      }
    }
  })
}

# gmp-public is created by the managed-prometheus addon — we create resources in
# it, not the namespace itself.

resource "kubectl_manifest" "gmp_filter_guard_sa" {
  yaml_body = templatefile("${path.module}/k8s_templates/gmp-filter-guard-service-account.yaml.tpl", {
    sa_name   = local.gmp_guard_sa_name
    namespace = local.gmp_guard_namespace
  })
  depends_on = [google_container_cluster.autopilot_cluster]
}

resource "kubectl_manifest" "gmp_filter_guard_role" {
  yaml_body = templatefile("${path.module}/k8s_templates/gmp-filter-guard-role.yaml.tpl", {
    role_name = local.gmp_guard_role_name
    namespace = local.gmp_guard_namespace
  })
  depends_on = [google_container_cluster.autopilot_cluster]
}

resource "kubectl_manifest" "gmp_filter_guard_rolebinding" {
  yaml_body = templatefile("${path.module}/k8s_templates/gmp-filter-guard-rolebinding.yaml.tpl", {
    role_name = local.gmp_guard_role_name
    sa_name   = local.gmp_guard_sa_name
    namespace = local.gmp_guard_namespace
  })
  depends_on = [
    kubectl_manifest.gmp_filter_guard_sa,
    kubectl_manifest.gmp_filter_guard_role,
  ]
}

resource "kubectl_manifest" "gmp_filter_guard_cronjob" {
  yaml_body = templatefile("${path.module}/k8s_templates/gmp-filter-guard-cronjob.yaml.tpl", {
    namespace    = local.gmp_guard_namespace
    sa_name      = local.gmp_guard_sa_name
    schedule     = var.gmp_guard_schedule
    image        = var.gmp_guard_image
    filter_patch = local.gmp_filter_patch
  })
  depends_on = [kubectl_manifest.gmp_filter_guard_rolebinding]
}
