#!/usr/bin/env python3
"""Render the Today home (lexitrail#107) against stubbed data and screenshot it.

WHY THIS EXISTS
---------------
@ensemble-hc2 blocked PR #133 on "did anyone look at the rendered thing", and
was right to: lexitrail has no Cloud Build trigger (#77), so nothing deploys on
merge and there is no later stage that would catch a broken layout. The unit
tests cover `srs.js` and `useDueToday`; neither can tell you the number is
legible or the button is reachable.

Standing the real backend up for this is not proportionate (match-making
WebSocket + a dynamically discovered middle layer), so this serves the
production BUILD and stubs the two API calls the screen makes. What that does
and does not prove:

  PROVES:  the real bundle, real CSS, real component tree, real router, at a
           real viewport -- i.e. everything between `Today.js` and pixels.
  DOES NOT: that the live API returns this shape. The stubs are written to
           match `wordsService.getWordsets` and
           `userService.getUserWordsByWordset` as the code calls them, and are
           the same fixtures the unit tests use. A backend contract change
           would pass here and fail in production.

NETWORK IS FAIL-CLOSED
----------------------
Every request to the API origin is either fulfilled from a fixture or ABORTED,
and any abort of an unrecognised path is reported. A screenshot taken while
silently talking to the real api.lexitrail.com would be a different artifact
than the one it claims to be, and analytics/funnel pollution is the exact
hazard `docs/itp-playwright-usability.md` 2.3 names.

THREE-STATE OUTCOME, never two -- "I could not render" must not look like "it
rendered fine":

    0  OK     every requested shot captured
    1  FAIL   the page rendered but the expected content was absent
    2  BLIND  could not serve, could not navigate, or playwright is missing

Usage:
    python3 e2e/today_screenshots.py --build ui/build --out docs/review-artifacts/107
"""
import argparse
import functools
import http.server
import json
import os
import re
import socketserver
import sys
import threading

API_ORIGIN = "https://api.lexitrail.com"
USER = {"email": "screenshot@lexitrail.demo", "name": "Screenshot User"}

# lexitrail#249. Setting `user` alone stopped signing anyone in on 2026-08-28.
#
# BEFORE #200 (issue-185) `AuthContext` read `sessionStorage.getItem('user')` and
# nothing else, so a user object by itself WAS a session. #200 introduced
# `authStorage.loadSession`, whose guest branch is `guestUser && guestToken`, and
# #201 narrowed it again to `guestUser && isGuestToken(guestToken)` -- guest-shaped
# meaning the `UNAUTH_USER:` prefix. A token-less stub therefore falls through to
# the localStorage branch, finds nothing, and renders the signed-out marketing
# landing. `.today` never appears and every shot fails.
#
# 🔴 The failure looked exactly like a broken deploy. It is not: a build of current
# `main` and the bundle serving production fail IDENTICALLY, which is what said the
# instrument had gone stale rather than the product. Keep this comment -- the next
# person to see "`.today` never rendered" will reach for the deploy first.
GUEST_TOKEN = "UNAUTH_USER:screenshot"

DAY_MS = 24 * 60 * 60 * 1000

# ONE definition on purpose (lexitrail#249): the previous code repeated the seed
# at three call sites, so a change had to be made three times or the run would
# authenticate on some shots and not others -- which reads as a flaky render, not
# as a half-applied stub.
SEED_SESSION = """({user, token}) => {
    sessionStorage.setItem('user', JSON.stringify(user));
    sessionStorage.setItem('access_token', token);
}"""

# A userword row as `getUserWordsByWordset` returns it. `recall_state: 2` is a
# 1-day interval and the review is 30 days old, so `isWordDue` is true --
# matching the `uw()` factory in `useDueToday.test.js` rather than inventing a
# second idea of what a due row looks like.
def due_word(word_id):
    import datetime
    ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    return {
        "word_id": word_id,
        "is_included": True,
        "recall_state": 2,
        "recall_history": [{"original_recall_time": ago.isoformat()}],
    }


