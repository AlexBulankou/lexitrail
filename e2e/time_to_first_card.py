#!/usr/bin/env python3
"""Time-to-first-card — the NUMBER lexitrail#266 asks for.

WHY THIS EXISTS
---------------
#266 is Alex's: *"big datasets slow to load. Pre cache and optimize so the user is
extremely fast to get to practice."* The bar is his phrasing, and the issue asks
that the close be a number rather than a feel.

PR #287 removed two costs on that path — a sequential-fetch waterfall and an
O(n*m) join measured at 77.5ms for 5k words — and deliberately did NOT claim to
have answered the issue, because "strictly less work, therefore cannot be slower"
is not "extremely fast to practice". This is the other half.

WHY IT READS A MARK AND NOT A SELECTOR
--------------------------------------
Waiting for `.container` or a card class needs no app change and is the tempting
option. It also decays silently: restyle or rename the card and the harness keeps
returning a plausible number for a different event. `lt:first-card` is emitted
once, from an effect (so it lands after React commits, i.e. after paint, not when
we decided to paint), and if it is missing this reports CANNOT-TELL rather than
substituting a proxy.

THREE OUTCOMES, AND `3` IS NOT `0`
-----------------------------------
    0  measured  — prints ms from navigation start, per run and median
    1  SLOW      — median above --budget-ms, when one is given
    3  CANNOT-TELL — the journey did not reach practice, or the mark is absent

The mark is absent on any build predating #266's app change, which is the honest
state for this harness against current prod: it means "not deployed yet", NOT
"fast". Those must not share an exit code — a perf check that reports success
when it measured nothing is the failure this repo keeps writing down.

--phases: WHERE THE FIXED COST GOES
-----------------------------------
PR #289 measured the total and split it by DATASET: ~1960 ms fixed, ~317 ms
dataset-dependent, about 86/14 at the biggest live set. That retired the
issue's own premise as the lever -- pre-caching the per-word path is bounded
above by the 14%. It did NOT say where the 1.96 s goes, so nothing yet points
at a fix.

`--phases` splits it by TIME, off `PerformanceNavigationTiming` and the mark:

    network   0 -> responseEnd                 the HTML: DNS, connect, TTFB
    parse     responseEnd -> DOMContentLoaded  bundle download + parse + exec
    app       DOMContentLoaded -> lt:first-card  everything we wrote

No app change was needed for this -- the browser records all three already.
That is the point of doing it before adding marks: an in-app mark can only
measure a phase somebody already suspected, and the measurement below moves
most of the cost into the phase nobody had instrumented.

⚠️ The three phases sum to the mark, and `app` is a REMAINDER, not a
measurement of any one thing. A remainder is the honest shape here -- naming
its parts needs in-app marks, which is the next slice -- but do not read it as
"time spent computing". It contains an idle gap.

WHY navCount IS ASSERTED
------------------------
Every number above is relative to the CURRENT document's navigation start. The
journey crosses `/` -> `/wordsets` -> `/game/<id>/PRACTICE`, and if any of those
were a real document load the timeline would reset and `markStart` would time
only the last leg -- a plausible, much smaller, wrong number. Measured on prod
2026-09-01: `navigation` entries == 1, so it is one SPA timeline and the mark
does span the whole arrival. Asserted per run rather than trusted, because a
router change could make it false without anything else moving.
"""
from __future__ import annotations

import argparse
import statistics
import sys

from playwright.sync_api import sync_playwright

MARK = "lt:first-card"
DEFAULT_URL = "https://lexitrail.com/"


