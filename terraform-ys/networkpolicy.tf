# Per-workload ingress allow for the lexitrail tenant (issue-905 step 2). The
# my-hermes terraform/tenants root puts default-deny-ingress + allow-same-namespace
# on this ns (baseline isolation); NetworkPolicies are additive, so this allow rule
# composes with the baseline. Same ownership boundary used for the orch ns
# (ensemble#6759): the NS + baseline = tenants root; per-workload allow = here.
#
# Without this, GKE LB health-check probes + Google front-ends are blocked by the
# baseline default-deny-ingress → backend NEGs read UNHEALTHY and the ingress never
# serves (HC2 #904 catch). 35.191.0.0/16 + 130.211.0.0/22 are GCP's LB health-check
# and GFE source ranges.
resource "kubernetes_network_policy" "allow_lb_healthcheck" {
  metadata {
    name      = "allow-lb-healthcheck"
    namespace = var.namespace
  }

  spec {
    pod_selector {} # all lexitrail pods (UI + backend serve via GKE ingress)
    policy_types = ["Ingress"]
    ingress {
      from {
        ip_block { cidr = "35.191.0.0/16" } # GCP LB health checks
      }
      from {
        ip_block { cidr = "130.211.0.0/22" } # GCP front-end proxies
      }
    }
  }
}
