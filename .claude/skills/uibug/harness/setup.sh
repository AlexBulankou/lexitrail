#!/usr/bin/env bash
# Idempotent harness setup. Safe to re-run; skips work that is already done.
#
# Browsers are pre-installed in this environment at $PLAYWRIGHT_BROWSERS_PATH
# (default /opt/pw-browsers), so we never run `playwright install` -- that would
# re-download ~150MB through the egress proxy for no gain. If a future image
# lacks them, set UIBUG_INSTALL_BROWSERS=1 to opt in explicitly.
set -euo pipefail
cd "$(dirname "$0")"

export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD="${PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD:-1}"

if [ ! -d node_modules/@playwright/test ]; then
  echo "[uibug] installing @playwright/test ..."
  npm install --no-audit --no-fund --loglevel=error
else
  echo "[uibug] @playwright/test already present"
fi

BROWSERS="${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}"
if [ -d "$BROWSERS" ]; then
  echo "[uibug] using pre-installed browsers at $BROWSERS"
elif [ "${UIBUG_INSTALL_BROWSERS:-0}" = "1" ]; then
  npx playwright install chromium
else
  echo "[uibug] WARNING: no browsers at $BROWSERS." >&2
  echo "[uibug] Re-run with UIBUG_INSTALL_BROWSERS=1 to download chromium." >&2
fi
echo "[uibug] setup ok"
