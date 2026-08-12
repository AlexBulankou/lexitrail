# WS2 increment 3b/3c (my-hermes#905) — Lexitrail backend API + UI workloads on
# ys-autopilot, in the collapsed `lexitrail` ns (D1). Mirrors the LIVE workloads
# (backend: `backend` ns; UI: `default` ns) into the single ns, pulling the same
# cross-project images from lexitrail/lexitrail-repo (D4; reader granted in iam.tf).
#
# The one config adaptation vs live: SQL_NAMESPACE. Live = "mysql" (MySQL lived in
# its own `mysql` ns). Here the MySQL StatefulSet (mysql.tf) is in THIS ns, so the
# backend resolves it at `mysql.${SQL_NAMESPACE}.svc.cluster.local` →
# `mysql.lexitrail...`. We set SQL_NAMESPACE = var.namespace so the collapse is
# automatic and the value can never drift from where MySQL actually runs.
#
# Brought up against the FRESH empty MySQL (mysql.tf) — the backend's /health may
# report DB-empty until the exec-step-4 dump→restore lands the live data; the
# load-bearing smoke-test for THIS increment is "pods pull + run + the cross-proj
# WI identity works", not "app fully serves live data".

# ---------- Backend ----------

# Non-secret config (mirrors live backend-config). SQL_NAMESPACE is the D1 adaptation.
resource "kubernetes_config_map_v1" "backend_config" {
  metadata {
    name      = "backend-config"
    namespace = var.namespace
  }
  data = {
    DATABASE_NAME      = var.database_name
    GOOGLE_CLIENT_ID   = var.google_client_id
    LOCATION           = var.location
    MYSQL_FILES_BUCKET = var.mysql_files_bucket
    PROJECT_ID         = var.lexitrail_project_id
    SQL_NAMESPACE      = var.namespace # D1 collapse: MySQL is in THIS ns now
  }
}

# Root DB password (live backend-secret has only DB_ROOT_PASSWORD — the backend
# connects as root, no separate app user). Same var as mysql.tf so the backend's
# credential always matches the DB it talks to.
resource "kubernetes_secret_v1" "backend_secret" {
  metadata {
    name      = "backend-secret"
    namespace = var.namespace
  }
  data = {
    DB_ROOT_PASSWORD = var.db_root_password
  }
  type = "Opaque"
}

resource "kubernetes_deployment_v1" "backend" {
  metadata {
    name      = "lexitrail-backend"
    namespace = var.namespace
    labels    = { app = "lexitrail-backend" }
  }

  spec {
    # my-hermes#123: a single-pod deployment on Autopilot has zero NEG-healthy
    # endpoints during any node consolidation/eviction, which is a full-site
    # 503 window, not a capacity dip (observed live 2026-08-12, ~60-90s).
    # 2 replicas + the PDB below (min_available=1) closes the gap: the PDB
    # blocks a voluntary eviction from taking BOTH pods at once.
    replicas = 2
    selector {
      match_labels = { app = "lexitrail-backend" }
    }

    template {
      metadata {
        labels = { app = "lexitrail-backend" }
      }
      spec {
        # The WI-annotated KSA from iam.tf — gives the pod the lexitrail-sa GSA
        # identity for cross-project GCS (MYSQL_FILES_BUCKET) + Vertex AI.
        service_account_name = "lexitrail-backend"

        container {
          name  = "lexitrail-backend"
          # Registry hostname is the AR repo's LOCATION (lexitrail-side), NOT the
          # ys region — same decoupling as the iam.tf AR grant (HC2 #15/#16 catch).
          image = "${var.lexitrail_repo_location}-docker.pkg.dev/${var.lexitrail_project_id}/lexitrail-repo/lexitrail-backend:${var.image_tag}"

          port {
            container_port = 80
          }

          env {
            name  = "PORT"
            value = "80"
          }

          # 6 keys from the ConfigMap + the root password from the Secret.
          dynamic "env" {
            for_each = toset(["MYSQL_FILES_BUCKET", "SQL_NAMESPACE", "DATABASE_NAME", "GOOGLE_CLIENT_ID", "PROJECT_ID", "LOCATION"])
            content {
              name = env.value
              value_from {
                config_map_key_ref {
                  name = kubernetes_config_map_v1.backend_config.metadata[0].name
                  key  = env.value
                }
              }
            }
          }

          env {
            name = "DB_ROOT_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.backend_secret.metadata[0].name
                key  = "DB_ROOT_PASSWORD"
              }
            }
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 80
            }
            initial_delay_seconds = 30
            period_seconds        = 10
            timeout_seconds       = 10
            failure_threshold     = 3
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = 80
            }
            initial_delay_seconds = 30
            period_seconds        = 10
            timeout_seconds       = 10
            failure_threshold     = 3
          }

          resources {
            # ephemeral-storage explicit to match Autopilot's injection (mirrors
            # live; keeps cpu/memory under drift-detection — see mysql.tf header).
            requests = {
              cpu                 = "100m"
              memory              = "256Mi"
              "ephemeral-storage" = "1Gi"
            }
            limits = {
              cpu                 = "200m"
              memory              = "512Mi"
              "ephemeral-storage" = "1Gi"
            }
          }
        }
      }
    }
  }

  # Same Autopilot-webhook churn handling as mysql.tf.
  lifecycle {
    ignore_changes = [
      metadata[0].annotations,
      spec[0].template[0].metadata[0].annotations,
      spec[0].template[0].spec[0].security_context,
      spec[0].template[0].spec[0].container[0].security_context,
      spec[0].template[0].spec[0].toleration,
      # issue-87: terraform does NOT own the image, so it must not assert one.
      # Live is digest-pinned (@sha256:3519ee7c…) while this file declares a TAG,
      # and nothing in this repo sets either: there is no deploy script, no
      # `kubectl set image`, no cloudbuild.yaml and no build trigger. The digests
      # were pinned by hand. Without this, every plan shows `~ container.image`
      # and an apply would silently UN-PIN both Deployments onto a floating tag —
      # against decipher#2616 (`reporter:alx`, pin ns-fl images by digest).
      # Adopting the digest here instead was rejected: with no updater it
      # re-drifts on the very next hand-deploy, which moves the problem rather
      # than fixing it. The real fix is a deploy path (issue-87 option (c)).
      spec[0].template[0].spec[0].container[0].image,
    ]
  }
}

