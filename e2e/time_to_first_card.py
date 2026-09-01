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
# issue-266 follow-up: the two cuts INSIDE `app`. Optional by construction --
# a build predating them still measures network/parse/app exactly as before,
# and the sub-split is reported absent rather than the run failing. Prod lags
# this repo, so the harness has to stay useful against a deployment that does
# not carry the marks yet.
AUTH_MARK = "lt:auth-settled"
REQ_MARK = "lt:wordsets-requested"
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
        # Read the sub-marks WITHOUT waiting: both are emitted strictly before
        # the first card, so if they are going to appear they already have. A
        # wait here would turn "this build predates the marks" into a 30s
        # timeout on every run.
        nav["sub"] = page.evaluate(
            """(names) => Object.fromEntries(names.map(n => {
                 const e = performance.getEntriesByName(n);
                 return [n, e.length === 1 ? e[0].startTime : null];
               }))""", [AUTH_MARK, REQ_MARK])
        # issue-266: read the resource timeline in the SAME evaluate pass as
        # the marks, before the page closes. Unconditional rather than gated on
        # the CLI flag -- it is one cheap read, and gating it would mean a run
        # that turned out to be interesting could not be re-examined without a
        # second visit to a site whose timings differ run to run.
        nav["res"] = page.evaluate(_RESOURCE_JS)
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


def app_split(ms: float, nav: dict) -> dict | None:
    """Split the `app` phase into its three named parts, or None when either
    sub-mark is missing.

    ALL-OR-NOTHING on purpose. With one mark present two of the three parts are
    still computable, and reporting those is the tempting thing. But the parts
    are only meaningful as a decomposition that SUMS to `app` -- a partial one
    invites reading a two-way split as though the third part were zero, which
    is the reassuring direction. Absent is reported as absent.

    A mark seen more than once yields None from the reader above (`length ===
    1`), so a regressed once-guard arrives here as missing rather than as a
    first-entry number that quietly measures something else.
    """
    sub = nav.get("sub") or {}
    auth, req = sub.get(AUTH_MARK), sub.get(REQ_MARK)
    if auth is None or req is None:
        return None
    parts = {
        "to_auth": auth - nav["dcl"],
        "auth_to_req": req - auth,
        "req_to_card": ms - req,
    }
    # A NEGATIVE part is not a duration. The three parts are a TELESCOPING sum,
    # so they add up to `app` no matter what order the marks fired in -- which
    # means "the parts sum to app" cannot detect a violated ordering, and the
    # self-test asserting it passed while this was wrong on every live run.
    #
    # Measured 2026-09-01, first run after the marks deployed:
    #
    #     app 1215.0 = ->auth 82.6 + auth->req -63.6 + req->card 1196.0
    #
    # `lt:wordsets-requested` fires ~70 ms BEFORE `lt:auth-settled` on every
    # run. The decomposition assumed auth gates the fetch; it does not -- the
    # wordset list is public and requested on mount. So the middle "phase" is
    # an overlap, not a wait, and printing -63.6 as a part invites reading it
    # as one. Reported as a violated precondition instead.
    parts["ordering_ok"] = all(v >= 0 for k, v in parts.items())
    return parts


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



# issue-266: WHAT OCCUPIES `req_to_card`. `--phases` narrowed the fixed cost to
# this one part (~1196 ms of a ~1215 ms `app`), and the earlier probe trace put
# roughly 520 ms of it in no named phase at all. The tempting next move is an
# in-app mark on the words request -- but the browser already records every
# fetch, so Resource Timing answers it with NO app change, which also means the
# measurement works against a prod build that predates any new mark.
#
# WHY COVERAGE, AND NOT A LIST OF REQUESTS
# ----------------------------------------
# A list of requests inside the window invites reading the largest one as "the
# cause". The question that actually discriminates is whether ANYTHING was in
# flight: if the window is fully covered by requests, the cost is network and
# the fix is fetch scheduling; if part of it is covered by NOTHING, the app is
# idle -- waiting on itself -- and no amount of request reordering touches it.
#
# WHY EVERY RESOURCE AND NOT JUST THE API
# ---------------------------------------
# `redundant_fetches.py`'s `DATA_RE` deliberately matches only payload URLs,
# because its question is "did we fetch the same bytes twice". Reusing it here
# would be the same word for a different job: every resource it filters out is
# one that could have been occupying the window, so a narrow matcher can only
# ever make the gap look BIGGER. That is the direction that flatters the "the
# app is idle" reading, so the matcher is deliberately the widest one available
# -- scripts, styles, images, XHR, everything the browser recorded.