def rested_word(word_id):
    """Included, but reviewed today at state 0 -- a full week of rest left."""
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        "word_id": word_id,
        "is_included": True,
        "recall_state": 0,
        "recall_history": [{"original_recall_time": now.isoformat()}],
    }


WORDSETS = [
    {"wordset_id": 1, "description": "HSK 1"},
    {"wordset_id": 2, "description": "HSK 2"},
]

SCENARIOS = {
    # 12 due overall, 8 of them in HSK 2 -- so the screen has to show a total
    # that differs from the set Start opens, which is the honest-limitation
    # case worth LOOKING at rather than reasoning about.
    "due": {1: [due_word(i) for i in range(4)], 2: [due_word(100 + i) for i in range(8)]},
    # Nothing due: every word rested. Exercises the all-caught-up branch.
    "caught-up": {1: [rested_word(i) for i in range(4)], 2: [rested_word(100 + i) for i in range(8)]},
}

VIEWPORTS = {"desktop": (1440, 900), "mobile": (390, 844)}


# ─── issue-108 (RD-2) — the game route, so a SESSION can be driven ──────────
# The card view and the completion screen are the two surfaces RD-2 changes,
# and neither is reachable from the Today home alone. Shapes here come from the
# BACKEND serializers, not from what the consumer expects:
#   /wordsets/<id>/words -> {"data": [{word_id, wordset_id, word, def1, def2,
#                                      quiz_options: [[w, pinyin, def2] x3]}]}
#   /userwords/query     -> {"data": [{..., recall_histories: [{recall_time}]}]}
# Getting the second of those wrong is exactly what lexitrail#135 was.
def game_word(i):
    return {
        "word_id": i,
        "wordset_id": 1,
        "word": "记",
        "def1": f"jì {i}",
        "def2": f"to remember ({i})",
        "quiz_options": [["忆", "yì", "memory"],
                         ["书", "shū", "book"],
                         ["水", "shuǐ", "water"]],
    }


# Two sessions worth looking at:
#   short  3 due words  -> CLEARED  ("you finished everything available")
#   full  12 due words  -> COMPLETE ("all 10 cards done") with 2 left over,
#                          which is the case that proves the budget BOUNDS the
#                          queue rather than the queue bounding itself.
# 🔴 The GAME path needs the RAW backend shape, which is NOT the shape
# `due_word()` above produces, and the difference is a live bug rather than a
# harness quirk: `/userwords/query` returns `recall_histories[].recall_time`
# (see `backend/app/routes/userwords.py`), while `due_word()` above emits the
# MAPPED `recall_history[].original_recall_time` that `useWordsetLoader`
# produces downstream. `useWordsetLoader` calls `userWord.recall_histories.map`,
# so feeding it the mapped shape throws and the game renders "Error loading
# data" — which is how this got noticed here.
#
# The consumer-side half of the same confusion is lexitrail#135 (the Today home
# read the mapped shape off raw rows and counted every included word as due).
# Once #136 lands, `due_word()` should collapse into this one; both are kept
# separate until then so this harness is honest about which shape each surface
# is currently being fed.
def game_userword(i):
    import datetime
    ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    return {
        "user_id": USER["email"],
        "word_id": i,
        "is_included": True,
        "recall_state": 2,
        "recall_histories": [{"recall": True, "recall_time": ago.isoformat(),
                              "new_recall_state": 2, "old_recall_state": 3,
                              "is_included": True}],
    }


# issue-137: the HEIGHT is part of the scenario, not scenery. The card count a
# layout shows is what the session's terminal rule reads, and the two defects
# this harness measured were both invisible at one height and visible at
# another -- 390x844 gives 2 slots, 390x600 gives 1, and the 1-slot case is
# where the window rule degenerates to the front rule it replaced. Measured on
# the pre-fix build: 2 slots -> "All 10 cards done" but TWELVE taps; 1 slot ->
# "9 of 10 cards done". Running only the first height would have shown a green
# headline for a session that both overran its budget and lost a card.
GAME_SCENARIOS = {("short", 844): 3, ("full", 844): 12, ("full-1card", 600): 12}

