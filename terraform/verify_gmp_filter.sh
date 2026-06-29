#!/usr/bin/env bash
# verify_gmp_filter.sh — detection guard for the GMP cadvisor cost-trim filter.
#
# Reads the live `gmp-public` OperatorConfig and asserts the 5-essential
# cadvisor keep-list (issue #5 ask #1, ~$15-18/mo trim) is still intact.
# READ-ONLY: never mutates the cluster.
#
# Exit codes:
#   0 — filter intact
#   1 — filter drifted / reset (re-apply per docs/runbooks/gmp-cadvisor-filter.md)
#   2 — could not read the OperatorConfig (cluster/auth issue)
#
# Refs: AlexBulankou/lexitrail#7, #5 (ask #1). Sister: AlexBulankou/ensemble#6669.
set -euo pipefail

NS=gmp-public
NAME=config
ESSENTIALS=(
  cpu_usage_seconds_total
  memory_working_set_bytes
  memory_usage_bytes
  network_receive_bytes_total
  network_transmit_bytes_total
)
RUNBOOK="docs/runbooks/gmp-cadvisor-filter.md"

if ! filter=$(kubectl get operatorconfig "$NAME" -n "$NS" \
      -o jsonpath='{.collection.filter.matchOneOf}' 2>/dev/null); then
  echo "ERROR: could not read OperatorConfig '$NAME' in namespace '$NS'." >&2
  echo "Check kubectl context + cluster auth." >&2
  exit 2
fi

if [[ -z "$filter" ]]; then
  echo "DRIFT: collection.filter.matchOneOf is EMPTY — cadvisor cost-trim filter has been reset." >&2
  echo "Re-apply per $RUNBOOK" >&2
  exit 1
fi

# Rule 1 — the drop-all-container rule must be present.
# kubectl renders the matchOneOf array as JSON with backslash-escaped inner
# quotes, so match on quote-free substrings: the `!~` negative-match operator
# AND the `container_.*` drop-all pattern (which appears only in rule 1 —
# rule 2 re-admits via `container_(...)`).
if [[ "$filter" != *'__name__!~'* || "$filter" != *'container_.*'* ]]; then
  echo "DRIFT: drop-all-container rule (negative-match on container_.*) missing from filter." >&2
  echo "Re-apply per $RUNBOOK" >&2
  exit 1
fi

# Rule 2 — every essential keep-list metric must be re-admitted.
missing=()
for e in "${ESSENTIALS[@]}"; do
  [[ "$filter" == *"$e"* ]] || missing+=("$e")
done
if (( ${#missing[@]} )); then
  echo "DRIFT: essential keep-list metric(s) missing: ${missing[*]}" >&2
  echo "Re-apply per $RUNBOOK" >&2
  exit 1
fi

echo "OK: GMP cadvisor cost-trim filter intact (drop-all-container + ${#ESSENTIALS[@]} essentials)."
exit 0
