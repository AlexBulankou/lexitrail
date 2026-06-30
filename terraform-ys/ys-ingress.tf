# WS2 increment 4b (my-hermes#905) — GKE Ingresses for the Lexitrail UI + backend
# on ys-autopilot. Mirrors the live ingresses (class=gce external Application LB),
# but TLS comes from the Certificate Manager cert-map (ys-tls.tf) via the
# `networking.gke.io/certmap` annotation instead of a GKE ManagedCertificate — so
# the cert can be ACTIVE before cutover (no HTTPS-down window; HC2 #905 catch 2).
#
# These create real external LBs in yojowa-claw NOW (they get the reserved static
# IPs), but receive NO live traffic until the incr-6 cutover A-flip — so standing
# them up early is safe + lets them warm up. HTTP routing is smoke-testable now;
# HTTPS goes green once the certs provision (gated on Alex's TopDNS CNAMEs).
#
# Health checks: GKE Ingress derives the backend health check from each Service's
# pod readiness probe (backend: HTTP /health:80; UI: TCP :3000 — added in
# workloads.tf per HC2 #16 nb). The incr-1 allow-lb-healthcheck NetworkPolicy
# (35.191.0.0/16 + 130.211.0.0/22) lets the LB probes reach the pods.

# HTTP→HTTPS redirect for the UI (mirrors live's FrontendConfig). The backend
# ingress is HTTPS-only (allow-http=false) so it needs no redirect.
resource "kubectl_manifest" "frontend_config" {
  yaml_body = <<-YAML
    apiVersion: networking.gke.io/v1beta1
    kind: FrontendConfig
    metadata:
      name: lexitrail-ys-frontend
      namespace: ${var.namespace}
    spec:
      redirectToHttps:
        enabled: true
  YAML
}

resource "kubernetes_ingress_v1" "ui" {
  metadata {
    name      = "lexitrail-ys-ui-ingress"
    namespace = var.namespace
    annotations = {
      "kubernetes.io/ingress.class"                 = "gce"
      "kubernetes.io/ingress.global-static-ip-name" = google_compute_global_address.ui.name
      "networking.gke.io/certmap"                   = google_certificate_manager_certificate_map.lexitrail.name
      "kubernetes.io/ingress.allow-http"            = "true" # serve HTTP → redirect to HTTPS
      "networking.gke.io/v1beta1.FrontendConfig"    = "lexitrail-ys-frontend"
    }
  }
  spec {
    rule {
      host = "lexitrail.com"
      http {
        path {
          path      = "/*"
          path_type = "ImplementationSpecific"
          backend {
            service {
              name = "lexitrail-ui"
              port { number = 80 }
            }
          }
        }
      }
    }
  }
  lifecycle {
    ignore_changes = [metadata[0].annotations]
  }
}

resource "kubernetes_ingress_v1" "backend" {
  metadata {
    name      = "lexitrail-ys-backend-ingress"
    namespace = var.namespace
    annotations = {
      "kubernetes.io/ingress.class"                 = "gce"
      "kubernetes.io/ingress.global-static-ip-name" = google_compute_global_address.backend.name
      "networking.gke.io/certmap"                   = google_certificate_manager_certificate_map.lexitrail.name
      "kubernetes.io/ingress.allow-http"            = "false" # HTTPS-only, mirrors live backend ingress
    }
  }
  spec {
    rule {
      host = "api.lexitrail.com"
      http {
        path {
          path      = "/*"
          path_type = "ImplementationSpecific"
          backend {
            service {
              name = "lexitrail-backend-service"
              port { number = 80 }
            }
          }
        }
      }
    }
  }
  lifecycle {
    ignore_changes = [metadata[0].annotations]
  }
}