# issue-144: the exclude/include control's STABLE accessible name. Kept as a
# constant because the harness and `WordCard.js` have to agree on it, and a
# string duplicated across two files with no test between them is how the
# runbook/parser pair in my-hermes#1462 nearly drifted.
EXCLUDE_CONTROL_LABEL = "Toggle whether this word is in your practice set"



class SPAHandler(http.server.SimpleHTTPRequestHandler):
    """Static server with SPA fallback -- unknown paths serve index.html."""

    def send_head(self):
        path = self.translate_path(self.path)
        if not os.path.exists(path) or os.path.isdir(path):
            self.path = "/index.html"
        return super().send_head()

    def log_message(self, *args):  # keep the harness output readable
        pass


def serve(build_dir):
    handler = functools.partial(SPAHandler, directory=build_dir)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def run_game(browser, base, out, unexpected, failures):
    """Drive a bounded session end to end and shoot both surfaces."""
    from playwright.sync_api import Error as PlaywrightError

    for (scenario, vp_h), n_due in GAME_SCENARIOS.items():
        words = [game_word(i) for i in range(1, n_due + 1)]
        userwords = [game_userword(i) for i in range(1, n_due + 1)]
        recall_writes = []
        ctx = browser.new_context(viewport={"width": 390, "height": vp_h})

        def route(r):
            url = r.request.url
            if "/words" in url and "/wordsets/" in url:
                return r.fulfill(status=200, content_type="application/json",
                                 body=json.dumps({"data": words}))
            if url.rstrip("/").endswith("/wordsets"):
                return r.fulfill(status=200, content_type="application/json",
                                 body=json.dumps({"data": WORDSETS}))
            if "/userwords/query" in url:
                return r.fulfill(status=200, content_type="application/json",
                                 body=json.dumps({"data": userwords}))
            # issue-137: the recall write is
            # `PUT /userwords/<user>/<word_id>/recall`, so the word it names is
            # in the URL. Recording it is what lets the drive loop below check
            # that the handler marked the word the LEARNER SAW -- a property
            # that used to hold for free (the visible set was a prefix, so slot
            # index == loader index) and now holds because the card carries
            # both indices deliberately.
            m_recall = re.search(r"/userwords/[^/]+/(\d+)/recall", url)
            if m_recall:
                recall_writes.append(int(m_recall.group(1)))
                return r.fulfill(status=200, content_type="application/json",
                                 body=json.dumps({"data": {}}))
            # Other /userwords + /users calls — accept and discard. The
            # session's progress is client-side, so a stubbed 200 is enough;
            # what matters is that nothing reaches the real API.
            if "/userwords" in url or "/users" in url:
                return r.fulfill(status=200, content_type="application/json",
                                 body=json.dumps({"data": {}}))
            unexpected.append(url)
            return r.abort()

        ctx.route(f"{API_ORIGIN}/**", route)
        ctx.route("**/*google-analytics*/**", lambda r: r.abort())
        ctx.route("**/*googletagmanager*/**", lambda r: r.abort())
        page = ctx.new_page()
        # gtag is called unguarded by Game.handleCardGuessed; without a stub the
        # first recall throws and the session cannot be driven at all.
        page.add_init_script("window.gtag = window.gtag || function () {};")
        # The first-run "How to play" dialog is modal and intercepts every
        # pointer event, so a fresh context cannot reach a card at all. Marking
        # the flag the component itself reads (`Game.js`: `showOnboarding`
        # initialises from `localStorage.lexitrail_onboarded`) reproduces a
        # RETURNING learner, which is who a habit screen is for. The overlay is
        # a real first-session surface and deserves its own shot, but not one
        # that hides the thing under test.
        page.add_init_script("try { localStorage.setItem('lexitrail_onboarded', '1'); } catch (e) {}")
        page.goto(base, wait_until="domcontentloaded")
        page.evaluate(SEED_SESSION, {"user": USER, "token": GUEST_TOKEN})
        page.goto(f"{base}/game/1/DUE_TODAY", wait_until="networkidle")

        try:
            page.wait_for_selector(".progress-info", timeout=15000)
        except PlaywrightError:
            failures.append(f"game/{scenario}: card view never rendered")
            ctx.close()
            continue

        # issue-144: the exclusion control must be reachable BY ITS ACCESSIBLE
        # NAME, not by a class. Presence only -- clicking it removes a word and
        # would perturb the session this scenario is measuring. Selecting by
        # name is the point: before #144 the control's only handle was its
        # visible text, which FLIPS with state ("Exclude"/"Include"), so a
        # driver had to know the word's state before it could find the button.
        # That is also how I came to report the exclusion path undrivable when
        # it was not -- I grepped WordCard.js for `aria-label`, got two hits,
        # and believed them.
        if not page.query_selector(f'[aria-label="{EXCLUDE_CONTROL_LABEL}"]'):
            failures.append(
                f"game/{scenario}: no control named {EXCLUDE_CONTROL_LABEL!r} "
                "-- the exclude button lost its aria-label (#144), so the only "
                "way to select it is the class or its state-dependent text")

        info = page.inner_text(".progress-info")
        expect_total = min(n_due, 10)
        if f"of {expect_total}" not in info:
            failures.append(f"game/{scenario}: progress reads {info!r}, expected 'of {expect_total}'")

        shot = os.path.join(out, f"session-{scenario}-card-mobile.png")
        page.screenshot(path=shot, full_page=True)
        print(f"captured {shot}  [{info}]")

        # Drive it: flip, mark memorized, repeat. Bounded by the BUDGET, not by
        # the queue — if the session failed to bound itself this loop would run
        # past `expect_total` and the assertion below catches it.
        taps, marked_wrong = 0, []
        for _ in range(expect_total + 4):
            if page.query_selector(".completed-session-title"):
                break
            try:
                page.click(".word-card-inner", timeout=4000)   # flip: def1 is on the back
                page.wait_for_timeout(200)
                shown = page.inner_text(".word-meaning-def1")
                before = len(recall_writes)
                page.click('[aria-label="Mark as memorized"]', timeout=4000)
                taps += 1
            except PlaywrightError:
                break
            page.wait_for_timeout(350)
            m_shown = re.search(r"(\d+)", shown)
            if m_shown and len(recall_writes) > before:
                want = int(m_shown.group(1))
                got = recall_writes[-1]
                if got != want:
                    marked_wrong.append((want, got))

        title_el = page.query_selector(".completed-session-title")
        if not title_el:
            failures.append(f"game/{scenario}: never reached a terminal state")
            ctx.close()
            continue

        title = title_el.inner_text()
        want = "Session complete" if n_due >= 10 else "All caught up"
        if want not in title:
            failures.append(f"game/{scenario}: terminal headline {title!r}, expected {want!r}")

        # issue-137: the headline alone said "Session complete" on a run that
        # had lost a card AND on one that had practised two past its budget, so
        # it is not the assertion. Both directions, because they fail
        # oppositely and only one of them is visible in the completion text:
        #
        #   taps <  expect_total  -> cards the learner was promised, dropped
        #                            (the completion screen SAYS "9 of 10")
        #   taps >  expect_total  -> cards outside the session, practised
        #                            (the completion screen still says "All 10
        #                            cards done" -- silent, and the reason a
        #                            headline check could never catch it)
        # issue-137: the handler must mark the word the learner was looking at.
        # 🔴 Checked to the END of the session on purpose. Early on, the slot
        # index and the loader index COINCIDE -- the loader has a session word
        # in front -- so a short drive reports clean even with the indices
        # deliberately crossed (measured: a 6-step probe missed it entirely,
        # a full-length one caught 2 per viewport). The divergence lives in the
        # same tail the original card-loss bug lived in.
        if marked_wrong:
            failures.append(
                f"game/{scenario}: {len(marked_wrong)} recall write(s) named a "
                f"word the learner was not looking at: "
                + ", ".join(f"showed {w}, wrote {g}" for w, g in marked_wrong))

        body = page.inner_text("body")
        if n_due >= 10:
            if taps != expect_total:
                failures.append(
                    f"game/{scenario}: {taps} card(s) practised for a "
                    f"{expect_total}-card session -- "
                    + ("session ran PAST its budget" if taps > expect_total
                       else "session finished SHORT"))
            if f"All {expect_total} cards done" not in body:
                failures.append(
                    f"game/{scenario}: completion text does not read "
                    f"'All {expect_total} cards done' -- got {body[:120]!r}")

        shot = os.path.join(out, f"session-{scenario}-done-mobile.png")
        page.screenshot(path=shot, full_page=True)
        print(f"captured {shot}  [{title}]")
        ctx.close()




