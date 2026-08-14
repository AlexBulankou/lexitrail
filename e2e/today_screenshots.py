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
import socketserver
import sys
import threading

API_ORIGIN = "https://api.lexitrail.com"
USER = {"email": "screenshot@lexitrail.demo", "name": "Screenshot User"}

DAY_MS = 24 * 60 * 60 * 1000

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="ui/build")
    ap.add_argument("--out", default="docs/review-artifacts/107")
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
                    page.evaluate("u => sessionStorage.setItem('user', JSON.stringify(u))", USER)
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
