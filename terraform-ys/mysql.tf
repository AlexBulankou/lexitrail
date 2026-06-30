# WS2 increment 2 (my-hermes#905) — MySQL StatefulSet + headless Service on
# ys-autopilot, in the collapsed `lexitrail` ns (D1).
#
# Mirrors the LIVE workload, not the live ../terraform template. The live cluster
# runs a StatefulSet `mysql` (pod mysql-0, PVC mysql-persistent-storage-mysql-0,
# 5Gi RWO) — the live root's resource is misleadingly named `mysql_deployment` but
# its template is in fact a StatefulSet; its standalone `mysql-pvc` (10Gi) is an
# ORPHAN the StatefulSet never mounts, so it is intentionally NOT reproduced here.
#
# Two deliberate adaptations vs live:
#   1. StorageClass: live pins `storageClassName: standard` (legacy in-tree
#      kubernetes.io/gce-pd, Immediate binding). ys-autopilot DOES expose a
#      `standard` class, but its default + recommended class is `standard-rwo`
#      (pd.csi.storage.gke.io, WaitForFirstConsumer, balanced PD). We OMIT the
#      explicit class so the PVC inherits `standard-rwo` (HC2 #905 review catch 3).
#      Verified live: `kubectl get storageclass` on ys-autopilot shows
#      `standard-rwo (default)`.
#   2. Root password: live hardcodes it in the pod env (plaintext). Here it comes
#      from a Kubernetes Secret populated by the sensitive `db_root_password` var
#      (no default; provided at apply, sourced cluster→cluster per D5 — see
#      README "Open dependency — secrets"). Keeps the secret out of git; it lives
#      only in tf state (access-controlled GCS) and the in-cluster Secret.
#
# This increment brings MySQL up on a FRESH (empty) PVC for smoke-testing the
# cross-project wiring. The live 527-day data is migrated by a later dump→restore
# step (exec order step 4), NOT the GCS seed job (which would clobber live data).

resource "kubernetes_secret_v1" "mysql_root" {
  metadata {
    name      = "mysql-root"
    namespace = var.namespace
  }
  # MYSQL_ROOT_PASSWORD is the only key the StatefulSet needs today; the backend
  # increment (3) can reference the same Secret for its DB connection.
  data = {
    MYSQL_ROOT_PASSWORD = var.db_root_password
  }
  type = "Opaque"
}

# Headless Service (clusterIP None) — gives the StatefulSet a stable per-pod DNS
# name (mysql-0.mysql.lexitrail.svc.cluster.local). Same shape as live.
resource "kubernetes_service_v1" "mysql" {
  metadata {
    name      = "mysql"
    namespace = var.namespace
  }
  spec {
    cluster_ip = "None"
    selector = {
      app = "mysql"
    }
    port {
      port        = 3306
      target_port = 3306
      name        = "mysql"
    }
  }

  # GKE injects `cloud.google.com/neg` (NEG controller) into the Service
  # annotations server-side. Our config doesn't declare it, so without this the
  # provider tries to strip it on every apply and GKE re-adds it — a perpetual
  # no-op diff that masks real drift. Ignore the server-managed annotations.
  lifecycle {
    ignore_changes = [metadata[0].annotations]
  }
}

resource "kubernetes_stateful_set_v1" "mysql" {
  metadata {
    name      = "mysql"
    namespace = var.namespace
    labels = {
      app = "mysql"
    }
  }

  spec {
    service_name = "mysql"
    replicas     = 1

    selector {
      match_labels = {
        app = "mysql"
      }
    }

    template {
      metadata {
        labels = {
          app = "mysql"
        }
      }

      spec {
        # Match live cost profile: schedule on Spot nodes. Autopilot honors the
        # gke-spot node affinity. Trade-off: a Spot preemption briefly restarts
        # the pod (data survives on the PD); acceptable for the live workload's
        # established cost choice. Revisit to standard nodes if the cutover soak
        # shows preemption-driven downtime hurts (candidate follow-up).
        affinity {
          node_affinity {
            required_during_scheduling_ignored_during_execution {
              node_selector_term {
                match_expressions {
                  key      = "cloud.google.com/gke-spot"
                  operator = "In"
                  values   = ["true"]
                }
              }
            }
          }
        }

        container {
          name  = "mysql"
          image = "mysql:8.0"
          args  = ["--local-infile=1"] # server-side LOAD DATA LOCAL INFILE (seed/restore)

          env {
            name = "MYSQL_ROOT_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.mysql_root.metadata[0].name
                key  = "MYSQL_ROOT_PASSWORD"
              }
            }
          }

          port {
            container_port = 3306
            name           = "mysql"
          }

          volume_mount {
            name       = "mysql-persistent-storage"
            mount_path = "/var/lib/mysql"
          }

          readiness_probe {
            exec {
              command = ["mysqladmin", "ping", "-h", "127.0.0.1"]
            }
            initial_delay_seconds = 10
            period_seconds        = 5
          }

          liveness_probe {
            exec {
              command = ["mysqladmin", "ping", "-h", "127.0.0.1"]
            }
            initial_delay_seconds = 30
            period_seconds        = 10
          }

          resources {
            # ephemeral-storage declared explicitly to MATCH Autopilot's injected
            # 1Gi (Autopilot requires it on every container). Declaring it — rather
            # than ignore_changes-ing all of resources — keeps cpu/memory under
            # drift-detection (the cost knob) while silencing the injection churn.
            requests = {
              cpu                 = "200m"
              memory              = "512Mi"
              "ephemeral-storage" = "1Gi"
            }
            limits = {
              cpu                 = "400m"
              memory              = "1024Mi"
              "ephemeral-storage" = "1Gi"
            }
          }
        }
      }
    }

    volume_claim_template {
      metadata {
        name = "mysql-persistent-storage"
      }
      spec {
        access_modes = ["ReadWriteOnce"]
        # storage_class_name intentionally omitted → ys-autopilot default
        # `standard-rwo` (see header comment, adaptation 1).
        resources {
          requests = {
            storage = "5Gi"
          }
        }
      }
    }
  }

  # Autopilot may scale up a node to place the pod; give the rollout headroom.
  timeouts {
    create = "10m"
    update = "10m"
  }

  # Autopilot's admission webhook injects server-side fields our config doesn't
  # declare: the `autopilot.gke.io/*` annotations (StatefulSet + pod-template),
  # a default pod- and container-level security_context (seccomp RuntimeDefault,
  # drop NET_RAW, run_as_non_root defaults), arch tolerations, and a
  # termination_grace_period adjustment. Without ignore_changes the provider
  # strips them every apply and Autopilot re-adds them — a perpetual no-op diff
  # that masks real drift. We ignore exactly the injected fields (NOT
  # container resources — ephemeral-storage is declared explicitly above so
  # cpu/memory stay under drift-detection) so future cutover re-applies plan
  # clean.
  lifecycle {
    ignore_changes = [
      metadata[0].annotations,
      spec[0].template[0].metadata[0].annotations,
      spec[0].template[0].spec[0].security_context,
      spec[0].template[0].spec[0].container[0].security_context,
      spec[0].template[0].spec[0].toleration,
      spec[0].template[0].spec[0].termination_grace_period_seconds,
    ]
  }
}