def run_start_flow(browser, base, unexpected, failures):
    """The one thing screenshots cannot show: that Start actually STARTS it.

    issue-107's AC asks for a green Playwright E2E. The screenshot pass proves
    each screen RENDERS; it says nothing about the transition between them, and
    the transition is where the contract lives — Start has to open a session on
    the wordset the home names, in DUE_TODAY mode, with the count it promised.

    Asserts, in the learner's order:
      1. the Today home names a due count and a target set
      2. clicking Start navigates to /game/<that wordset>/DUE_TODAY
      3. the session that opens is bounded, and its size matches what Today
         said was in that set

    (3) is the load-bearing one. A home that says "8 of them in HSK 2" and then
    opens a 4-card session is two features that each work and a product that
    lies, which is exactly the disagreement `totalDue` deriving from
    `dueByWordset` exists to prevent — and nothing until now tested it ACROSS
    the two screens.
    """
    from playwright.sync_api import Error as PlaywrightError

    # Two sets, so Start has to CHOOSE: 3 due in set 1, 8 due in set 2.
    # pickStartSet must open set 2, and a bug that opens "the first set" or
    # "the whole list" fails visibly rather than plausibly.
    words_by_set = {1: [game_word(i) for i in range(1, 4)],
                    2: [game_word(i) for i in range(101, 109)]}
    uw_by_set = {1: [game_userword(i) for i in range(1, 4)],
                 2: [game_userword(i) for i in range(101, 109)]}

    ctx = browser.new_context(viewport={"width": 390, "height": 844})

    def route(r):
        url = r.request.url
        if "/words" in url and "/wordsets/" in url:
            wid = int(url.split("/wordsets/")[1].split("/")[0])
            return r.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"data": words_by_set.get(wid, [])}))
        if url.rstrip("/").endswith("/wordsets"):
            return r.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"data": WORDSETS}))
        if "/userwords/query" in url:
            wid = int(url.split("wordset_id=")[1].split("&")[0])
            return r.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"data": uw_by_set.get(wid, [])}))
        if "/userwords" in url or "/users" in url:
            return r.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"data": {}}))
        unexpected.append(url)
        return r.abort()

    ctx.route(f"{API_ORIGIN}/**", route)
    ctx.route("**/*google-analytics*/**", lambda r: r.abort())
    ctx.route("**/*googletagmanager*/**", lambda r: r.abort())

    page = ctx.new_page()
    page.add_init_script("window.gtag = window.gtag || function () {};")
    page.add_init_script("try { localStorage.setItem('lexitrail_onboarded', '1'); } catch (e) {}")
    page.goto(base, wait_until="domcontentloaded")
    page.evaluate(SEED_SESSION, {"user": USER, "token": GUEST_TOKEN})
    page.goto(base, wait_until="networkidle")

    try:
        page.wait_for_selector(".today-headline", timeout=15000)
    except PlaywrightError:
        failures.append("start-flow: Today home never rendered")
        ctx.close()
        return

    home_text = page.inner_text(".today")
    if "11" not in home_text:
        failures.append(f"start-flow: home should total 11 due (3+8), got {home_text!r}")
    if "HSK 2" not in home_text:
        failures.append(f"start-flow: home should name HSK 2 as the target, got {home_text!r}")

    try:
        page.click(".today-start", timeout=8000)
        page.wait_for_url("**/game/**", timeout=10000)
    except PlaywrightError:
        failures.append("start-flow: Start did not navigate")
        ctx.close()
        return

    # The set Today NAMED, and the mode that means "today's due", not the whole
    # wordset. A Start that opened /game/1/PRACTICE would still "work".
    if "/game/2/DUE_TODAY" not in page.url:
        failures.append(f"start-flow: expected /game/2/DUE_TODAY, landed on {page.url}")

    try:
        page.wait_for_selector(".progress-info", timeout=15000)
    except PlaywrightError:
        failures.append("start-flow: session never rendered after Start")
        ctx.close()
        return

    info = page.inner_text(".progress-info")
    # 8 due in that set, under a 10-card budget -> an 8-card session. If the
    # home and the session disagreed, this is where it would show.
    if "of 8" not in info:
        failures.append(f"start-flow: session should hold the 8 the home promised, reads {info!r}")

    if not failures:
        print("start-flow OK: home 11 due -> Start -> /game/2/DUE_TODAY -> "
              f"session {info!r}")
    ctx.close()



