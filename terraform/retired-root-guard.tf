# This root is RETIRED — the live stack is provisioned by ../terraform-ys/.
#
# The reason this needs more than a README warning: `sql.tf`'s
# `mysql_schema_and_data_job` runs schema-tables.sql unconditionally on any
# apply that reaches it. schema-tables.sql opens with:
#
#     DROP TABLE IF EXISTS recall_history;
#     DROP TABLE IF EXISTS userwords;
#     ...
#
# and the Job's replacement trigger is a content hash over schema-tables.sql +
# schema-data.sql + csv/**. Any edit to those files — for any reason,
# including one unrelated to this root — changes the hash, and the next
# `terraform apply` that reaches this resource drops and recreates
# users/userwords/recall_history/words/wordsets from schema-data.sql's seed
# data. There is no additive-migration path anywhere in this repo (see
# lexitrail#222): drop-and-recreate is the only schema-change mechanism that
# exists, in this root or terraform-ys.
#
# `google_container_cluster.autopilot_cluster` (main.tf) provisions its own
# cluster in this root, so a fresh clone applying this root does not reach
# the live ys-autopilot cluster/database directly. The residual risk this
# guards against is state/`.env` drift: this root uses **local state only**
# (see README's Deployment warning) and reads CLUSTER_NAME/PROJECT_ID from a
# gitignored `.env` — if either ever pointed at the live project/cluster
# (accidentally shared `.env`, a stale state file on the wrong machine),
# `mysql_schema_and_data_job` would run against live data with no further
# confirmation step.
#
# So: refuse to plan/apply this root at all unless the operator explicitly
# opts in. There is no default of `true` — an unset/false value fails
# validation on every `terraform plan`/`apply` in this directory, regardless
# of -target.
variable "i_understand_this_root_is_retired_and_may_drop_prod_tables" {
  type        = bool
  default     = false
  description = "Must be explicitly set true (-var) to plan/apply this retired root. See lexitrail#222."

  validation {
    condition     = var.i_understand_this_root_is_retired_and_may_drop_prod_tables == true
    error_message = <<-EOT
      terraform/ is RETIRED (lexitrail#222) — the live stack is provisioned by
      ../terraform-ys/, not this root. mysql_schema_and_data_job here runs an
      UNCONDITIONAL DROP TABLE (recall_history, userwords, words, wordsets,
      users) keyed to a content hash over schema-tables.sql/schema-data.sql/
      csv/** — any edit to those files re-arms it on the next apply.

      If you have confirmed with the team that running terraform in THIS
      root (not terraform-ys/) is intentional, re-run with:
        -var='i_understand_this_root_is_retired_and_may_drop_prod_tables=true'
    EOT
  }
}
