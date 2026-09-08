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
            # hc2 #413 review: serve the proxy's OWN health endpoints so
            # readiness can mean "can actually serve", not just "bound a port".
            #
            # ⚠️ --http-address is load-bearing for the SAME reason --address is,
            # and defaults the same wrong way: `--http-address string  Address for
            # Prometheus and health check server (default "localhost")`. Left at
            # the default the kubelet cannot reach the probe, every check fails,
            # and with a readiness probe attached the pod never becomes Ready --
            # so the Service would have NO endpoints. Verified against the 2.8.0
            # binary's own --help, not from memory.
            "--health-check",
            "--http-address=0.0.0.0",
            "--http-port=9090",
            # DERIVED, not reconstructed: `connection_name` IS the
            # project:region:instance string the proxy wants, so it cannot drift
            # from the instance if the region or name ever changes.
            google_sql_database_instance.lexitrail.connection_name,
          ]

          port {
            container_port = 3306
          }

          port {
            name           = "health"
            container_port = 9090
          }

          # The proxy is a TCP forwarder; these are the documented small-footprint
          # values and were enough for the probe. Revisit if the cutover shows
          # throttling under real query load -- it has NOT been load-tested.
          resources {
            requests = { cpu = "50m", memory = "64Mi" }
            limits   = { cpu = "200m", memory = "128Mi" }
          }

          # LIVENESS: restart-on-stuck only. issue-301's reasoning (workloads.tf)
          # applies here more strongly than it does to the backend -- this pod IS
          # the path to the DB, so a liveness probe that fails when Cloud SQL is
          # unreachable would restart the very thing that reconnects to it. So
          # liveness stays on the proxy's own /liveness, which reports the
          # PROCESS, not the upstream.
          liveness_probe {
            http_get {
              path = "/liveness"
              port = 9090
            }
            initial_delay_seconds = 10
            period_seconds        = 30
          }

          # READINESS: gates ROUTING, never restarts -- orthogonal to the above,
          # and NOT covered by issue-301's rationale (hc2 #413 review, correctly).
          # Without it Kubernetes defaults readiness to true the instant the
          # container is Running, so with replicas=2 any future rollout can route
          # live post-cutover traffic to a proxy that is not serving yet.
          #
          # 🔴 A tcp_socket probe on 3306 would NOT be enough, and this session
          # has the direct evidence: the scratch probe logged
          #     "Listening on [::]:3306"
          #     "The proxy has started successfully and is ready for new connections!"
          # and only THEN failed every connection with
          #     403 ... missing permission cloudsql.instances.get
          # The port was bound and accepting the whole time. A TCP check passes on
          # a proxy that cannot reach Cloud SQL at all -- it would have called that
          # pod Ready. /readiness reports whether the proxy can actually SERVE,
          # which is the question routing needs answered.
          readiness_probe {
            http_get {
              path = "/readiness"
              port = 9090
            }
            initial_delay_seconds = 3
            period_seconds        = 5
            failure_threshold     = 3
          }
        }
      }
    }
  }
}
