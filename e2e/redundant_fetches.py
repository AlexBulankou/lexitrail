#!/usr/bin/env python3
"""Redundant data-fetch check — lexitrail#91, and the measurement half of #52 item 6.

WHY THIS EXISTS
---------------
Alex's item 6 in lexitrail#52 is *"wordsets loading persisted several minutes
after clicking around"*, and asks that users never be interrupted by a loading
state. Two separable questions live in that sentence:

  (a) does the load STALL?          -- reported here, never gated on
  (b) how much of it is REDUNDANT?  -- what this harness gates on

(b) is measurable and stable; (a) is not reproducible on demand from the guest
journey (both arms cleared in ~1.0s on prod, 2026-08-10), so gating on it would
produce a check that is green for the wrong reason. Reporting (a) while gating
on (b) keeps the stall visible without pretending we can summon it.

WHAT IT MEASURES
----------------
`useWordsetLoader`'s cache key carries `mode`; the two payloads it caches do
not -- `getWordsByWordset(wordsetId)` and `getUserWordsByWordset(userId,
wordsetId)` take no mode, and `mode` only drives a client-side `.filter()`. So
every mode switch is a guaranteed cache miss on bytes already in memory.
Measured on prod before the fix: 3 wordsets x 4 modes issued 25 data requests,
7 distinct -- 18 redundant, each wordset fetched 4x.

THIS IS A DETECTOR, SO IT HAS CONTROLS
--------------------------------------
A silent detector and a healthy site look identical, so silence carries no
information unless the instrument is known to be able to speak.

  1. `--self-test` drives the pure counter over a synthetic trace with known
     duplicates and asserts it flags EXACTLY those, then over a duplicate-free
     trace and asserts it stays silent. It validates the instrument (can it
     fire? can it stay quiet?) without asserting anything about the live site,
     so fixing #91 does not expire the control.

  2. Outcomes are THREE-state. "I could not reach the page" must never render
     as "no redundancy":

         0  PASS   no data URL was fetched more than once
         1  FAIL   at least one data URL was fetched more than once
         2  BLIND  could not measure (no Try button, no wordset controls, or
                   zero data requests observed -- which means the probe never
                   exercised the loader, not that the loader is efficient)

FUNNEL SAFETY (docs/itp-playwright-usability.md 2.3)
Navigation only, over the guest ("Try") journey — never the Google sign-in
path. No card is answered, so no recall/exclusion state is written to the demo
account.

Unlike `tap_targets.py` this harness *clicks*, and the Try button fires a GA4
`try_with_demo_account` event, so the analytics abort is not optional here: it
is installed on the CONTEXT with the REGEX matcher BEFORE the first navigation
(a glob misses the real `www.`/`region1.` subdomains). The run reports how many
beacons were blocked and FAILS if any completed, so the clean-funnel claim is
measured rather than asserted.
"""
import argparse
import re
import sys
import time
from collections import Counter

URL_DEFAULT = "https://lexitrail.com"

# The loader's two payloads, matched by REGEX rather than substring.
#
# Deliberately not a full URL: the query string carries the demo user id, which
# varies per session (t3vs6@, pap8f@, 057zh@ observed across runs), and pinning
# it would make the check silently measure nothing.
#
# But `"/words"` as a substring ALSO matches `/wordsets` -- the wordset LIST
# endpoint, which the home page refetches on every back-navigation. That is a
# different call with a different lifetime, and counting it swamped the signal:
# it alone accounted for all 12 remaining "redundant" requests on a build where
# the loader's own payloads had ZERO duplicates. Anchor on the wordset id.
DATA_RE = re.compile(r"/wordsets/[^/]+/words|/userwords/")

MODES = ["PRACTICE", "DUE_TODAY", "SHOW_EXCLUDED", "TEST"]
WORDSETS = [1, 2, 3]

# Regex, not a glob — a glob like `**/google-analytics.com/**` silently misses
# the real `www.`/`region1.` subdomains and lets live beacons through.
ANALYTICS_RE = re.compile(
    r"googletagmanager\.com|google-analytics\.com|analytics\.google\.com")

EXIT_PASS, EXIT_FAIL, EXIT_BLIND = 0, 1, 2


def redundant(urls, keys=None):
    """Pure core: given observed request URLs, return the redundancy report.

    Kept free of Playwright so `--self-test` can drive it directly.
    """
    matcher = keys or DATA_RE
    data = [u for u in urls if matcher.search(u)]
    counts = Counter(data)
    dupes = {u: n for u, n in counts.items() if n > 1}
    return {
        "total": len(data),
        "distinct": len(counts),
        "redundant": len(data) - len(counts),
        "dupes": dupes,
    }


def self_test():
    """Validate the instrument in BOTH directions."""
    ok = True

    # (1) it fires, and on exactly the duplicated URL
    trace = [
        "https://api.x/wordsets/1/words",
        "https://api.x/wordsets/1/words",
        "https://api.x/userwords/query?user_id=a&wordset_id=1",
        "https://api.x/static/js/main.abc.js",  # not a data URL; must be ignored
    ]
    r = redundant(trace)
    if r["redundant"] != 1 or list(r["dupes"]) != ["https://api.x/wordsets/1/words"]:
        print(f"SELF-TEST FAIL: expected exactly the words URL flagged, got {r}")
        ok = False

    # (2) it stays silent when there is nothing to report
    clean = [
        "https://api.x/wordsets/1/words",
        "https://api.x/userwords/query?user_id=a&wordset_id=1",
    ]
    r = redundant(clean)
    if r["redundant"] != 0 or r["dupes"]:
        print(f"SELF-TEST FAIL: expected silence on a clean trace, got {r}")
        ok = False

    # (3) a trace with no data URLs at all reports nothing to count -- the
    #     caller turns this into BLIND rather than PASS.
    r = redundant(["https://api.x/static/js/main.abc.js"])
    if r["total"] != 0:
        print(f"SELF-TEST FAIL: expected zero data requests, got {r}")
        ok = False

    print("SELF-TEST PASS: counter fires on duplicates and stays silent without them"
          if ok else "SELF-TEST FAILED")
    return EXIT_PASS if ok else EXIT_FAIL


