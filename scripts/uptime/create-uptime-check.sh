#!/usr/bin/env bash
# LexiTrail (lexitrail.com) uptime check — joins the CONSOLIDATED uptime chart + SMS page path
# in the yojowa-claw project (Alex, 2026-09-05: "consolidate all checks in a
# single project — yojowa-claw, the project that has most shared services").
#
# The shared foundation (SMS/email channels, the generic uptime-failure-policy,
# the all-products dashboard, and re-created leaseok/withby/yojowa-site checks)
# lives in my-hermes hermes-config/uptime/ — apply that kit FIRST (phases 01-02
# at minimum; the SMS channel needs Alex's one-time verify). This script only
# adds this product's check; the policy matches uptime_check/check_passed
# GENERICALLY (grouped by check_id), so chart membership and SMS paging attach
# automatically the moment the check exists.
#
# Flags are CANONICAL (no doc-YAML mirror — see market-mind sms-alerts #3623
# dual-source-drift lesson). Idempotent. Operator-driven apply (not in
# auto-deploy): run on bp with monitoring.editor on yojowa-claw.

set -euo pipefail

PROJECT="yojowa-claw"
DISPLAY_NAME="lexitrail-home"
HOST="lexitrail.com"
CHECK_PATH="/"
POLICY_DISPLAY_NAME="uptime-failure-policy"
SMS_DISPLAY_NAME="phone-3506"

echo "==> Preconditions: foundation kit applied to ${PROJECT}?"
POLICY=$(gcloud alpha monitoring policies list --project="${PROJECT}" \
  --filter='displayName="'"${POLICY_DISPLAY_NAME}"'"' --format='value(name)' | head -1)
[[ -n "${POLICY}" ]] || { echo "ERROR: '${POLICY_DISPLAY_NAME}' missing in ${PROJECT} — apply my-hermes hermes-config/uptime/ phases 01-02 first." >&2; exit 1; }
SMS=$(gcloud alpha monitoring channels list --project="${PROJECT}" \
  --filter='displayName="'"${SMS_DISPLAY_NAME}"'" AND type="sms"' --format='value(name)' | head -1)
[[ -n "${SMS}" ]] || { echo "ERROR: SMS channel '${SMS_DISPLAY_NAME}' missing in ${PROJECT}." >&2; exit 1; }
STATUS=$(gcloud alpha monitoring channels describe "${SMS}" --project="${PROJECT}" --format='value(verificationStatus)')
[[ "${STATUS}" == "VERIFIED" ]] || { echo "ERROR: SMS channel status=${STATUS} (Alex's one-time verify pending)." >&2; exit 1; }
gcloud alpha monitoring policies describe "${POLICY}" --project="${PROJECT}" \
  --format='value(notificationChannels)' | grep -q "${SMS}" || { echo "ERROR: SMS channel not attached to policy." >&2; exit 1; }

EXISTING=$(gcloud monitoring uptime list-configs --project="${PROJECT}" \
  --filter='displayName="'"${DISPLAY_NAME}"'"' --format='value(name)' | head -1)
if [[ -n "${EXISTING}" ]]; then
  echo "==> Uptime check already exists: ${EXISTING} — no-op."
  exit 0
fi

echo "==> Creating '${DISPLAY_NAME}' -> https://${HOST}${CHECK_PATH}"
# Shape mirrors the proven withby-ai check (60s period, 3 US regions, 2xx).
gcloud monitoring uptime create "${DISPLAY_NAME}" \
  --project="${PROJECT}" \
  --resource-type=uptime-url \
  --resource-labels="host=${HOST},project_id=${PROJECT}" \
  --protocol=https \
  --path="${CHECK_PATH}" \
  --port=443 \
  --request-method=get \
  --status-classes=2xx \
  --period=1 \
  --timeout=10 \
  --regions=usa-oregon,usa-iowa,usa-virginia \
  --user-labels="surface=shared-uptime-chart,recipient=alex,requested=2026-09-05,filed_by=zz3,product=lexitrail"

echo "==> Done — the check joins the consolidated chart + SMS policy automatically."