resource "kubernetes_service_v1" "backend" {
  metadata {
    name      = "lexitrail-backend-service"
    namespace = var.namespace
  }
  spec {
    selector = { app = "lexitrail-backend" }
    port {
      port        = 80
      target_port = 80
    }
    type = "ClusterIP"
  }

  lifecycle {
    ignore_changes = [metadata[0].annotations]
  }
}

# my-hermes#123: minAvailable=1 stops Autopilot's node-consolidation evictions
# (a "voluntary" disruption per the K8s eviction API) from taking the ONLY
# other replica down while a scale-down is already in flight elsewhere.
# It does not cover involuntary disruptions (a node dying outright) — that
# risk is what the 2nd replica itself (not the PDB) primarily addresses.
resource "kubernetes_pod_disruption_budget_v1" "backend" {
  metadata {
    name      = "lexitrail-backend-pdb"
    namespace = var.namespace
  }
  spec {
    min_available = 1
    selector {
      match_labels = { app = "lexitrail-backend" }
    }
  }
}

# ---------- UI ----------

resource "kubernetes_deployment_v1" "ui" {
  metadata {
    name      = "lexitrail-ui-deployment"
    namespace = var.namespace
    labels    = { app = "lexitrail-ui" }
  }

  spec {
    # my-hermes#123: see the identical comment on the backend deployment above.
    replicas = 2
    selector {
      match_labels = { app = "lexitrail-ui" }
    }

    template {
      metadata {
        labels = { app = "lexitrail-ui" }
      }
      spec {
        container {
          name  = "lexitrail-ui"
          # Registry hostname = repo location (lexitrail-side), not ys_region (HC2 #16).
          image = "${var.lexitrail_repo_location}-docker.pkg.dev/${var.lexitrail_project_id}/lexitrail-repo/lexitrail-ui:${var.image_tag}"

          port {
            container_port = 3000
          }

          # Readiness probe (HC2 #16 nb): live UI had none, but once an ingress
          # fronts the Service (incr-4) the LB should only route to ready pods.
          # TCP :3000 (the UI serves static assets; no dedicated health path).
          readiness_probe {
            tcp_socket {
              port = 3000
            }
            initial_delay_seconds = 5
            period_seconds        = 10
          }

          resources {
            requests = {
              cpu                 = "50m"
              memory              = "128Mi"
              "ephemeral-storage" = "1Gi"
            }
            limits = {
              cpu                 = "100m"
              memory              = "256Mi"
              "ephemeral-storage" = "1Gi"
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      metadata[0].annotations,
      spec[0].template[0].metadata[0].annotations,
      spec[0].template[0].spec[0].security_context,
      spec[0].template[0].spec[0].container[0].security_context,
      spec[0].template[0].spec[0].toleration,
      # issue-87 — same reasoning as the backend above. Live UI is
      # @sha256:7449639f… at revision 14, all fourteen set by hand.
      spec[0].template[0].spec[0].container[0].image,
    ]
  }
}

resource "kubernetes_service_v1" "ui" {
  metadata {
    name      = "lexitrail-ui"
    namespace = var.namespace
  }
  spec {
    selector = { app = "lexitrail-ui" }
    port {
      port        = 80
      target_port = 3000 # UI container listens on 3000; service fronts it on 80
    }
    type = "ClusterIP"
  }

  lifecycle {
    ignore_changes = [metadata[0].annotations]
  }
}

# my-hermes#123: see the identical comment on the backend PDB above.
resource "kubernetes_pod_disruption_budget_v1" "ui" {
  metadata {
    name      = "lexitrail-ui-pdb"
    namespace = var.namespace
  }
  spec {
    min_available = 1
    selector {
      match_labels = { app = "lexitrail-ui" }
    }
  }
}