def one_run(ctx, url: str, timeout_ms: int,
            wordset: str | None = None) -> tuple[float | None, str | None, dict]:
    """Drive the guest journey to practice and read the mark.

    (ms, error, nav). `nav` carries the navigation-timing cut points for
    `--phases` and is `{}` on any early return -- an empty dict is not a
    timeline that failed the navCount check, and `phase_split` distinguishes
    them: `{}` yields None because `.get("navCount")` is None, never 1."""
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        # Same journey shape as redundant_fetches.py -- deliberately, so the two
        # harnesses agree about what "reaching practice" means.
        page.click("button.try-button", timeout=timeout_ms)

        # Try does NOT land on the wordset list. It stays on `/` and reveals a nav
        # link; the wordset controls only exist after that navigation. My first
        # version clicked straight through to `.wordset-button` and returned "no
        # wordset controls" on every run -- a real CANNOT-TELL, but for a journey
        # reason rather than the missing-mark reason it was written to detect.
        # Traced against prod rather than guessed: Try -> a.nav-wordsets-link ->
        # /wordsets -> button.wordset-button-practice.
        try:
            page.click("a.nav-wordsets-link", timeout=timeout_ms)
        except Exception:
            return None, "no wordsets nav link after Try", {}

        # PRACTICE specifically. The list also offers due/excluded/test buttons,
        # and "extremely fast to get to practice" is the bar in #266 -- timing a
        # different mode would answer a question nobody asked.
        try:
            page.wait_for_selector("button.wordset-button-practice", timeout=timeout_ms)
        except Exception:
            return None, "no practice control on /wordsets", {}

        # issue-266: WHICH wordset is the whole question. The issue is about BIG
        # datasets, and the first button in DOM order is HSK1 -- 150 words against
        # HSK6's 2500 (measured via /wordsets/<id>/words). Timing the first button
        # answers "how fast is the smallest set", which is not what was asked.
        #
        # Anchored on the wordset's visible NAME rather than an index, because
        # index order is a rendering detail that can change without anyone
        # noticing the measurement silently moved to a different dataset.
        if wordset:
            btns = page.query_selector_all("button.wordset-button-practice")
            target = None
            for b in btns:
                # NOT `closest('[class*=wordset]')`: the button's OWN class is
                # `wordset-button-practice`, so closest() matches the button itself
                # and returns innerText "Practice" for every row. parentElement is
                # the row: "HSK1 | Practice | Due Today | Show Excluded | Test!".
                row = b.evaluate("el => el.parentElement ? el.parentElement.innerText : ''")
                if wordset.lower() in (row or "").lower():
                    target = b
                    break
            if target is None:
                names = [b.evaluate("el => el.parentElement ? el.parentElement.innerText : ''")
                         .split("\n")[0] for b in btns]
                return None, f"wordset {wordset!r} not found among {names}", {}
            target.click()
        else:
            page.query_selector_all("button.wordset-button-practice")[0].click()

        # Wait for the MARK, not for a selector. If it never arrives we say so.
        try:
            page.wait_for_function(
                f"() => performance.getEntriesByName({MARK!r}).length > 0",
                timeout=timeout_ms,
            )
        except Exception:
            return None, f"mark {MARK!r} never appeared (build predates #266?)", {}

        ms = page.evaluate(f"() => performance.getEntriesByName({MARK!r})[0].startTime")
        # A mark emitted more than once would mean the once-guard regressed; the
        # metric would still read [0] and hide it, so check rather than assume.
        n = page.evaluate(f"() => performance.getEntriesByName({MARK!r}).length")
        if n != 1:
            return None, f"mark emitted {n} times — the once-guard has regressed", {}
        nav = page.evaluate(_PHASE_JS)
        return float(ms), None, nav
    finally:
        page.close()


# The three cut points, read once per run. `responseEnd` and
# `domContentLoadedEventEnd` come from the SAME PerformanceNavigationTiming
# entry as `startTime: 0`, so all four numbers share one origin and the
# subtractions below are meaningful without any clock conversion.
_PHASE_JS = """() => {
  const navs = performance.getEntriesByType('navigation');
  if (navs.length !== 1) return {navCount: navs.length};
  const n = navs[0];
  return {navCount: 1, responseEnd: n.responseEnd,
          dcl: n.domContentLoadedEventEnd, loadEnd: n.loadEventEnd};
}"""


def phase_split(ms: float, nav: dict) -> dict | None:
    """(network, parse, app) for one run, or None when the timeline is not one
    SPA navigation -- in which case `ms` is not what it appears to be and the
    caller must say so rather than print a smaller, plausible number."""
    if nav.get("navCount") != 1:
        return None
    return {
        "network": nav["responseEnd"],
        "parse": nav["dcl"] - nav["responseEnd"],
        "app": ms - nav["dcl"],
    }


