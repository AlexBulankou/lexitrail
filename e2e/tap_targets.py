#!/usr/bin/env python3
"""Render-level tap-target floor check — lexitrail#52 item 3.

WHY THIS EXISTS, and what it does that the unit test cannot
-----------------------------------------------------------
`ui/src/styles/tapTargets.test.js` checks that the CSS *declares* a >=44px
floor. It says so itself, in its own docstring, and explicitly declines to
claim item 3. It passed continuously while **23 of 33 controls on the live
mobile site rendered under 44px** — because a declaration is not an outcome.
A parent with a fixed height, an `align-items: center` on a short flex row, or
a control simply never added to the enumerated selector list all produce a
green unit test over an undersized button.

So this harness measures the **rendered box** in a real browser. It is the
render-level proof the unit test names and disclaims.

THIS IS A DETECTOR, SO IT HAS CONTROLS
--------------------------------------
A detector's broken state and a healthy site produce the same output — silence.
"It didn't report anything" is therefore nearly information-free unless the
detector is known to be able to speak. Two things follow, and both are
deliberate:

  1. `--self-test` drives the measurement over a fixture with a known-small and
     a known-large control and asserts it flags EXACTLY the small one. That
     validates the instrument (can it fire? can it stay silent?) WITHOUT
     asserting anything about the live site — so it does not expire the moment
     someone fixes a real button. A control keyed on today's prod state would.

  2. Outcomes are THREE-state, never two. "I could not reach the page" must not
     render as "the page is clean":

         0  PASS   every visible control measured >= the floor
         1  FAIL   at least one control measured under the floor
         2  BLIND  could not measure (navigation failed, or zero controls found)

     A two-state version would exit 0 on a site that failed to load, which is
     the single most likely way for this check to start lying.

FUNNEL SAFETY (docs/itp-playwright-usability.md 2.3)
----------------------------------------------------
GA4 beacons fire on the guest path. They are aborted on the CONTEXT, with the
REGEX matcher, BEFORE the first navigation — a glob like `**/google-analytics.com/**`
silently misses the real `www.`/`region1.` subdomains and lets live analytics
through. The run reports how many were blocked and asserts that ZERO completed,
so the clean-funnel claim is measured rather than asserted.

This check never clicks anything. It measures a public page, so it cannot reach
the Google sign-in path the doc warns against.

RUNNER CHOICE — a deliberate deviation from the doc, stated rather than silent
------------------------------------------------------------------------------
`docs/itp-playwright-usability.md` 2.4 prescribes a top-level `e2e/` folder with
its own `package.json` and `@playwright/test`. This file honours that section's
actual rule — **nothing in the product tree** (`ui/package.json`,
`ui/package-lock.json`, `ui/src/**`, `backend/app/**` are all untouched) — but
uses Python, because `@playwright/test` is not resolvable on the runner while
`playwright` for Python is, and the browsers are already cached. That buys the
same isolation with no new lockfile and no npm install step. If a node harness
is added later this file should give way to it.

USAGE
    python3 e2e/tap_targets.py --self-test          # validate the instrument
    python3 e2e/tap_targets.py                      # measure prod, ALL viewports
    python3 e2e/tap_targets.py --url http://localhost:3000
    python3 e2e/tap_targets.py --viewport mobile --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict

# lexitrail#163: the pure-measurement half lives in its own module so this
# file has room for the next route (#85). One-way import; see lt_measure.
from lt_measure import (  # noqa: E402  (sys.path shim is the caller's)
    EXIT_PASS, EXIT_FAIL, EXIT_BLIND, _OUTCOME, FLOOR_PX,
    VIEWPORTS, Control, _measure, selftest_detach)
# lexitrail#163 seam: routes grow, so they live in their own file (#85).
from lt_routes import (  # noqa: E402
    ROUTES, PRACTICE_URL_MARKER, WORDSETS_URL_MARKER, SIGNED_OUT_MARKER,
    enter_guest, enter_practice, enter_wordsets,
    _GUEST_FIXTURE_MOVES, _GUEST_FIXTURE_STUCK, _PRACTICE_FIXTURE_NO_NAV)

try:
    from playwright.sync_api import sync_playwright, Error as PlaywrightError
except ImportError:  # pragma: no cover - environment guard
    print("FATAL: playwright for Python is not installed "
          "(pip install playwright && playwright install chromium)", file=sys.stderr)
    raise SystemExit(2)


#: Regex, NOT a glob — see the module docstring and doc 2.3. Substring-matches
#: the full request URL, so it catches www./region1. subdomains that a glob
#: pattern silently misses.
ANALYTICS_RE = re.compile(
    r"googletagmanager\.com|google-analytics\.com|analytics\.google\.com")






def run_viewport(browser, url: str, name: str, route: str = "landing"
                 ) -> tuple[list[Control], int, list[str]]:
    """Measure one (route, viewport). Returns (controls, blocked, completed)."""
    ctx = browser.new_context(**VIEWPORTS[name])
    blocked = 0
    completed: list[str] = []

    def _abort(route):
        nonlocal blocked
        blocked += 1
        route.abort()

    # Installed on the CONTEXT and BEFORE new_page/goto — doc 2.3. Order is
    # load-bearing: a route set after navigation lets the first beacons through.
    ctx.route(ANALYTICS_RE, _abort)
    page = ctx.new_page()
    page.on("requestfinished",
            lambda r: completed.append(r.url) if ANALYTICS_RE.search(r.url) else None)
    try:
        page.goto(url, wait_until="networkidle", timeout=60_000)
    except PlaywrightError as e:
        ctx.close()
        raise RuntimeError(f"navigation to {url} failed: {e}") from e
    enter = ROUTES[route]
    if enter is not None:
        try:
            enter(page)
        except RuntimeError:
            ctx.close()
            raise
    controls = _measure(page)
    ctx.close()
    return controls, blocked, completed


def _report(name: str, controls: list[Control], blocked: int, completed: list[str],
            route: str = "landing") -> int:
    print(f"\n=== {route} / {name} ({VIEWPORTS[name]['viewport']['width']}x"
          f"{VIEWPORTS[name]['viewport']['height']}) ===")
    print(f"analytics: {blocked} blocked, {len(completed)} completed"
          + ("  <- FUNNEL LEAK" if completed else "  (funnel clean)"))
    for u in completed:
        print(f"  LEAKED: {u}")
    if not controls:
        print("BLIND: zero visible interactive controls found — not a clean result.")
        return EXIT_BLIND

    bad = [c for c in controls if c.undersized]
    grouped: dict[str, list[Control]] = {}
    for c in bad:
        grouped.setdefault(c.key, []).append(c)

    print(f"measured {len(controls)} visible controls, "
          f"{len(bad)} under the {FLOOR_PX:.0f}px floor "
          f"({len(grouped)} distinct)")
    for key, group in sorted(grouped.items(), key=lambda kv: min(c.short_side for c in kv[1])):
        c = group[0]
        n = f" x{len(group)}" if len(group) > 1 else ""
        print(f"  FAIL {c.width:6.1f}x{c.height:6.1f}  {key}{n}"
              + (f'  | "{c.text}"' if c.text else ""))
    return EXIT_FAIL if bad else EXIT_PASS


# --------------------------------------------------------------------------
# Instrument control. Validates that the measurement can BOTH fire and stay
# silent, against a fixture whose geometry we set — so it tests the detector,
# not the site, and does not decay when a real button is fixed.
# --------------------------------------------------------------------------
_FIXTURE = """data:text/html,
<html><body style="margin:0">
  <button id="small" style="width:100px;height:20px">too short</button>
  <button id="big"   style="width:100px;height:60px">fine</button>
  <button id="thin"  style="width:20px;height:100px">too narrow</button>
  <button id="hidden" style="display:none">invisible</button>
