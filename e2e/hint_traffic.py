#!/usr/bin/env python3
"""Hint-traffic check — the un-re-measured 🟡 row on lexitrail#45.

WHY THIS EXISTS
---------------
The ITP round-3 report filed *"hint traffic fires while hints are hidden — 114
involuntary requests in one session"*. #45 has carried it as
🟡 **likely addressed, unverified** ever since: `d525e81` (PR #30) made hint
images opt-in and `WordCard.js` now carries an explicit early return

    if (!isHintDisplayed) { setLoadingHint(false); return; }

…which reads exactly like the fix. **A code reading is not a measurement.** The
same "obviously fixed by inspection" move on the sister ITP row (#42 NEW-8) was
confirmed wrong later by an actual probe, so this row gets a probe too.

WHAT IT MEASURES
----------------
Requests matching `/hint/generate_hint` while browsing the practice card grid,
in two arms:

    ARM A  hints HIDDEN (the app's default)  -> expected 0
    ARM B  hints SHOWN  ("Show Hints")       -> expected > 0

THIS IS A DETECTOR, SO ARM B IS NOT OPTIONAL
--------------------------------------------
A zero in ARM A is worthless on its own: a probe that never sees any request and
a page that correctly issues none are byte-identical outputs. ARM B is the
positive control, run in the SAME session against the SAME cards, and it must
fire or the whole run is BLIND rather than PASS. (This is the failure that cost
four attempts on #42 NEW-1: a control that silently fails converts an unverified
zero into an apparently-verified one.)

⚠️ ARM ORDER IS LOAD-BEARING and must stay A-then-B. `hintService.js` holds a
per-session `hintCache` keyed on user+word, so a hint fetched in ARM B is served
from memory afterwards — running B first would make A's zero unfalsifiable.

Outcomes are THREE-state:

    0  PASS   hidden fired 0 requests AND the control fired > 0
    1  FAIL   hidden fired >= 1 request
    2  BLIND  could not reach practice, no cards, or the control fired 0

FUNNEL SAFETY (docs/itp-playwright-usability.md 2.3)
Guest ("Try") journey only, never the Google sign-in path. Hints are toggled and
cards are browsed; no card is answered, so no recall/exclusion state is written.
Analytics beacons are aborted on the CONTEXT with a REGEX matcher before the
first navigation, and the run FAILS if any completed.
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lt_routes import enter_practice  # noqa: E402  (sys.path shim above)

URL_DEFAULT = "https://lexitrail.com"

# Anchored on the ROUTE, not on the word "hint": the bundle path, the CSS and
# the rendered image URLs all contain "hint", and counting those would report
# traffic on a page that issued no API call at all.
HINT_RE = re.compile(r"/hint/generate_hint")

ANALYTICS_RE = re.compile(
    r"googletagmanager\.com|google-analytics\.com|analytics\.google\.com")

EXIT_PASS, EXIT_FAIL, EXIT_BLIND = 0, 1, 2


def count_hints(urls):
    """Pure core: hint-API requests in an observed request trace."""
    hits = [u for u in urls if HINT_RE.search(u)]
    return {"total": len(hits), "distinct": len(set(hits)),
            "by_url": dict(Counter(hits))}


def self_test():
    """Validate the instrument in BOTH directions."""
    ok = True

    # (1) it fires, and only on the API route
    trace = [
        "https://api.lexitrail.com/hint/generate_hint?user_id=a&word_id=1",
        "https://api.lexitrail.com/hint/generate_hint?user_id=a&word_id=2",
        "https://lexitrail.com/static/js/main.abc.js",       # bundle: ignore
        "https://storage.googleapis.com/lx/hints/1.png",     # image: ignore
        "https://api.lexitrail.com/wordsets/1/words",        # data: ignore
    ]
    r = count_hints(trace)
    if r["total"] != 2 or r["distinct"] != 2:
        print(f"SELF-TEST FAIL: expected exactly the 2 API calls, got {r}")
        ok = False

    # (2) it stays silent on a trace with nothing to report -- including one
    #     that CONTAINS the word "hint", which is the whole point of anchoring
    #     on the route.
    clean = ["https://lexitrail.com/static/css/hint-image.css",
             "https://api.lexitrail.com/wordsets/1/words"]
    r = count_hints(clean)
    if r["total"] != 0:
        print(f"SELF-TEST FAIL: expected silence on a hint-shaped non-API "
              f"trace, got {r}")
        ok = False

    print("SELF-TEST PASS" if ok else "SELF-TEST FAIL")
    return EXIT_PASS if ok else EXIT_FAIL


def browse(page, seen, seconds=6):
    """Scroll the card grid so every card mounts, then settle."""
    page.mouse.wheel(0, 1200)
    page.wait_for_timeout(2_000)
    page.mouse.wheel(0, -1200)
    page.wait_for_timeout(seconds * 1_000)


def run(url, headed=False):
    from playwright.sync_api import sync_playwright

    seen, blocked, leaked = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})

        def guard(route):
            if ANALYTICS_RE.search(route.request.url):
                blocked.append(route.request.url)
                route.abort()
            else:
                route.continue_()

        ctx.route("**/*", guard)
        page = ctx.new_page()
        page.on("request", lambda r: seen.append(r.url))
        page.on("requestfinished",
                lambda r: leaked.append(r.url)
                if ANALYTICS_RE.search(r.url) else None)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3_000)
            enter_practice(page)
        except RuntimeError as e:
            print(f"BLIND: {e}")
            browser.close()
            return EXIT_BLIND

        # The first-visit "How to play" overlay is aria-modal and intercepts
        # pointer events, so the Show Hints click silently retries for 30s and
        # the CONTROL reads 0 -- i.e. the rig, not the app, produces the BLIND.
        # Dismissed explicitly rather than waited out.
        try:
            page.get_by_role("button", name="Got it").first.click(timeout=5_000)
            page.wait_for_timeout(1_000)
        except Exception:                                   # noqa: BLE001
            pass  # not shown on a repeat visit; absence is fine

        cards = page.locator(".word-card-front").count()
        if cards == 0:
            print("BLIND: practice view reached but 0 cards rendered -- the "
                  "probe never exercised WordCard, so a zero says nothing")
            browser.close()
            return EXIT_BLIND

        # ---- ARM A: hints hidden (default) --------------------------------
        mark_a = len(seen)
        browse(page, seen)
        arm_a = count_hints(seen[mark_a:])

        # ---- ARM B: control -- hints shown --------------------------------
        # 🔴 The mark goes BEFORE the click, not after it. Toggling hints on
        # re-runs WordCard's effect for every mounted card, so the control's
        # requests fire DURING the click -- a mark taken afterwards excludes
        # exactly the events it exists to observe, and the run reads BLIND on a
        # working site. Measured: 10 requests fire on the click itself.
        mark_b = len(seen)
        toggled = False
        try:
            page.get_by_role("button", name="Show Hints").first.click(
                timeout=10_000)
            toggled = True
        except Exception as e:                        # noqa: BLE001
            print(f"BLIND: could not toggle hints on: {e}")
        if toggled:
            browse(page, seen)
            # Assert the toggle actually MOVED state: a click that silently
            # no-ops (the "How to play" modal used to intercept it) leaves the
            # label unchanged and would otherwise be indistinguishable from a
            # site that issues no hint traffic.
            labels = page.eval_on_selector_all(
                "button.game-settings-button", "els => els.map(e => e.innerText)")
            if "Hide Hints" not in labels:
                print(f"BLIND: clicked Show Hints but the labels are {labels} "
                      "-- the toggle did not change state")
                toggled = False
        arm_b = count_hints(seen[mark_b:])

        browser.close()

    print(f"cards rendered      {cards}")
    print(f"ARM A hints HIDDEN  {arm_a['total']} hint requests "
          f"({arm_a['distinct']} distinct)")
    print(f"ARM B hints SHOWN   {arm_b['total']} hint requests "
          f"({arm_b['distinct']} distinct)   <- positive control")
    print(f"analytics blocked   {len(blocked)}   leaked {len(leaked)}")
    if leaked:
        print(f"FAIL: analytics beacons completed: {leaked[:3]}")
        return EXIT_FAIL

    if not toggled or arm_b["total"] == 0:
        print("BLIND: the control fired 0 hint requests, so ARM A's zero "
              "cannot be distinguished from a probe that sees nothing")
        return EXIT_BLIND
    if arm_a["total"]:
        print(f"FAIL: {arm_a['total']} hint requests while hints were hidden: "
              f"{list(arm_a['by_url'])[:3]}")
        return EXIT_FAIL
    print("PASS: no hint traffic while hints are hidden, and the control fired")
    return EXIT_PASS


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=URL_DEFAULT)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    return self_test() if a.self_test else run(a.url, a.headed)


if __name__ == "__main__":
    sys.exit(main())
