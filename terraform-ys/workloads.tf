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
    LOCATION           = var.ys_region
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
    replicas = 1
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
          image = "${var.ys_region}-docker.pkg.dev/${var.lexitrail_project_id}/lexitrail-repo/lexitrail-backend:${var.image_tag}"

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

# ---------- UI ----------

resource "kubernetes_deployment_v1" "ui" {
  metadata {
    name      = "lexitrail-ui-deployment"
    namespace = var.namespace
    labels    = { app = "lexitrail-ui" }
  }

  spec {
    replicas = 1
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
          image = "${var.ys_region}-docker.pkg.dev/${var.lexitrail_project_id}/lexitrail-repo/lexitrail-ui:${var.image_tag}"

          port {
            container_port = 3000
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
