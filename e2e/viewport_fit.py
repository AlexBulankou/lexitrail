#!/usr/bin/env python3
"""Does the practice screen FIT its viewport? Measured by rect (lexitrail#341).

WHY THIS EXISTS RATHER THAN A `visible` COUNT
---------------------------------------------
`#339`'s harness counted a card as visible if its rect INTERSECTS the viewport
at all. A card clipped by 31px still counts. So `visible == total` was green
throughout, and only a screenshot could see the defect — hc2@ caught it by
asking for one instead of accepting the numeric table. This asserts on the rect
(`bottom <= viewport.height`), which is the thing the count could not express.

WHAT IT GUARDS, AND WHY PORTRAIT IS THE INTERESTING ONE
-------------------------------------------------------
Measured on live prod 2026-09-04 (#341):

    mobile_landscape  844x390   scrollH 513   overflow +123
    mobile (portrait) 390x844   scrollH 844   overflow    0
    desktop          1440x900   scrollH 900   overflow    0

Portrait fits with **zero pixels to spare** — `cards-area` uses 592 of 592. That
is the regression this file is really for: any change that adds height to the
practice screen breaks portrait silently, and nothing today would catch it. The
landscape clip is the finding that prompted the work; the portrait zero-margin
is the ongoing risk.

🔴 LANDSCAPE OVERFLOW IS EXPECTED AND MUST NOT FAIL THE CHECK
-------------------------------------------------------------
Per the decision recorded on #341, a phone in landscape cannot show this screen:
minimum content is ~425px (53 stats + 291 card + 44 button + 24 progress +
margins) against 342px available under a 48px fixed navbar — **83px short with
every removable pixel of container chrome already gone**, and the card's 291 is
floored by an 85px image plus 44px tap targets. Landscape scrolls by design.

So landscape is REPORTED, never asserted. Encoding it as a failure would make
this permanently red, and `tap_targets.py` already states the consequence in
this repo's own words: *"a gate people routinely override stops being a gate --
the override becomes the habit."* A check that is always red is not a check.

⚠️ That is also why this does not simply assert "overflow <= 123" for landscape.
Pinning today's number would turn every legitimate landscape change into a red
and would need editing on each one -- the same muting pressure by another route.

THREE-STATE EXIT, same convention as `tap_targets.py`
------------------------------------------------------
    0  PASS   every ASSERTED viewport fits
    1  FAIL   an asserted viewport overflows, or an element is clipped in one
    2  BLIND  could not measure (navigation failed, no container, no cards)

BLIND exists so "I could not look" can never be reported as "the page is clean".
A failed guest login and a healthy page must not produce the same exit.

Usage:
    python3 e2e/viewport_fit.py                      # measure prod, all viewports
    python3 e2e/viewport_fit.py --url http://localhost:3000
    python3 e2e/viewport_fit.py --self-test          # prove the checker can FAIL
    python3 e2e/viewport_fit.py --json
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from lt_measure import EXIT_PASS, EXIT_FAIL, EXIT_BLIND, VIEWPORTS  # noqa: E402
from lt_routes import enter_practice  # noqa: E402

#: Viewports whose overflow is a DEFECT. Landscape is deliberately absent --
#: see the module docstring; it is measured and printed, never asserted.
ASSERTED = ("mobile", "desktop")

#: The container whose children make up the practice screen.
_CONTAINER = ".container"

_PROBE = """() => {
  const c = document.querySelector('.container');
  if (!c) return {error: 'no .container'};
  const kids = [...c.children].map(e => {
    const b = e.getBoundingClientRect();
    return {cls: (e.className || '').toString().split(' ')[0] || e.tagName,
            top: +b.top.toFixed(1), bottom: +b.bottom.toFixed(1),
            h: +b.height.toFixed(1)};
  });
  return {
    vw: innerWidth, vh: innerHeight,
    scrollH: document.documentElement.scrollHeight,
    clientH: document.documentElement.clientHeight,
    cards: document.querySelectorAll('[class*="word-card"]').length,
    kids,
  };
}"""


def _classify(kid: dict, vh: float) -> str:
    """below-fold / clipped / ok for one element against the viewport height."""
    if kid["top"] >= vh:
        return "below-fold"
    if kid["bottom"] > vh:
        return "clipped"
    return "ok"


def measure(page) -> dict:
    """Rects for the practice screen. Raises on an unusable page -> BLIND."""
    r = page.evaluate(_PROBE)
    if r.get("error"):
        raise RuntimeError(r["error"])
    if not r["kids"]:
        raise RuntimeError(".container has no children")
    # A practice screen with no cards is not a fitting screen -- it is a page we
    # failed to reach. Distinguishing this from "fits" is the whole of BLIND.
    if not r["cards"]:
        raise RuntimeError("no word-card elements: practice view not reached")
    r["overflow"] = r["scrollH"] - r["vh"]
    for k in r["kids"]:
        k["state"] = _classify(k, r["vh"])
    return r


def _render(name: str, r: dict, asserted: bool) -> None:
    tag = "ASSERTED" if asserted else "reported"
    print(f"\n=== {name} {r['vw']}x{r['vh']}  scrollH={r['scrollH']}  "
          f"overflow={r['overflow']:+d}  [{tag}]")
    for k in r["kids"]:
        flag = "" if k["state"] == "ok" else f"   <-- {k['state'].upper()}"
        print(f"    {k['cls']:<28} top={k['top']:<7} bottom={k['bottom']:<7} "
              f"h={k['h']}{flag}")


def run(url: str, viewports: list[str]) -> tuple[int, dict]:
    from playwright.sync_api import sync_playwright

    results: dict[str, dict] = {}
    blind: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for name in viewports:
                ctx = browser.new_context(**VIEWPORTS[name])
                page = ctx.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    enter_practice(page)
                    page.wait_for_timeout(2500)
                    results[name] = measure(page)
                except Exception as e:  # noqa: BLE001 - reported, never swallowed
                    print(f"=== {name}: BLIND -- {e}", file=sys.stderr)
                    blind.append(name)
                finally:
                    ctx.close()
        finally:
            browser.close()

    if blind:
        return EXIT_BLIND, results

    failures = []
    for name, r in results.items():
        asserted = name in ASSERTED
        _render(name, r, asserted)
        if not asserted:
            continue
        if r["overflow"] > 0:
            failures.append(f"{name}: page overflows by {r['overflow']}px")
        for k in r["kids"]:
            if k["state"] != "ok":
                failures.append(f"{name}: {k['cls']} is {k['state']} "
                                f"(bottom={k['bottom']} > vh={r['vh']})")

    print()
    if failures:
        for f in failures:
            print(f"FAIL  {f}")
        return EXIT_FAIL, results
    print(f"PASS  {', '.join(ASSERTED)} fit; "
          f"landscape reported above and expected to overflow (#341)")
    return EXIT_PASS, results


def self_test() -> int:
    """Prove the checker can return FAIL -- a check that cannot fail is not one.

    Feeds `_classify` and the overflow arithmetic a synthetic screen that is too
    tall, and a control that fits. Both arms are required: an arm that only ever
    sees the failing case cannot tell a working detector from one stuck on FAIL.
    """
    ok = True
    fits = {"vh": 800, "kids": [{"cls": "a", "top": 0, "bottom": 700, "h": 700}],
            "scrollH": 800}
    tall = {"vh": 390, "kids": [{"cls": "card", "top": 130, "bottom": 421, "h": 291},
                                {"cls": "button", "top": 423, "bottom": 467, "h": 44}],
            "scrollH": 513}

    cases = [
        ("fits -> ok", _classify(fits["kids"][0], fits["vh"]), "ok"),
        ("clipped card", _classify(tall["kids"][0], tall["vh"]), "clipped"),
        ("below-fold button", _classify(tall["kids"][1], tall["vh"]), "below-fold"),
        ("overflow arithmetic", tall["scrollH"] - tall["vh"], 123),
        ("no overflow", fits["scrollH"] - fits["vh"], 0),
    ]
    for label, got, want in cases:
        status = "ok " if got == want else "BAD"
        if got != want:
            ok = False
        print(f"  [{status}] {label}: got {got!r}, want {want!r}")
    print("self-test PASS" if ok else "self-test FAIL")
    return EXIT_PASS if ok else EXIT_FAIL


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default="https://lexitrail.com")
    ap.add_argument("--viewport", action="append", choices=sorted(VIEWPORTS),
                    help="repeatable; default = all three")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        return self_test()

    code, results = run(a.url, a.viewport or list(VIEWPORTS))
    if a.json:
        print(json.dumps({"exit": code, "results": results}, indent=1))
    return code


if __name__ == "__main__":
    sys.exit(main())