def self_test(build, base_factory):
    """Does the session stub DISCRIMINATE, or would anything render Today? (#249)

    The bug this file just recovered from was a stub that silently stopped
    authenticating. The obvious fix -- seed a token until the shots come back --
    is satisfied equally by a stub that authenticates EVERYTHING, and that
    version would render Today for a visitor who should see the marketing page.
    So the positive arm alone cannot tell a working stub from a broken gate.

    Two arms, one build, one instant:
        guest-shaped token (UNAUTH_USER:)  -> .today MUST render
        member-shaped token (ya29.*)       -> .today MUST NOT render

    The second arm is the load-bearing one. `loadSession`'s guest branch is
    `guestUser && isGuestToken(guestToken)`, and a `ya29.` token in
    sessionStorage is exactly the pre-#185 member session #201 exists to refuse.

    0 OK   1 FAIL (an arm came out the wrong way)   2 BLIND (could not run)
    """
    from playwright.sync_api import sync_playwright
    httpd, port = serve(build)
    base = f"http://127.0.0.1:{port}"
    arms = {"guest": (GUEST_TOKEN, True), "member-shaped": ("ya29.not-a-guest-token", False)}
    bad = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for name, (token, want_today) in arms.items():
                ctx = browser.new_context(viewport={"width": 1280, "height": 900})
                # Fail closed, same as the main run: nothing leaves this machine.
                ctx.route("**/*", lambda r: (r.continue_() if r.request.url.startswith(base)
                                             else r.abort()))
                page = ctx.new_page()
                page.goto(base, wait_until="domcontentloaded")
                page.evaluate(SEED_SESSION, {"user": USER, "token": token})
                page.add_init_script(
                    "try { localStorage.setItem('lexitrail_onboarded', '1'); } catch (e) {}")
                page.goto(base, wait_until="domcontentloaded")
                page.wait_for_timeout(1200)
                got_today = page.locator(".today").count() > 0
                verdict = "OK" if got_today == want_today else "WRONG"
                print(f"  self-test {name:14} .today={got_today}  want={want_today}  {verdict}")
                if got_today != want_today:
                    bad.append(name)
                ctx.close()
            browser.close()
    except Exception as exc:                                  # noqa: BLE001
        print(f"BLIND: self-test could not run: {exc}", file=sys.stderr)
        return 2
    finally:
        httpd.shutdown()
    if bad:
        print(f"FAIL: the stub does not discriminate -- wrong arm(s): {bad}", file=sys.stderr)
        return 1
    print("self-test OK: guest token renders Today, member-shaped token does not")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="ui/build")
    ap.add_argument("--out", default="docs/review-artifacts/107")
    ap.add_argument("--self-test", action="store_true",
                    help="prove the session stub discriminates, then exit (#249)")
    args = ap.parse_args()

    if not os.path.isfile(os.path.join(args.build, "index.html")):
        print(f"BLIND: no build at {args.build} -- run `react-scripts build` first",
              file=sys.stderr)
        return 2
    try:
        from playwright.sync_api import sync_playwright, Error as PlaywrightError
    except ImportError:
        print("BLIND: playwright for Python is not installed", file=sys.stderr)
        return 2

    if args.self_test:
        return self_test(args.build, None)

    os.makedirs(args.out, exist_ok=True)
    httpd, port = serve(args.build)
    base = f"http://127.0.0.1:{port}"
    unexpected, failures = [], []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for scenario, words in SCENARIOS.items():
                for vp_name, (w, h) in VIEWPORTS.items():
                    ctx = browser.new_context(viewport={"width": w, "height": h})

                    def route(r):
                        url = r.request.url
                        # NB `/wordsets` itself contains the substring
                        # `/words` -- the first version of this predicate used
                        # `"/words" not in url` and aborted every wordsets
                        # call. The fail-closed report below is what surfaced
                        # it; a permissive default would have screenshotted an
                        # error state and called it a pass.
                        if url.rstrip("/").endswith("/wordsets"):
                            # The wire body is `{"data": [...]}`: `getData`
                            # returns `response.data` (the JSON body) and
                            # `getWordsets` then reads `.data` off THAT. A bare
                            # array renders the error state -- which this
                            # harness correctly refused to screenshot as a pass.
                            return r.fulfill(status=200, content_type="application/json",
                                             body=json.dumps({"data": WORDSETS}))
                        if url.startswith(f"{API_ORIGIN}/userwords/query"):
                            wid = int(url.split("wordset_id=")[1].split("&")[0])
                            return r.fulfill(status=200, content_type="application/json",
                                             body=json.dumps({"data": words.get(wid, [])}))
                        # Fail closed: anything else is aborted AND reported, so
                        # a silent real-API call cannot hide inside a green run.
                        unexpected.append(url)
                        return r.abort()

                    ctx.route(f"{API_ORIGIN}/**", route)
                    # Analytics never leaves the machine (itp-playwright 2.3).
                    ctx.route("**/*google-analytics*/**", lambda r: r.abort())
                    ctx.route("**/*googletagmanager*/**", lambda r: r.abort())

                    page = ctx.new_page()
                    page.goto(base, wait_until="domcontentloaded")
                    # Sign in the way AuthContext reads it, then reload so the
                    # provider initialises from storage.
                    page.evaluate(SEED_SESSION, {"user": USER, "token": GUEST_TOKEN})
                    page.goto(base, wait_until="networkidle")

                    try:
                        page.wait_for_selector(".today", timeout=10000)
                        # The count/all-caught-up text only appears once the
                        # fan-out resolves; without this the shot can catch the
                        # loading state and look like a broken screen.
                        # Either resolved state -- but NOT the loading state.
                        # An error renders `.today-error`, which the content
                        # assertion below then fails on, so a broken fetch
                        # cannot be screenshotted as a working screen.
                        page.wait_for_selector(".today-headline, .today-error", timeout=10000)
                    except PlaywrightError:
                        failures.append(f"{scenario}/{vp_name}: .today never rendered")
                        ctx.close()
                        continue

                    text = page.inner_text(".today")
                    want = "All caught up" if scenario == "caught-up" else "reviews due today"
                    if want not in text:
                        failures.append(f"{scenario}/{vp_name}: expected {want!r}, got {text!r}")

                    path = os.path.join(args.out, f"today-{scenario}-{vp_name}.png")
                    page.screenshot(path=path, full_page=True)
                    print(f"captured {path}")
                    ctx.close()
            run_game(browser, base, args.out, unexpected, failures)
            run_start_flow(browser, base, unexpected, failures)
            browser.close()
    finally:
        httpd.shutdown()

    if unexpected:
        print(f"FAIL: {len(unexpected)} request(s) to unstubbed API paths: "
              f"{sorted(set(unexpected))[:5]}", file=sys.stderr)
        return 1
    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1
    print("OK: all screenshots captured, no unstubbed requests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
