# lexitrail#358 — managed Cloud SQL for MySQL, replacing the self-hosted
# `mysql-0` StatefulSet in mysql.tf.
#
# WHY: on 2026-09-03 lexitrail.com was functionally down ~8h because `mysql-0`
# was evicted from a preemptible/spot node with nowhere to reschedule
# (lexitrail#331). A stateful DB on spot capacity is the root cause; managed
# Cloud SQL is always-on and not subject to spot eviction. Alex's decision
# 2026-09-04: cheapest viable managed instance.
#
# THIS FILE PROVISIONS ONLY. It does not cut over — mysql.tf stays live and
# untouched, and nothing reads this instance yet. The dump→import and the
# `DATABASE_URL` repoint are separate, reversible slices, so an apply here is
# additive and a rollback is a `terraform destroy` of these three resources.
#
# ── Sizing: MEASURED, not assumed ──────────────────────────────────────────
# The issue says "right-size at migration: run mysqldump | wc -c (or check the
# PVC used bytes) before picking the tier". Measured 2026-09-08 against live
# mysql-0:
#
#   lexitraildb   143.11 MB logical, 7 tables    disk 418M used of 4.9G (9%)
#     userwords        29,355 rows   75.55 MB
#     words             4,472 rows   53.81 MB
#     recall_history   95,141 rows   13.55 MB
#     users             2,276 rows    0.17 MB
#   MySQL 8.0.46
#
# ⚠️ The issue's design sketch describes this as "~150 words × 6 levels + per-user
# progress rows". Live is 4,472 words and 2,276 users. That does not change the
# "well under 1GB" conclusion, but it is a real app with real usage and the
# buffer-pool note below is not theoretical because of it.
#
# ── Tier: db-f1-micro, and why starting cheap is SAFE rather than optimistic ─
# f1-micro is 614 MiB RAM, so the InnoDB buffer pool lands roughly the size of
# the 143 MB dataset — the hot set (userwords + words = 129 MB) is nearly the
# whole database. That is workable and it is the tier most likely to produce a
# "slow since the cutover" report.
#
# Starting here anyway, because the decision says CHEAPEST VIABLE and the tier
# is REVERSIBLE IN MINUTES: a machine-type change is a stop/start, not a
# migration. Choosing cheap first risks one short restart; choosing g1-small
# (1.7 GiB, ~3x cost) first pays that difference forever on a budget-sensitive
# project (goal 1.3).
#
# 🔴 TRIPWIRE, so this is a decision and not a hope: capture p95 on
# `/wordsets` and a Practice round BEFORE cutover. If either degrades against
# that baseline, `tier = "db-g1-small"` and re-apply. Without the baseline,
# "degraded" has nothing to be measured against.
#
# ⚠️ The baseline must include CPU UTILISATION, not just latency (hc2 review).
# f1-micro is SHARED-CORE and burstable, so once the burst budget is spent the
# symptom is CPU throttling, not buffer-pool misses — a latency-only capture
# would show the degradation and misattribute the cause, and the two point at
# the same remedy here only by luck.
#
# ── Deliberate choices, stated so a reviewer can disagree with the reason ───
#  1. availability_type ZONAL (no HA). The root cause was SPOT EVICTION, which
#     managed Cloud SQL removes whether or not it is HA. Paying for REGIONAL
#     would be solving a different problem than the one #331 documented.
#  2. deletion_protection TRUE. This holds 2,276 users' progress. The migration
#     runbook can flip it deliberately; it must not be absent by default.
#  3. Public IP + Cloud SQL Auth Proxy, NOT private IP. The cluster lives in
#     yojowa-claw and this instance in lexitrail, so private IP needs
#     cross-project VPC peering — real work, and not needed to prove the
#     migration. The connector wiring is the next slice.
#     ⚠️ `ipv4_enabled = true` with NO authorized_networks means the instance is
#     reachable only via the Auth Proxy / IAM, not from the open internet.
#  4. disk_autoresize TRUE with a 10 GB floor. 418 MB used today (~24x
#     headroom), and recall_history grows with every practice round, so the
#     failure mode to avoid is a full disk rather than an oversized bill.
#  5. binary_log_enabled TRUE — required for point-in-time recovery, and the
#     thing you cannot retrofit after you need it.

resource "google_sql_database_instance" "lexitrail" {
  name             = "lexitrail-mysql"
  database_version = "MYSQL_8_0" # live is 8.0.46
  region           = var.ys_region
  project          = var.lexitrail_project_id

  # Reversible-by-runbook, not by accident.
  deletion_protection = true

  settings {
    tier              = "db-f1-micro"
    availability_type = "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = 10
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      binary_log_enabled             = true
      start_time                     = "09:00" # ~02:00 PT, off-peak
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 7
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      ipv4_enabled = true
      # No authorized_networks: reachable via the Cloud SQL Auth Proxy / IAM
      # only. Adding a CIDR here would open it to the internet.
      #
      # ssl_mode pinned EXPLICITLY rather than inherited (hc2 review). Today the
      # network layer already blocks direct TCP because authorized_networks is
      # empty, so this is belt-and-braces — but the two protections have
      # DIFFERENT lifetimes: someone adding a CIDR later for a debug session
      # removes the network protection and would silently remove encryption
      # enforcement with it if that were left to a provider default. This holds
      # 2,276 users' data; a security default worth having is worth stating.
      ssl_mode = "ENCRYPTED_ONLY"
    }

    maintenance_window {
      day          = 7  # Sunday
      hour         = 10 # ~03:00 PT
      update_track = "stable"
    }
  }
}

resource "google_sql_database" "lexitraildb" {
  name     = var.database_name # "lexitraildb", same name as live
  instance = google_sql_database_instance.lexitrail.name
  project  = var.lexitrail_project_id
}

# Root user, seeded from the SAME variable the in-cluster Secret uses (mysql.tf),
# so the dump→import step does not need a second credential. The app-scoped user
# is deliberately NOT created here — it belongs with the cutover slice that also
# repoints DATABASE_URL, and creating it now would leave an unused grant.
resource "google_sql_user" "root" {
  name     = "root"
  instance = google_sql_database_instance.lexitrail.name
  password = var.db_root_password
  host     = "%"
  project  = var.lexitrail_project_id
}
