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
"""
from __future__ import annotations

import argparse
import statistics
import sys

from playwright.sync_api import sync_playwright

MARK = "lt:first-card"
DEFAULT_URL = "https://lexitrail.com/"


def one_run(ctx, url: str, timeout_ms: int) -> tuple[float | None, str | None]:
    """Drive the guest journey to practice and read the mark. (ms, error)."""
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
            return None, "no wordsets nav link after Try"

        # PRACTICE specifically. The list also offers due/excluded/test buttons,
        # and "extremely fast to get to practice" is the bar in #266 -- timing a
        # different mode would answer a question nobody asked.
        try:
            page.wait_for_selector("button.wordset-button-practice", timeout=timeout_ms)
        except Exception:
            return None, "no practice control on /wordsets"
        page.query_selector_all("button.wordset-button-practice")[0].click()

        # Wait for the MARK, not for a selector. If it never arrives we say so.
        try:
            page.wait_for_function(
                f"() => performance.getEntriesByName({MARK!r}).length > 0",
                timeout=timeout_ms,
            )
        except Exception:
            return None, f"mark {MARK!r} never appeared (build predates #266?)"

        ms = page.evaluate(f"() => performance.getEntriesByName({MARK!r})[0].startTime")
        # A mark emitted more than once would mean the once-guard regressed; the
        # metric would still read [0] and hide it, so check rather than assume.
        n = page.evaluate(f"() => performance.getEntriesByName({MARK!r}).length")
        if n != 1:
            return None, f"mark emitted {n} times — the once-guard has regressed"
        return float(ms), None
    finally:
        page.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--runs", type=int, default=5,
                    help="repeat count; the MEDIAN is reported (one run is noise)")
    ap.add_argument("--budget-ms", type=float, default=None,
                    help="fail with 1 if the median exceeds this")
    ap.add_argument("--timeout-ms", type=int, default=30000)
    args = ap.parse_args()

    samples: list[float] = []
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for i in range(args.runs):
            # A FRESH context per run. Sharing one would let run 2..N read run 1's
            # warm cache, which measures the wrong journey -- the issue is about a
            # user arriving, not about re-entering.
            ctx = browser.new_context(viewport={"width": 390, "height": 844})
            ms, err = one_run(ctx, args.url, args.timeout_ms)
            ctx.close()
            if err:
                errors.append(f"run {i+1}: {err}")
            else:
                samples.append(ms)
                print(f"  run {i+1}: {ms:8.1f} ms")
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

    if args.budget_ms is not None and med > args.budget_ms:
        print(f"SLOW: median {med:.1f} ms exceeds budget {args.budget_ms:.1f} ms",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
