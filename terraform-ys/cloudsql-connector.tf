# lexitrail#358 — the CONNECTOR slice: what lets the cluster reach the managed
# Cloud SQL instance created in cloudsql.tf. Provisioning it was step 1; nothing
# in the cluster could reach it until this file.
#
# 🔴 THIS FILE DOES NOT CUT ANYTHING OVER. It adds a grant and a proxy Deployment
# that nothing points at yet. The cutover is a separate, deliberate act: flipping
# `Service/mysql`'s selector (see CUTOVER-RUNBOOK-CLOUDSQL.md §5). Applying this
# is therefore safe at any time — the backend keeps talking to mysql-0.
#
# WHY A DEPLOYMENT + SERVICE SWAP, NOT A SIDECAR
# ----------------------------------------------
# The app builds its URI in code, with the host as a template:
#
#   backend/app/config.py:
#     'mysql+pymysql://root:{}@mysql.{}.svc.cluster.local:3306/{}'
#         .format(DB_ROOT_PASSWORD, os.getenv('SQL_NAMESPACE'), DATABASE_NAME)
#
# There is no DATABASE_URL, and SQL_NAMESPACE fills the NAMESPACE slot, so no
# value of it yields any host but `mysql.<ns>.svc.cluster.local`. A sidecar
# listens on 127.0.0.1 and would need a backend/** change + image rebuild +
# app redeploy INSIDE the DB window — two variables at once, rollback = redeploy.
#
# ⚠️ config.py's `else` branch dials `localhost` and reads like sidecar support
# already exists. It does not: its gate is KUBERNETES_SERVICE_HOST, which
# Kubernetes injects into every pod, so in-cluster that branch is unreachable.
# It is the local-dev path. Do not "enable" it.
#
# Pointing the existing headless Service at a proxy Deployment keeps the hostname
# the app already dials, so the backend never learns anything changed, and
# rollback is flipping a selector — seconds, no build.

# (1) The grant. MEASURED, not assumed: a scratch proxy running under the REAL
# `lexitrail-backend` KSA authorized via Workload Identity, accepted a connection
# through a headless Service, and then failed OUTBOUND with
#
#   403 boss::NOT_AUTHORIZED ... missing permission cloudsql.instances.get
#       on resource instances/lexitrail-mysql
#
# so this binding is the whole remaining connectivity gap. Reusing the existing
# `lexitrail-sa` GSA (iam.tf reads it) rather than minting one keeps a single
# identity owning the bucket / Vertex / SQL grants, same rationale as iam.tf's.
#
# 🔑 The CLIENT-side error was uninformative — `ERROR 2013 Lost connection ...
# reading initial communication packet`, which reads like a network or TLS fault
# and sends you to the three NetworkPolicies in this ns, where you find a
# plausible story and lose the window. The proxy's own log is what names the
# cause. If this ever regresses, read the PROXY log, not the client's.
resource "google_project_iam_member" "backend_gsa_cloudsql_client" {
  project = var.lexitrail_project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${data.google_service_account.lexitrail_backend_gsa.email}"
}

# (2) The proxy. Its own Deployment rather than a sidecar, per the header.
#
# Runs under the SAME KSA as the backend (`lexitrail-backend`, iam.tf), so it
# inherits the Workload Identity binding already in place and needs no key file.
# That is also why the probe was run under that KSA and not a convenience one:
# a probe under a different identity would have proven nothing about this path.
resource "kubernetes_deployment_v1" "cloudsql_proxy" {
  metadata {
    name      = "cloudsql-proxy"
    namespace = var.namespace
    labels    = { app = "cloudsql-proxy" }
  }

  spec {
    # 2 replicas: during the cutover this sits on the app's data path, so a
    # single replica would make a proxy restart a DB outage. The instance is
    # single-zone; this is about the PROXY's availability, not the DB's.
    replicas = 2

    selector {
      match_labels = { app = "cloudsql-proxy" }
    }

    template {
      metadata {
        labels = { app = "cloudsql-proxy" }
      }

      spec {
        service_account_name = "lexitrail-backend"

        container {
          name  = "cloud-sql-proxy"
          image = "gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.8.0"

          # --address=0.0.0.0, NOT the 127.0.0.1 default: as a Deployment behind
          # a Service the listener must accept connections from OTHER pods. The
          # default is correct for a sidecar and would silently accept nothing
          # here (the Service would have endpoints and every dial would hang).
          args = [
            "--address=0.0.0.0",
            "--port=3306",
            # DERIVED, not reconstructed: `connection_name` IS the
            # project:region:instance string the proxy wants, so it cannot drift
            # from the instance if the region or name ever changes.
            google_sql_database_instance.lexitrail.connection_name,
          ]

          port {
            container_port = 3306
          }

          # The proxy is a TCP forwarder; these are the documented small-footprint
          # values and were enough for the probe. Revisit if the cutover shows
          # throttling under real query load -- it has NOT been load-tested.
          resources {
            requests = { cpu = "50m", memory = "64Mi" }
            limits   = { cpu = "200m", memory = "128Mi" }
          }

          # Liveness only, deliberately -- and NOT a DB-dependent readiness probe.
          # workloads.tf records why for the backend (issue-301): a DB-dependent
          # liveness probe converts a brief DB blip into a total outage by
          # restarting every replica. The same reasoning applies here, more so:
          # this pod IS the path to the DB, so a probe that fails when the DB is
          # unreachable would restart the thing that reconnects to it.
          liveness_probe {
            tcp_socket { port = 3306 }
            initial_delay_seconds = 10
            period_seconds        = 30
          }
        }
      }
    }
  }
}