</body></html>"""


#: Guest-entry controls (#85). Two fixtures, because the entry assertion has to
#: be able to come out BOTH ways -- a check that can only pass is not a check.



# issue-85: HAS the links enter_practice clicks, so the click succeeds and only
# the URL assertion can refuse it. Without them it raises on the click instead,
# and the arm passes with the URL check deleted -- what v1 of this test did.


def self_test(browser) -> int:
    ctx = browser.new_context(**VIEWPORTS["desktop"])
    page = ctx.new_page()
    page.goto(_FIXTURE)
    controls = _measure(page)
    ctx.close()

    by = {c.text: c for c in controls}
    failures: list[str] = []

    # Fires on both the short and the narrow control (the floor is on the SHORT
    # SIDE, so a wide-but-short button must not pass on width alone).
    for want in ("too short", "too narrow"):
        if want not in by:
            failures.append(f"did not measure the {want!r} control at all")
        elif not by[want].undersized:
            failures.append(f"{want!r} measured {by[want].width}x{by[want].height} "
                            f"but was NOT flagged")
    # Stays silent on the compliant control.
    if "fine" not in by:
        failures.append("did not measure the compliant control")
    elif by["fine"].undersized:
        failures.append("flagged the compliant 100x60 control — false positive")
    # Skips the invisible one rather than scoring it either way.
    if "invisible" in by:
        failures.append("measured a display:none control; it has no tap target")

    # --- guest-entry control (#85 AC4) -------------------------------------
    # The dangerous failure is a silent no-op click reported as a measured
    # route. Drive the assertion to BOTH verdicts against fixtures whose
    # behaviour we set, so this tests the entry logic and not the live site.
    ctx = browser.new_context(**VIEWPORTS["desktop"])
    page = ctx.new_page()
    page.goto(_GUEST_FIXTURE_MOVES)
    try:
        enter_guest(page)          # state MOVES -> must return quietly
    except RuntimeError as e:
        failures.append(f"entry raised on a page where the state DID move: {e}")
    page.goto(_GUEST_FIXTURE_STUCK)
    try:
        enter_guest(page)          # state does NOT move -> must raise (-> BLIND)
        failures.append("entry did NOT raise on a click that changed nothing — "
                        "an unreachable route would report as measured")
    except RuntimeError:
        pass
    # --- practice-route URL assertion (#85) --------------------------------
    # Moves state without navigating -- the exact shape that made the old guest
    # route report the homepage as measured. enter_practice must refuse it.
    # --- click-FAILURE path (#85 follow-up) --------------------------------
    # _GUEST_FIXTURE_MOVES has `Try` but NO "Word Sets" link, so guest entry
    # succeeds and the next click TIMES OUT -- the only fixture that reaches the
    # `except PlaywrightError` arms in this module. Without it, dropping the
    # PlaywrightError import leaves the self-test GREEN while every click
    # failure raises NameError instead of degrading to BLIND. That is exactly
    # the bug hc2 found in the #163 extraction, and this file inherited the
    # same blind spot when the routes moved.
    page.goto(_GUEST_FIXTURE_MOVES)
    try:
        enter_wordsets(page)
        failures.append("wordsets entry did NOT raise when the Word Sets click "
                        "could not resolve — the click-failure path is unreachable")
    except RuntimeError:
        pass
    except NameError as e:
        failures.append(f"wordsets entry raised NameError on the click-failure "
                        f"path ({e}) — a missing import, not a graceful BLIND")

    page.goto(_PRACTICE_FIXTURE_NO_NAV)
    try:
        enter_wordsets(page)
        failures.append("wordsets entry did NOT raise on a page that moves "
                        "state without navigating — the #85 failure exactly")
    except RuntimeError:
        pass
    page.goto(_PRACTICE_FIXTURE_NO_NAV)
    try:
        enter_practice(page)
        failures.append("practice entry did NOT raise on a page that moves "
                        "state without navigating — the #85 failure exactly")
    except RuntimeError:
        pass
    ctx.close()

    # --- detach/re-render race (#163 review) -------------------------------
    # Deterministic, no browser: see lt_measure.selftest_detach for why a fake
    # page rather than a timing fixture.
    failures.extend(selftest_detach())

    if failures:
        print("SELF-TEST FAILED — the instrument cannot be trusted:")
        for f in failures:
            print(f"  {f}")
        return EXIT_FAIL
    print("SELF-TEST PASS — detector fires on short AND narrow, stays silent on "
          "compliant, skips invisible; guest entry raises on a no-op click and "
          "stays quiet when the state moves; practice entry refuses a route "
          "that authenticated without navigating, and so does wordsets entry; a "
          "detached node is skipped rather than counted or raised; and a click "
          "that cannot resolve degrades to BLIND.")
    return EXIT_PASS


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="https://lexitrail.com/",
                    help="page to measure (default: live site)")
    # "all" replaces "both", which stopped being true when a third viewport
    # landed (issue-45). "both" is still ACCEPTED and means every viewport, so
    # an existing caller keeps working -- but it would now silently mean three,
    # so the help text says so rather than letting a script author assume two.
    ap.add_argument("--viewport", choices=[*VIEWPORTS, "all", "both"],
                    default="all",
                    help="which viewport(s) to measure. Default: all "
                         f"({len(VIEWPORTS)} today). 'both' is a deprecated "
                         "alias for 'all' and does NOT mean exactly two.")
    ap.add_argument("--route", choices=[*ROUTES, "all"], default="all",
                    help="which journey to measure (#85). Default: all.")
    ap.add_argument("--self-test", action="store_true",
                    help="validate the detector against a known fixture and exit")
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            if args.self_test:
                return self_test(browser)

            names = (list(VIEWPORTS) if args.viewport in ("all", "both")
                     else [args.viewport])
            routes = list(ROUTES) if args.route == "all" else [args.route]
            worst = EXIT_PASS
            payload: dict = {"url": args.url, "floor_px": FLOOR_PX, "routes": {}}
            for route in routes:
                payload["routes"][route] = {}
                for name in names:
                    try:
                        controls, blocked, completed = run_viewport(
                            browser, args.url, name, route)
                    except RuntimeError as e:
                        # BLIND, never PASS. A route we could not reach is not a
                        # route we measured -- AC4.
                        print(f"\n=== {route} / {name} ===\nBLIND: {e}", file=sys.stderr)
                        worst = max(worst, EXIT_BLIND)
                        payload["routes"][route][name] = {"outcome": "blind",
                                                          "error": str(e)}
                        continue
                    rc = _report(name, controls, blocked, completed, route)
                    # A funnel leak is a failure in its own right, independent of sizes.
                    if completed:
                        rc = max(rc, EXIT_FAIL)
                    worst = max(worst, rc)
                    payload["routes"][route][name] = {
                        "outcome": _OUTCOME[rc].lower(),
                        "measured": len(controls),
                        "analytics_blocked": blocked,
                        "analytics_completed": len(completed),
                        "undersized": [asdict(c) for c in controls if c.undersized],
                    }
            if args.json:
                print(json.dumps(payload, indent=2))
            print(f"\nVERDICT: {_OUTCOME[worst]} (exit {worst})")
            return worst
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
