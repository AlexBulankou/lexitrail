#!/usr/bin/env python3
"""Is a practice session actually BOUNDED on the live site? (lexitrail#108, RD-2)

WHY THIS EXISTS AND WHY THE UNIT TESTS DO NOT COVER IT
------------------------------------------------------
`ui/src/utils/session.js` has 37 unit tests and they are good ones. They did not
catch #137 — a bounded session finishing SHORT, 8 of 10 cards, because two
captured cards left the queue via the window rule. That passed every unit test
and was visible only in a rendered view. RD-2's whole value is a finish line the
user can SEE, so the thing to assert is what the user sees.

WHAT THIS ASSERTS
-----------------
On the live practice view, `.progress-info` must carry the SESSION shape with a
denominator no larger than the budget:

    'cards 1–10 of 10'   <- bounded. `progressLabel` against `sessionKeys.size`
    'card 4 of 10'       <- bounded, single-card layout
    'recalled 0 out of 2500'  <- NOT bounded: Game.js's non-session branch

🔴 THE DENOMINATOR IS THE WHOLE TEST. On HSK6 the wordset holds 2500 words, so
an unbound session and a bound one differ by two orders of magnitude in exactly
one number. `session.js`'s own header says the naive `toShow.slice(0, BUDGET)`
would render "10 cards in, 10 cards left, forever" — visually bounded and
functionally endless. That bug produces a *correct-looking* label, so a check
that merely asserted "the session shape is present" would pass on it. Asserting
the denominator against the budget is what makes this a test rather than a
screenshot.

THE BUDGET IS DERIVED, NOT HARDCODED
------------------------------------
Read from `ui/src/utils/streak.js`'s `DEFAULT_GOAL`, which is what
`SESSION_BUDGET` aliases. Hardcoding 10 here would let the harness and the app
drift apart silently, and the harness would then be asserting a number the
product no longer uses — the same reasoning `smoke_backend_content.py` gives for
deriving its route from `wordsets.py` rather than hardcoding it.

⚠️ This deliberately checks `<=`, not `==`. A session legitimately binds FEWER
than the budget when the queue holds fewer words (`sessionOutcome`'s CLEARED
state — "you finished everything available"), and for a due-today queue that is
the best possible outcome, not a shortfall. `== budget` would fail a healthy
small wordset.

THREE OUTCOMES, AND THE THIRD MUST NEVER RENDER AS THE FIRST
------------------------------------------------------------
    exit 0  PASS   a session-shaped label with a denominator within budget
    exit 1  FAIL   the non-session label, or a denominator over budget
    exit 2  BLIND  could not reach practice, no label, or the budget could not
                   be read. NOT a pass. NOT a failure. Go look.

`--self-test` validates the PARSER against synthetic labels, including the
unbounded one, so a run that reports PASS is a run whose instrument has been
shown able to report FAIL.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lt_routes import enter_practice  # noqa: E402  (sys.path shim above)

EXIT_PASS, EXIT_FAIL, EXIT_BLIND = 0, 1, 2

DEFAULT_URL = "https://lexitrail.com/"
PROGRESS_SELECTOR = ".progress-info"

#: `progressLabel` in ui/src/utils/session.js emits 'card N of T' or
#: 'cards N–M of T' (an EN DASH, U+2013, not a hyphen). Both carry ' of T',
#: which is the only part this needs.
_SESSION_LABEL_RE = re.compile(r"\bcards?\s+\d+(?:\s*[–-]\s*\d+)?\s+of\s+(\d+)\b")

#: Game.js's NON-session branch: 'recalled X out of Y'. Matching this is a real
#: finding -- it means the view rendered without a session binding at all.
_UNBOUNDED_LABEL_RE = re.compile(r"\brecalled\s+\d+\s+out\s+of\s+(\d+)\b")

_DEFAULT_GOAL_RE = re.compile(r"export\s+const\s+DEFAULT_GOAL\s*=\s*(\d+)")


def read_budget(repo_root: Path) -> int | None:
    """`DEFAULT_GOAL` from ui/src/utils/streak.js, or None (-> BLIND).

    None rather than a fallback default on purpose: a fallback would let a
    renamed constant read as a healthy budget, and the check would then be
    asserting against a number the product does not use.
    """
    src = repo_root / "ui" / "src" / "utils" / "streak.js"
    try:
        m = _DEFAULT_GOAL_RE.search(src.read_text(encoding="utf-8"))
    except OSError:
        return None
    return int(m.group(1)) if m else None


def classify(label: str, budget: int) -> tuple[int, str]:
    """(exit, reason) for one rendered `.progress-info` string. Pure."""
    if not label.strip():
        return EXIT_BLIND, "empty .progress-info -- nothing rendered to judge"
    m = _UNBOUNDED_LABEL_RE.search(label)
    if m:
        return EXIT_FAIL, (
            f"NOT bounded: label is Game.js's non-session branch "
            f"('recalled ... out of {m.group(1)}'), so no session was bound")
    m = _SESSION_LABEL_RE.search(label)
    if not m:
        return EXIT_BLIND, (
            f"unrecognised label {label!r} -- neither the session shape nor the "
            f"non-session shape; the instrument cannot judge it")
    total = int(m.group(1))
    if total > budget:
        return EXIT_FAIL, (
            f"session denominator {total} EXCEEDS the budget {budget} -- the "
            f"session is not bound to SESSION_BUDGET")
    return EXIT_PASS, f"bounded: denominator {total} <= budget {budget}"


def self_test() -> int:
    """Validate the parser. A PASS below is only worth something if these hold."""
    cases = [
        ("cards 1–10 of 10", 10, EXIT_PASS, "the live shape, multi-card"),
        ("card 4 of 10", 10, EXIT_PASS, "single-card layout"),
        ("cards 1-10 of 10", 10, EXIT_PASS, "ASCII hyphen tolerated"),
        ("cards 1–4 of 4", 10, EXIT_PASS, "CLEARED: fewer than budget is healthy"),
        # 🔴 The arm that matters: the #108 regression, on the biggest wordset.
        ("recalled 0 out of 2500", 10, EXIT_FAIL, "the unbounded non-session label"),
        ("cards 1–10 of 2500", 10, EXIT_FAIL, "session shape, wordset-sized denominator"),
        ("", 10, EXIT_BLIND, "empty -> BLIND, never PASS"),
        ("loading", 10, EXIT_BLIND, "unrecognised -> BLIND, never PASS"),
    ]
    rc = EXIT_PASS
    for label, budget, want, why in cases:
        got, reason = classify(label, budget)
        if got != want:
            print(f"SELF-TEST FAIL ({why}): {label!r} -> {got} ({reason}), wanted {want}",
                  file=sys.stderr)
            rc = EXIT_FAIL
    if rc == EXIT_PASS:
        print("session_bounded: SELF-TEST PASS (live shape; single-card; ascii-hyphen; "
              "cleared-under-budget; unbounded-label->FAIL; wordset-denominator->FAIL; "
              "empty->BLIND; unrecognised->BLIND)")
    return rc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--timeout-ms", type=int, default=60_000)
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    repo_root = Path(__file__).resolve().parent.parent
    budget = read_budget(repo_root)
    if budget is None:
        print("BLIND: could not read DEFAULT_GOAL from ui/src/utils/streak.js -- "
              "the budget this asserts against is unknown, so no verdict is possible",
              file=sys.stderr)
        return EXIT_BLIND

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        try:
            page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout_ms)
            enter_practice(page)
            page.wait_for_selector(PROGRESS_SELECTOR, timeout=args.timeout_ms)
            page.wait_for_timeout(2_000)
            label = page.inner_text(PROGRESS_SELECTOR).strip()
        except Exception as e:  # noqa: BLE001 -- any failure to reach it is BLIND
            print(f"BLIND: could not reach a practice card -- {type(e).__name__}: "
                  f"{str(e)[:200]}", file=sys.stderr)
            return EXIT_BLIND
        finally:
            browser.close()

    rc, reason = classify(label, budget)
    tag = {EXIT_PASS: "PASS", EXIT_FAIL: "FAIL", EXIT_BLIND: "BLIND"}[rc]
    stream = sys.stdout if rc == EXIT_PASS else sys.stderr
    print(f"{tag}: {PROGRESS_SELECTOR} = {label!r} -- {reason}", file=stream)
    return rc


if __name__ == "__main__":
    sys.exit(main())
