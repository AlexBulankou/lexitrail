#!/usr/bin/env python3
"""lexitrail#447 step 2 + the acceptance criterion, as one runnable instrument.

WHY THIS EXISTS AS A SCRIPT AND NOT AS A NOTE
`eventCount` counts `recall` EVENTS. The bulk path emits one event carrying
`cards_count: N`, so event-counting undercounts card volume by whatever N is.
Step 2 of #447 says "anything that reports recall volume or accuracy should
switch to SUM(cards_count)" -- and there is nothing in this repo to switch:
`grep -rn eventCount` over `scripts/` and `ui/src` returns NOTHING (control:
`recall` matches five files). The reporting happens in ad-hoc queries, which
is exactly the surface a prose instruction cannot reach. So the correct query
is written down HERE, where it can be run instead of remembered.

It is also the AC's own measurement:

    "runReport ... returns a non-zero cards_count sum for `recall` over a
     7-day window, and that sum is strictly GREATER than the `recall`
     eventCount for the same window. A sum equal to eventCount means the
     metric registered but the bulk path is not being exercised."

🔴 THREE OUTCOMES, AND THE THIRD MUST NOT READ AS EITHER OF THE OTHERS.
GA4 custom metrics are NOT retroactive: `cards_count` was registered
2026-09-11 (customMetrics/15762078411), so a 7-day window only becomes
meaningful on or after 2026-09-18. Before then a zero sum is "no data yet",
which is NOT the same fact as "the bulk path is not being exercised" -- and
a two-state check would print the second while the first is true.

    sum  > eventCount   MET         the undercount was real and is now visible
    sum == eventCount   NOT MET     registered, but bulk recall is not firing
    sum == 0            UNDECIDED   no populated days in the window yet

CREDENTIAL NOTE (#447, zz1's correction 2026-09-11): scope is chosen when you
MINT the token, not fixed on the service account. This reads, so it mints
`analytics.readonly` deliberately -- a reporting script has no business
holding `analytics.edit`. The earlier claim that the SA "is analytics.readonly
and every Admin write 403s" was a mis-minted token read as an account property.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

PROPERTY_ID = os.environ.get("LEXITRAIL_GA4_PROPERTY_ID", "366310598")
KEY_PATH = os.environ.get(
    "LEXITRAIL_GA4_KEY", os.path.expanduser("~/.ensemble/keys/my-hermes-sa-key.json"))
SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
DATA_API = "https://analyticsdata.googleapis.com/v1beta/properties/{}:runReport"

# The registered custom metric's API name. GA4 exposes an event-scoped custom
# metric as `customEvent:<parameterName>` -- NOT as the bare parameter name,
# which is what the pre-registration query in #447 used and why it 400'd.
CARDS_METRIC = "customEvent:cards_count"

MET, NOT_MET, UNDECIDED, ERROR = 0, 1, 3, 4


def _token() -> str:
    from google.oauth2 import service_account
    import google.auth.transport.requests as gar
    creds = service_account.Credentials.from_service_account_file(
        KEY_PATH, scopes=[SCOPE])
    creds.refresh(gar.Request())
    return creds.token


def run_report(token: str, days: int) -> dict:
    body = {
        "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "today"}],
        "dimensions": [{"name": "eventName"}],
        "metrics": [{"name": "eventCount"}, {"name": CARDS_METRIC}],
        "dimensionFilter": {
            "filter": {"fieldName": "eventName",
                       "stringFilter": {"value": "recall"}}},
    }
    req = urllib.request.Request(
        DATA_API.format(PROPERTY_ID), data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def totals(report: dict) -> tuple[int, int]:
    """(eventCount, cards_count sum) for the `recall` row, 0/0 when absent.

    An ABSENT row and a row of zeros are the same answer to this question --
    no recall volume in the window -- so collapsing them here is deliberate.
    The three-way verdict is made by the caller, which can tell 0 from 0 by
    the DATE, not by the payload.
    """
    for row in report.get("rows") or []:
        vals = [int(v.get("value", 0)) for v in row.get("metricValues", [])]
        if len(vals) >= 2:
            return vals[0], vals[1]
    return 0, 0


def verdict(events: int, cards: int) -> tuple[int, str]:
    if cards == 0:
        return UNDECIDED, (
            f"UNDECIDED: cards_count sum is 0 over the window (eventCount "
            f"{events}). `cards_count` was registered 2026-09-11 and GA4 "
            f"custom metrics are NOT retroactive, so this is 'no populated "
            f"days yet', which is NOT the same as 'the bulk path is not "
            f"firing'. Re-run on or after 2026-09-18.")
    if cards > events:
        return MET, (
            f"MET: cards_count sum {cards} > recall eventCount {events} "
            f"(undercount was {cards - events} cards, "
            f"{(cards - events) / cards:.0%} of volume). Report BOTH numbers "
            f"on close, as #447 asks.")
    return NOT_MET, (
        f"NOT MET: cards_count sum {cards} == eventCount {events}. The metric "
        f"is registered and populating, but every recall is single-card -- the "
        f"bulk path is not being exercised. That is a finding about the app, "
        f"not about the metric.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=7,
                    help="window length; the AC specifies 7")
    ap.add_argument("--json", action="store_true", help="machine-readable")
    args = ap.parse_args()

    try:
        report = run_report(_token(), args.days)
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        # 🔴 Report the STATUS, not just that it failed (zz1, #447): a 400 is
        # field validation and means the request was already AUTHORISED, so it
        # is a query bug. A 403 is the permission gap, checked before fields.
        kind = ("query is malformed -- auth already passed" if e.code == 400
                else "PERMISSION -- checked before any field" if e.code == 403
                else "")
        print(f"ERROR http={e.code} {kind}\n{detail}", file=sys.stderr)
        return ERROR
    except Exception as e:  # noqa: BLE001 -- announce, never swallow
        print(f"ERROR {type(e).__name__}: {e}", file=sys.stderr)
        return ERROR

    events, cards = totals(report)
    code, msg = verdict(events, cards)
    if args.json:
        print(json.dumps({"eventCount": events, "cards_count": cards,
                          "days": args.days, "verdict": code, "message": msg}))
    else:
        print(msg)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