def self_test() -> int:
    """Validate `phase_split` itself, the way redundant_fetches.py validates its
    counter: can it produce a split, and does it REFUSE on the one input shape
    that makes the total meaningless? The refusing arm is unreachable on a
    healthy prod (navCount is 1 there), so it would otherwise ship untested and
    be exercised for the first time on the day a router change breaks it."""
    ok = True

    got = phase_split(1000.0, {"navCount": 1, "responseEnd": 100.0,
                               "dcl": 400.0, "loadEnd": 410.0})
    want = {"network": 100.0, "parse": 300.0, "app": 600.0}
    if got != want:
        print(f"FAIL split: {got} != {want}", file=sys.stderr); ok = False
    elif sum(want.values()) != 1000.0:
        print("FAIL split: phases do not sum to the mark", file=sys.stderr); ok = False

    # THE ARM THAT MATTERS. Two navigations means the timeline reset mid-journey
    # and `ms` timed only the last leg. Returning a split here would print three
    # small, internally-consistent, wrong numbers.
    for bad, why in ((({"navCount": 2, "responseEnd": 1.0, "dcl": 2.0}), "reset timeline"),
                     ({}, "no timeline read at all")):
        try:
            got_bad = phase_split(1000.0, bad)
        except Exception as exc:  # noqa: BLE001
            # A crash also means the guard is gone, but it is a DIFFERENT
            # signal from a wrong number and must not read as a clean failure.
            print(f"FAIL: split raised {type(exc).__name__} on a {why} "
                  f"instead of returning None", file=sys.stderr)
            ok = False
            continue
        if got_bad is not None:
            print(f"FAIL: split returned {got_bad} for a {why}", file=sys.stderr); ok = False

    print("self-test: PASS" if ok else "self-test: FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--runs", type=int, default=5,
                    help="repeat count; the MEDIAN is reported (one run is noise)")
    ap.add_argument("--budget-ms", type=float, default=None,
                    help="fail with 1 if the median exceeds this")
    ap.add_argument("--timeout-ms", type=int, default=30000)
    ap.add_argument("--phases", action="store_true",
                    help="also split each run into network / parse / app "
                         "(issue-266: WHERE the ~1.96s fixed cost goes)")
    ap.add_argument("--wordset", default=None,
                    help="name to match in the wordset row, e.g. HSK6 (the BIGGEST live set, "
                         "2500 words). Omitted = first button in DOM order = HSK1 (150), which "
                         "is NOT what #266 asks about.")
    ap.add_argument("--self-test", action="store_true",
                    help="validate phase_split's own arms and exit; touches no site")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    samples: list[float] = []
    phases: list[dict] = []
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for i in range(args.runs):
            # A FRESH context per run. Sharing one would let run 2..N read run 1's
            # warm cache, which measures the wrong journey -- the issue is about a
            # user arriving, not about re-entering.
            ctx = browser.new_context(viewport={"width": 390, "height": 844})
            ms, err, nav = one_run(ctx, args.url, args.timeout_ms, args.wordset)
            ctx.close()
            if err:
                errors.append(f"run {i+1}: {err}")
                continue
            samples.append(ms)
            if not args.phases:
                print(f"  run {i+1}: {ms:8.1f} ms")
                continue
            ph = phase_split(ms, nav)
            if ph is None:
                # LOUD, not a dropped column. navCount != 1 means `ms` timed
                # only the last leg of the journey, so the TOTAL is wrong too
                # -- reporting a phase-less row beside good rows would let a
                # number that measures a different thing into the median.
                errors.append(
                    f"run {i+1}: {nav.get('navCount')} navigation entries, not 1 "
                    f"-- the SPA timeline reset, so {ms:.1f} ms does not span "
                    f"the arrival; excluded from the median")
                samples.pop()
                continue
            phases.append(ph)
            print(f"  run {i+1}: {ms:8.1f} ms  =  network {ph['network']:6.1f}"
                  f" + parse {ph['parse']:6.1f} + app {ph['app']:7.1f}")
        browser.close()

    if not samples:
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        print(f"CANNOT-TELL: 0 of {args.runs} runs produced a measurement",
              file=sys.stderr)
        return 3

    med = statistics.median(samples)
    print(f"\ntime-to-first-card: median {med:.1f} ms over {len(samples)}/{args.runs} runs"
          f"  (min {min(samples):.1f}, max {max(samples):.1f})")
    if errors:
        # Partial success is reported, never silently averaged away.
        print(f"  {len(errors)} run(s) failed:", file=sys.stderr)
        for e in errors:
            print(f"    {e}", file=sys.stderr)

    if phases:
        # Median PER PHASE, not a split of the median: the phases of one run
        # sum to that run, but three independent medians need not sum to the
        # median total, so the sum is printed and any gap is shown rather than
        # quietly absorbed into the largest phase.
        med_ph = {k: statistics.median([p[k] for p in phases])
                  for k in ("network", "parse", "app")}
        tot = sum(med_ph.values())
        print(f"  phases (median of {len(phases)}): "
              f"network {med_ph['network']:.1f} ({100*med_ph['network']/tot:.0f}%)"
              f" | parse {med_ph['parse']:.1f} ({100*med_ph['parse']/tot:.0f}%)"
              f" | app {med_ph['app']:.1f} ({100*med_ph['app']/tot:.0f}%)")
        print(f"  (phase medians sum to {tot:.1f} ms vs total median {med:.1f} ms;"
              f" they need not agree exactly -- see the note in the code)")
        print("  NB `app` is a REMAINDER, not a measurement of computation.")

    if args.budget_ms is not None and med > args.budget_ms:
        print(f"SLOW: median {med:.1f} ms exceeds budget {args.budget_ms:.1f} ms",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
