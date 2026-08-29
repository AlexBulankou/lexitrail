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
    # lexitrail#123: a single-pod deployment on Autopilot has zero NEG-healthy
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
          name = "lexitrail-backend"
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

          # issue-164: WITHOUT this, liveness starts counting at t+30s and kills
          # the container at ~t+60-80s -- before the app has always finished
          # importing. Measured on this exact deployment/image, two cold starts:
          #
          #   kb8nr 2026-08-20  first serving at +67s  -> SIGKILL 137 at +81s
          #   lfmws 2026-08-22  first serving at +37s  -> survived, ~1 failure spare
          #
          # Same image digest; the variable is Python import time, which moves
          # with node and image-cache state. So every cold start was a coin-toss.
          #
          # A startup_probe is the correct instrument rather than a bigger
          # liveness initial_delay: while it is active Kubernetes SUSPENDS both
          # liveness and readiness, and once it succeeds liveness takes over at
          # its normal cadence. Raising initial_delay instead would buy the same
          # startup headroom by permanently delaying detection of a genuine
          # mid-life hang, which is the thing liveness exists for.
          #
          # 10 + (30 x 10) = up to 310s to bind, ~4.6x the worst start observed.
          # Generous on purpose: the failure this replaces is a kill loop on a
          # healthy app, and the cost of the slack is only a slower first
          # detection of a container that never binds at all.
          startup_probe {
            http_get {
              path = "/health"
              port = 80
            }
            initial_delay_seconds = 10
            period_seconds        = 10
            timeout_seconds       = 10
            failure_threshold     = 30
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
              # issue-276 AC1: 200m -> 1. At 200m the container was throttled in
              # 98.7% of every scheduling period and spent MORE wall time frozen
              # (130.9 s) than running (62.2 s), which is the whole gap between the
              # algorithm's 0.37 ms/word and production's ~64 ms/word (#266).
              #
              # This is FREE. Autopilot bills REQUESTS, and requests are untouched at
              # 100m. Probe-verified against the live webhook before applying, with a
              # positive control: this exact shape passes `--dry-run=server` UNMUTATED
              # while a shape missing ephemeral-storage is visibly mutated, so the
              # unmutated echo means "the webhook saw it and left it alone" rather than
              # "no webhook ran". Probe a BARE POD, not the Deployment -- dry-running
              # the Deployment returns a confident wrong answer.
              #
              # Measured after the roll, against the still-running 200m pod as a
              # simultaneous same-image control:
              #   200m  nr_throttled 3086/3126 (98.7%)  throttled 130.9 s / usage 62.2 s
              #   1      nr_throttled    7/841 ( 0.8%)  throttled   0.33 s / usage 50.8 s
              #
              # ⚠️ Do NOT bundle a memory raise into this edit. Autopilot enforces a
              # cpu:memory ratio and reports a violation as a WARNING, not an error, so
              # a bundled change reports as free and surfaces a cost later with nothing
              # pointing at it. AC3 (memory) is a separate decision.
              cpu                 = "1"
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

# lexitrail#123: minAvailable=1 stops Autopilot's node-consolidation evictions
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
    # lexitrail#123: see the identical comment on the backend deployment above.
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
          name = "lexitrail-ui"
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

          # issue-124: keep serving while the load balancer stops routing here.
          #
          # #123 gave this Deployment 2 replicas and a PDB, and deleting one pod
          # STILL produced ~10s of 503s from lexitrail.com while the surviving
          # replica was Ready throughout. That is the container-native LB drain
          # gap, not a capacity gap: the pod enters Terminating and stops
          # serving IMMEDIATELY, while the GCLB's NEG still has its endpoint
          # programmed and keeps sending it traffic for a few more seconds.
          # Adding replicas cannot fix it — the dying endpoint is still in the
          # NEG. The measured asymmetry says the same thing: the same test
          # against lexitrail-backend dropped 0 of 20 requests, and the backend
          # is not fronted by a NEG.
          #
          # So the pod must OUTLIVE its own deprogramming. `preStop` runs before
          # SIGTERM, so the container keeps answering for the sleep's duration
          # while the NEG drops it.
          #
          # 30s against a ~10s measured blip is deliberate margin, not a guess
          # at the exact number: NEG propagation varies with LB state and being
          # 20s generous costs a slower rollout, while being 2s short costs
          # user-visible 503s on every deploy. Tune DOWN only against a measured
          # run, never up-front.
          lifecycle {
            pre_stop {
              exec {
                command = ["/bin/sleep", "30"]
              }
            }
          }
        }

        # Must exceed the preStop sleep, or the kubelet SIGKILLs the pod
        # mid-drain and the sleep buys nothing. 45 = 30 + headroom for the
        # container's own shutdown.
        termination_grace_period_seconds = 45
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

# lexitrail#123: see the identical comment on the backend PDB above.
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
