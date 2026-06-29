# Runbook — GMP cadvisor metric-drop filter (cost-trim durability)

## What this protects

The Cloud Monitoring cost trim from issue #5 (ask #1, ~$15–18/mo) drops
high-cardinality `container_*` cadvisor series from Google Managed
Prometheus (GMP), keeping only 5 essential container metrics. The trim
lives in the `collection.filter` of the `gmp-public` `OperatorConfig`
named `config`.

`OperatorConfig` is a **managed-prometheus addon resource**. A managed-
prometheus **addon upgrade** (or any process that re-templates the addon)
can reset `collection.filter` to defaults — silently dropping the filter
and re-inflating Cloud Monitoring cost ~$15–18/mo. Nobody would notice
until a billing review.

## Detection

Run the read-only check (no mutation):

    terraform/verify_gmp_filter.sh

- exit 0 — filter intact.
- exit 1 — filter drifted/reset → re-apply (below).
- exit 2 — could not read the OperatorConfig (cluster/auth issue).

Schedule this (cron / CI) so a reset is caught in hours, not at the next
billing review. (Durable in-cluster guard that re-applies automatically:
see "Remaining work" below — tracked on #7.)

## Re-apply (recovery)

The exact merge-patch — idempotent, and a merge-type patch preserves the
sibling `externalLabels` block:

    kubectl patch operatorconfig config -n gmp-public --type merge -p '{"collection":{"filter":{"matchOneOf":["{__name__!~\"container_.*\"}","{__name__=~\"container_(cpu_usage_seconds_total|memory_working_set_bytes|memory_usage_bytes|network_receive_bytes_total|network_transmit_bytes_total)\"}"]}}}'

Verify after:

    terraform/verify_gmp_filter.sh   # expect exit 0 / "OK"

### The verbatim filter (keep-list)

    filter:
      matchOneOf:
      - '{__name__!~"container_.*"}'
      - '{__name__=~"container_(cpu_usage_seconds_total|memory_working_set_bytes|memory_usage_bytes|network_receive_bytes_total|network_transmit_bytes_total)"}'

Rule 1 drops every `container_*` series; rule 2 re-admits the 5 essentials
(CPU usage, memory working-set, memory usage, network rx/tx bytes).

## Remaining work (AC1 — durable guard)

Detection + documented recovery (this runbook + the verify script) close
the "silent + slow-to-notice" half of the risk. The durable guard that
makes the filter survive a reset **automatically** is still tracked on #7:

- **Option A (preferred) — terraform-codified re-apply CronJob.** An
  in-cluster `CronJob` (additive; does NOT adopt the addon-owned
  `OperatorConfig`) that re-applies the patch every N hours. Needs a
  `ServiceAccount` + `Role`/`RoleBinding` granting `patch operatorconfigs`
  in `gmp-public`. Fits the existing `terraform/k8s_templates/*.yaml.tpl`
  + `kubectl` provider pattern.
- **Option B — adopt the OperatorConfig into terraform** via the
  `kubectl` provider with server-side-apply. Higher risk: terraform then
  co-owns an addon resource and can fight the addon controller on
  upgrades. Prefer Option A.

This is deliberate live-prod terraform work; give it its own focused
review rather than rushing it. Sister fleet-wide gap:
AlexBulankou/ensemble#6669.

Refs: #5 (ask #1), #7.