def measure(url, settle_ms, nav):
    from playwright.sync_api import sync_playwright

    seen = []
    blocked = []
    completed = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844})

        # Installed on the CONTEXT and BEFORE new_page/goto — order is
        # load-bearing: a route set after navigation lets the first beacons
        # through. This harness CLICKS Try, which fires a GA4 event.
        def _abort(route):
            blocked.append(route.request.url)
            route.abort()

        ctx.route(ANALYTICS_RE, _abort)
        page = ctx.new_page()
        page.on("request", lambda r: seen.append(r.url))
        page.on("requestfinished",
                lambda r: completed.append(r.url) if ANALYTICS_RE.search(r.url) else None)

        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        try:
            page.click("button.try-button", timeout=10000)
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            ctx.close()
            return None, f"could not start the guest journey: {str(exc)[:120]}"
        page.wait_for_timeout(2500)

        if not page.query_selector_all(".wordset-button"):
            ctx.close()
            return None, "no wordset controls found after Try"

        if nav == "goto":
            # Hard navigation. Reloads the SPA every view, so the in-memory
            # cache is wiped each time — this arm measures the deep-link /
            # reload path and is BLIND to any caching fix by construction.
            for ws in WORDSETS:
                for mode in MODES:
                    page.goto(f"{url}/game/{ws}/{mode}",
                              wait_until="commit", timeout=20000)
                    page.wait_for_timeout(settle_ms)
        else:
            # Client-side routing — what a user actually does when switching
            # mode, and the ONLY arm in which an in-memory cache can apply.
            # The DOM is rebuilt after each back, so controls are re-queried.
            for i in range(len(WORDSETS) * len(MODES)):
                controls = page.query_selector_all(".wordset-button")
                if i >= len(controls):
                    break
                controls[i].click()
                page.wait_for_timeout(max(settle_ms, 1500))
                page.go_back()
                page.wait_for_timeout(1000)

        # report-only: does the final view ever finish loading?
        start = time.time()
        cleared = None
        for _ in range(90):
            page.wait_for_timeout(1000)
            if "loading" not in (page.inner_text("body") or "").lower():
                cleared = time.time() - start
                break
        ctx.close()

    report = redundant(seen)
    report["cleared_s"] = cleared
    report["ga_blocked"] = len(blocked)
    report["ga_completed"] = completed
    return report, None


def main():
    ap = argparse.ArgumentParser(description="Redundant data-fetch check (lexitrail#91)")
    ap.add_argument("--url", default=URL_DEFAULT)
    ap.add_argument("--self-test", action="store_true",
                    help="validate the detector itself; touches no site")
    ap.add_argument("--nav", choices=["click", "goto"], default="click",
                    help="click = client-side routing (default; the only arm in which "
                         "an in-memory cache can apply). goto = hard navigation, which "
                         "wipes the cache every view and is blind to caching fixes.")
    ap.add_argument("--settle-ms", type=int, default=350,
                    help="pause per view; deliberately shorter than a load so a "
                         "new request is issued while the previous is in flight")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    report, why_blind = measure(args.url, args.settle_ms, args.nav)
    if report is None:
        print(f"BLIND: {why_blind}")
        return EXIT_BLIND

    views = len(WORDSETS) * len(MODES)
    print(f"views navigated: {views}  ({len(WORDSETS)} wordsets x {len(MODES)} modes)"
          f"  | nav={args.nav}")
    print(f"data requests: {report['total']} | distinct: {report['distinct']} "
          f"| redundant: {report['redundant']}")
    print("loading cleared in: " +
          (f"{report['cleared_s']:.1f}s" if report["cleared_s"] is not None
           else "NOT CLEARED in 90s")
          + "   (report-only, never gated -- see module docstring)")

    print(f"analytics beacons blocked: {report['ga_blocked']} | completed: "
          f"{len(report['ga_completed'])}")
    if report["ga_completed"]:
        print("FAIL: a live analytics beacon completed — this run polluted the "
              "funnel. Fix the matcher before trusting any further run.")
        for u in report["ga_completed"][:3]:
            print(f"   {u[:110]}")
        return EXIT_FAIL

    if report["total"] == 0:
        print("BLIND: zero data requests observed — the probe never exercised the "
              "loader, which is not the same as the loader being efficient.")
        return EXIT_BLIND

    for u, n in sorted(report["dupes"].items(), key=lambda kv: -kv[1]):
        print(f"   x{n}  {u[:110]}")

    if report["redundant"]:
        print(f"FAIL: {report['redundant']} redundant data requests "
              f"({report['redundant'] * 100 // report['total']}% of traffic).")
        return EXIT_FAIL
    print("PASS: no data URL fetched more than once.")
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
