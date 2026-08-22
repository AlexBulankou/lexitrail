"""Lexitrail journey routes for the tap-target harness (lexitrail#85).

Split out of `tap_targets.py` per lexitrail#163's seam: routes are the part that
GROWS -- each journey adds an entry callable, a URL marker and a fixture -- so
they get their own file rather than eating the harness's headroom. `lt_measure`
holds the pure measurement half; this holds everything that knows what Lexitrail
looks like.

The self-test FIXTURES live here too, with the code they exercise, so a future
extraction cannot separate an assertion from the page that makes it fail.

⚠️ Dependencies were derived by AST rather than by reading: the #163 extraction
broke because `PlaywrightError` was caught here and imported only in the origin
module, and an import does not cross a module boundary. The free names this file
needs are exactly `re`, `PlaywrightError` and `INTERACTIVE_SELECTOR`, and all
three are imported below.
"""
from __future__ import annotations

import re

from playwright.sync_api import Error as PlaywrightError

from lt_measure import INTERACTIVE_SELECTOR

# --------------------------------------------------------------------------
# Routes (#85). The landing page is only the PUBLIC surface; every journey
# behind the guest session was unmeasured, and the same enumerated selector
# list governs those screens too.
#
# 🔴 The guest path is entered by TEXT, and the live label is `Try` -- NOT
# "Try without signing in", which is what #85's AC1 and
# docs/itp-playwright-usability.md 2.2 both say. Measured on live prod
# 2026-08-11: a selector on the documented string matches nothing.
#
# 🔴 Entry is asserted on the DOM, never on the URL or a control COUNT:
#   * the app is an SPA -- the URL is IDENTICAL before and after entry, so a
#     page.url assertion reads as not-reached on success, which under AC4
#     would be a PERMANENT false BLIND;
#   * the count was 33 BEFORE and 33 AFTER a click that genuinely changed
#     state, so a count comparison cannot see the transition either.
# What does change: `Sign in` / `Try` disappear and `Word Sets` appears. We
# assert `Sign in` is GONE, which fails loudly if the click silently no-ops.
# --------------------------------------------------------------------------
# ⚠️ SCOPE (#85): the "never assert on the URL" rule above is about GUEST entry
# specifically, where the URL genuinely does not move. `enter_practice` below
# asserts on page.url and must -- it navigates to /game/, which the landing page
# cannot reach. Reading this as a blanket rule is what left the guest route
# measuring the homepage for six cells.
GUEST_ENTRY_RE = re.compile(r"^\s*Try\s*$", re.I)
SIGNED_OUT_MARKER = "Sign in"


def _visible_texts(page) -> list[str]:
    return page.eval_on_selector_all(
        INTERACTIVE_SELECTOR,
        "els => els.filter(e => e.getBoundingClientRect().width > 0)"
        ".map(e => (e.innerText || e.getAttribute('aria-label') || '').trim())")


def enter_guest(page) -> None:
    """Click into the guest session. Raises RuntimeError if the state did not move.

    Raising is the point: the caller turns it into BLIND. A route we could not
    enter must never be reported as a clean measurement of that route -- that
    is the reassuring-direction failure AC4 exists to prevent.
    """
    before = _visible_texts(page)
    if SIGNED_OUT_MARKER not in before:
        raise RuntimeError(
            f"no {SIGNED_OUT_MARKER!r} control on the landing page -- either the "
            "app is already signed in or the entry surface moved; refusing to "
            "guess which")
    try:
        page.get_by_text(GUEST_ENTRY_RE).first.click(timeout=10_000)
    except PlaywrightError as e:
        raise RuntimeError(f"guest entry click failed: {e}") from e
    page.wait_for_timeout(4_000)
    after = _visible_texts(page)
    if SIGNED_OUT_MARKER in after:
        raise RuntimeError(
            f"clicked guest entry but {SIGNED_OUT_MARKER!r} is still present -- "
            "the click did not change state")


WORDSETS_URL_MARKER = "/wordsets"
PRACTICE_URL_MARKER = "/game/"


def enter_wordsets(page) -> None:
    """Guest, then the wordset list. Raises -> BLIND.

    issue-85 names this surface explicitly and nothing had ever measured it:
    `enter_practice` passes THROUGH it without stopping, so a green practice
    cell says nothing about the list itself.

    ⚠️ Deliberately does NOT share a step with `enter_practice`, and the four
    duplicated lines are the price of a real control. If `enter_practice`
    called this, its own URL assertion would no longer be independently
    testable -- neutering the /game/ assert would still raise HERE, so the
    self-test arm for it would go green with the assertion gone. A DRY-er
    version of these two functions is a weaker instrument, which is the same
    trade this file already makes for `landing` vs `guest`.
    """
    enter_guest(page)
    try:
        page.get_by_role("link", name="Word Sets").first.click(timeout=10_000)
        page.wait_for_timeout(4_000)
    except PlaywrightError as e:
        raise RuntimeError(f"could not reach the wordset list: {e}") from e
    if WORDSETS_URL_MARKER not in page.url:
        raise RuntimeError(
            f"clicked the Word Sets link but the URL is {page.url!r}, carrying "
            f"no {WORDSETS_URL_MARKER!r} -- still on the page we started from")


def enter_practice(page) -> None:
    """Guest, then navigate to the practice card view. Raises -> BLIND.

    issue-85: `enter_guest` alone authenticates IN PLACE and never leaves the
    landing page, so `guest` measured the homepage and reported it as a second
    route. The tell was `landing` and `guest` returning an IDENTICAL control
    count in all six cells; nothing failed.

    The assertion is on NAVIGATION, not session state: a state-moved check is
    satisfied by authenticating without going anywhere, which makes BLIND
    unreachable by construction, and a verdict that cannot be reached is not a
    verdict. Clicks the in-app links, not page.goto(): a hard nav DOES preserve
    the session (measured), but skips the nav -- #120 found a defect in it.
    """
    enter_guest(page)
    try:
        page.get_by_role("link", name="Word Sets").first.click(timeout=10_000)
        page.wait_for_timeout(4_000)
        page.get_by_text("Practice", exact=True).first.click(timeout=10_000)
        page.wait_for_timeout(8_000)
    except PlaywrightError as e:
        raise RuntimeError(f"could not reach the practice view: {e}") from e
    if PRACTICE_URL_MARKER not in page.url:
        raise RuntimeError(
            f"clicked through to practice but the URL is {page.url!r}, carrying "
            f"no {PRACTICE_URL_MARKER!r} -- still on the page we started from, "
            "which is the #85 failure itself")


#: name -> entry callable (None = measure the page as landed)
ROUTES: dict[str, object] = {"landing": None, "guest": enter_guest,
                             "wordsets": enter_wordsets,
                             "practice": enter_practice}


_GUEST_FIXTURE_MOVES = """data:text/html,
<html><body style="margin:0">
  <button onclick="document.getElementById('so').remove()">Try</button>
  <span id="so"><button>Sign in</button></span>
</body></html>"""

_GUEST_FIXTURE_STUCK = """data:text/html,
<html><body style="margin:0">
  <button>Try</button>
  <button>Sign in</button>
</body></html>"""

_PRACTICE_FIXTURE_NO_NAV = """data:text/html,
<html><body style="margin:0">
  <button onclick="document.getElementById('so').remove()">Try</button>
  <span id="so"><button>Sign in</button></span>
  <a href="javascript:void(0)">Word Sets</a><button>Practice</button>
</body></html>"""