_RESOURCE_JS = """() => performance.getEntriesByType('resource').map(e => ({
  name: e.name, start: e.startTime, end: e.responseEnd,
}))"""


def uncovered_spans(start: float, end: float,
                    intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """The parts of [start, end] covered by NO interval, as merged spans.

    Pure and total: the live reading is one call to this over whatever the
    browser recorded, so every judgement about the gap is a property of this
    function and can be tested without a browser.

    Intervals are clipped to the window before merging. An interval that starts
    before `start` (a request already in flight when the window opens) still
    covers the beginning of it, and dropping such a request -- the naive
    `if i.start >= start` filter -- would report its coverage as idle."""
    clipped = sorted((max(a, start), min(b, end))
                     for a, b in intervals if min(b, end) > max(a, start))
    spans: list[tuple[float, float]] = []
    cursor = start
    for a, b in clipped:
        if a > cursor:
            spans.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < end:
        spans.append((cursor, end))
    return spans


def request_split(ms: float, nav: dict) -> dict | None:
    """Coverage of the `req_to_card` window, or None when it cannot be measured.

    THREE-STATE, like every sibling detector here. "I could not read the
    resource timeline" must never render as "the window was idle", because
    those two produce the same shape -- an uncovered window -- from opposite
    facts. No entries at all, or a timeline whose `end` values are all zero,
    is reported absent rather than as 100% idle."""
    sub = nav.get("sub") or {}
    req = sub.get(REQ_MARK)
    res = nav.get("res")
    if req is None or not res:
        return None
    # A cross-origin resource without Timing-Allow-Origin still exposes
    # startTime and responseEnd, so a zero here is not the CORS case -- it is a
    # timeline we did not read properly. Refuse rather than treat 0 as "ended
    # at navigation start", which would make every such entry cover the whole
    # window and hide a real gap.
    if all(not r.get("end") for r in res):
        return None
    window = ms - req
    if window <= 0:
        return None
    spans = uncovered_spans(req, ms, [(r["start"], r["end"]) for r in res])
    idle = sum(b - a for a, b in spans)
    widest = max(spans, key=lambda s: s[1] - s[0], default=None)
    return {
        "window": window,
        "idle": idle,
        "idle_pct": 100.0 * idle / window,
        "widest": (widest[1] - widest[0]) if widest else 0.0,
        # Relative to the mark, so the number is readable against the phase
        # split printed on the line above it rather than against page load.
        "widest_at": (widest[0] - req) if widest else None,
        "n_resources": len(res),
        # issue-266: WHO BRACKETS THE HOLE. "there is a 370 ms idle span" is not
        # yet actionable -- the actionable form is "the app finishes X and does
        # not ask for Y for 370 ms". These are the last resource to END at or
        # before the span opens and the first to START at or after it closes,
        # which is the pair a reader needs to look for the await between them.
        #
        # Nearest-by-time, NOT nearest-in-list-order: the resource array is in
        # startTime order, so the entry adjacent to the hole in the list can be
        # a long request that started much earlier and is still in flight.
        "before": _nearest(res, widest[0], "end", before=True) if widest else None,
        "after": _nearest(res, widest[1], "start", before=False) if widest else None,
    }


def _nearest(res: list[dict], t: float, key: str, *, before: bool) -> str | None:
    """Name of the resource whose `key` time is closest to `t` on one side.

    Ties broken by taking the LAST match scanning in time order, so a burst of
    requests sharing a timestamp reports the one adjacent to the hole rather
    than an arbitrary member of the burst."""
    cands = [r for r in res if (r.get(key, 0) <= t if before else r.get(key, 0) >= t)]
    if not cands:
        return None
    pick = max(cands, key=lambda r: r[key]) if before else min(cands, key=lambda r: r[key])
    # Basename only: full CDN URLs are ~120 chars and would wrap the line the
    # reader is scanning, and the discriminating part is always the tail.
    return pick["name"].rsplit("/", 1)[-1][:44] or pick["name"][:44]


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

    # app_split: the all-or-nothing arm is the one that would ship untested,
    # because prod WILL carry both marks once this deploys and the missing-mark
    # path then becomes unreachable from a live run.
    nav = {"dcl": 100.0, "sub": {AUTH_MARK: 300.0, REQ_MARK: 500.0}}
    got = app_split(1000.0, nav)
    want = {"to_auth": 200.0, "auth_to_req": 200.0, "req_to_card": 500.0,
            "ordering_ok": True}
    if got != want:
        print(f"FAIL app_split: {got} != {want}", file=sys.stderr); ok = False
    elif sum(v for k, v in want.items() if k != "ordering_ok") != 1000.0 - nav["dcl"]:
        print("FAIL app_split: parts do not sum to `app`", file=sys.stderr); ok = False

    # issue-266: uncovered_spans is the whole judgement about the gap, so it
    # gets both directions. A detector that can only ever report "idle" would
    # confirm the hypothesis it was built to test.
    #
    # (1) KNOWN-POSITIVE: a real hole between two requests.
    got_u = uncovered_spans(0.0, 100.0, [(0.0, 30.0), (70.0, 100.0)])
    if got_u != [(30.0, 70.0)]:
        print(f"FAIL uncovered: {got_u} != [(30.0, 70.0)]", file=sys.stderr); ok = False

    # (2) KNOWN-NEGATIVE: fully covered, including an OVERLAPPING pair -- the
    # merge must not report the overlap as a hole. Without this arm a coverage
    # bug reads as an idle gap, which is the finding this flag exists to make,
    # i.e. exactly the direction that would go unquestioned.
    for covered, why in (([(0.0, 100.0)], "one spanning request"),
                         ([(0.0, 60.0), (40.0, 100.0)], "an overlapping pair"),
                         ([(0.0, 50.0), (50.0, 100.0)], "two abutting requests")):
        got_c = uncovered_spans(0.0, 100.0, covered)
        if got_c != []:
            print(f"FAIL uncovered: {got_c} != [] for {why}", file=sys.stderr); ok = False

    # (3) THE STRADDLE. A request already in flight when the window opens is the
    # naive `start >= window_start` filter's blind spot, and dropping it would
    # report its coverage as idle -- inventing a gap at the front of the window,
    # which is precisely where the reported one sits.
    got_s = uncovered_spans(50.0, 100.0, [(10.0, 80.0)])
    if got_s != [(80.0, 100.0)]:
        print(f"FAIL uncovered straddle: {got_s} != [(80.0, 100.0)]", file=sys.stderr); ok = False

    # (4) request_split REFUSES rather than reporting a fully-idle window. Both
    # unreadable shapes must return None: no entries at all, and entries whose
    # `end` is uniformly zero (a timeline we failed to read, NOT the CORS case
    # -- responseEnd survives a missing Timing-Allow-Origin).
    base = {"dcl": 100.0, "sub": {AUTH_MARK: 300.0, REQ_MARK: 500.0}}
    for res, why in ((None, "no resource read"), ([], "an empty timeline"),
                     ([{"name": "x", "start": 0.0, "end": 0.0}], "all-zero ends")):
        got_r = request_split(1000.0, {**base, "res": res})
        if got_r is not None:
            print(f"FAIL request_split: returned {got_r} for {why} "
                  f"instead of refusing", file=sys.stderr); ok = False

    # (5) ...and DOES measure when it can, so (4) is not passing by never working.
    got_r = request_split(1000.0, {**base,
                                   "res": [{"name": "a", "start": 500.0, "end": 700.0}]})
    if got_r is None or abs(got_r["idle"] - 300.0) > 1e-9 or abs(got_r["window"] - 500.0) > 1e-9:
        print(f"FAIL request_split: {got_r} does not measure a 300ms idle tail",
              file=sys.stderr); ok = False

    # THE ARM THE SUM-CHECK CANNOT SEE. The parts telescope, so they add to
    # `app` for ANY mark order -- which is exactly why the sum assertion above
    # passed on live data where the order was wrong. This is the control that
    # discriminates, added only after the live run produced -63.6 ms and the
    # self-test stayed green. Marks reversed: request BEFORE auth.
    rev = {"dcl": 100.0, "sub": {AUTH_MARK: 500.0, REQ_MARK: 300.0}}
    got_rev = app_split(1000.0, rev)
    if got_rev is None:
        print("FAIL app_split: refused a reversed pair; it should REPORT it",
              file=sys.stderr); ok = False
    else:
        if got_rev["ordering_ok"] is not False:
            print("FAIL app_split: reversed marks did not set ordering_ok False",
                  file=sys.stderr); ok = False
        if got_rev["auth_to_req"] >= 0:
            print("FAIL app_split: reversed marks did not yield a negative part",
                  file=sys.stderr); ok = False
        tot = sum(v for k, v in got_rev.items() if k != "ordering_ok")
        if tot != 1000.0 - rev["dcl"]:
            print("FAIL app_split: the reversed parts should STILL sum to app "
                  "-- if they do not, the telescoping claim is wrong and this "
                  "whole control is testing something else", file=sys.stderr)
            ok = False

    for bad, why in (({"dcl": 100.0, "sub": {AUTH_MARK: 300.0, REQ_MARK: None}}, "one mark absent"),
                     ({"dcl": 100.0, "sub": {}}, "neither mark present"),
                     ({"dcl": 100.0}, "no sub read at all")):
        try:
            got_bad = app_split(1000.0, bad)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL app_split: raised {type(exc).__name__} with {why} "
                  f"instead of returning None", file=sys.stderr)
            ok = False
            continue
        if got_bad is not None:
            print(f"FAIL app_split: returned {got_bad} with {why}",
                  file=sys.stderr); ok = False

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
    ap.add_argument("--requests", action="store_true",
                    help="also report how much of req->card had NOTHING in "
                         "flight (issue-266: is the gap network, or is it idle?)")
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
    app_parts: list[dict] = []
    req_parts: list[dict] = []
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
            sub = app_split(ms, nav)
            if sub is not None:
                app_parts.append(sub)
                flag = "" if sub["ordering_ok"] else "   <- ORDERING VIOLATION"
                print(f"            app {ph['app']:7.1f}  =  ->auth {sub['to_auth']:6.1f}"
                      f" + auth->req {sub['auth_to_req']:6.1f}"
                      f" + req->card {sub['req_to_card']:6.1f}{flag}")
                if args.requests:
                    rq = request_split(ms, nav)
                    if rq is None:
                        # Absent, not zero. See request_split's docstring: an
                        # unreadable timeline and a fully idle window are the
                        # same shape from opposite facts.
                        print("            requests: CANNOT MEASURE "
                              "(no resource timeline on this run)")
                    else:
                        req_parts.append(rq)
                        print(f"            req->card {rq['window']:7.1f}  =  "
                              f"idle {rq['idle']:6.1f} ({rq['idle_pct']:4.1f}%)"
                              f" over {rq['n_resources']} resources;"
                              f" widest idle span {rq['widest']:6.1f}"
                              f" at +{rq['widest_at']:.1f}")
                        if rq["widest"] > 50.0:
                            # Only for a hole big enough to be worth chasing --
                            # naming the neighbours of a 5 ms gap is noise that
                            # would train the reader to skip the line.
                            print(f"              hole brackets: after "
                                  f"{rq['before']!r} -> before {rq['after']!r}")
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
        if app_parts:
            med_ap = {k: statistics.median([a[k] for a in app_parts])
                      for k in ("to_auth", "auth_to_req", "req_to_card")}
            print(f"  app split (median of {len(app_parts)}): "
                  f"DCL->auth {med_ap['to_auth']:.1f}"
                  f" | auth->wordsets-requested {med_ap['auth_to_req']:.1f}"
                  f" | requested->first-card {med_ap['req_to_card']:.1f}")
            bad = [a for a in app_parts if not a["ordering_ok"]]
            if bad:
                # Loud, and it does NOT invalidate the outer network/parse/app
                # split -- that one has no ordering assumption in it. Only the
                # sub-parts are affected, and only in what they MEAN.
                print(f"  🔴 ORDERING VIOLATION on {len(bad)}/{len(app_parts)} run(s): "
                      f"a negative part means the marks did not fire in the assumed "
                      f"order, so the middle figure is an OVERLAP, not a wait. "
                      f"The outer network/parse/app split is unaffected.")
        if req_parts:
            # issue-266: report the SPLIT, not a median idle. Across 25 runs on prod (2026-09-01) the
            # idle is bimodal -- a run either carries a ~200-460 ms hole or it
            # carries none -- and a median would land between the two modes on a
            # value no run ever produced, which is the single most misleading
            # number this harness could print.
            big = [r for r in req_parts if r["widest"] > 50.0]
            small = [r for r in req_parts if r["widest"] <= 50.0]
            print(f"  req->card idle: {len(big)}/{len(req_parts)} run(s) carry a "
                  f">50ms hole")
            for label, group in (("with hole", big), ("without", small)):
                if not group:
                    continue
                print(f"    {label:<10} req->card median "
                      f"{statistics.median([r['window'] for r in group]):7.1f} ms"
                      f"  (widest idle median "
                      f"{statistics.median([r['widest'] for r in group]):6.1f})")
        else:
            # NOT silence. A build predating the sub-marks and a build whose
            # once-guard regressed both land here, and both are worth saying
            # out loud -- an absent split must not read as "app has no parts".
            print("  app split: UNAVAILABLE -- lt:auth-settled / "
                  "lt:wordsets-requested absent (build predates them?)")
        print("  NB `app` is a REMAINDER, not a measurement of computation.")

    if args.budget_ms is not None and med > args.budget_ms:
        print(f"SLOW: median {med:.1f} ms exceeds budget {args.budget_ms:.1f} ms",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
