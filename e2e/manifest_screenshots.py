#!/usr/bin/env python3
"""Capture the two PWA manifest screenshots (lexitrail#75) from the real app.

WHY THIS EXISTS
---------------
`manifest.json`'s `screenshots[]` (shown in the Chrome/Android install prompt)
and the schema.org block both served a raw capture of a live demo session —
`Demo User` / `4usvy@lexitrail.demo` in the NavBar, a `recalled 0 out of 149`
counter, a running timer (lexitrail#75). The schema.org half was fixed in
#171 by repointing at the marketing OG asset; that fix is deliberately wrong
for `manifest.json` — AC2 rules it out explicitly, because a PWA install
prompt is supposed to show the *app*, not a social card. This produces a
genuine, clean, in-app capture instead, reusing `today_screenshots.py`'s
serve/stub machinery (issue-108 already proved a session can be driven
end-to-end against stubs; #75's own AC3 asks for exactly that path).

THE IDENTITY PROBLEM AND WHY MOBILE VIEWPORT SOLVES IT STRUCTURALLY
--------------------------------------------------------------------
Every signed-in route shows *some* identity in the NavBar — there is no
guest/anonymous state that reaches `/wordsets` or `/game`. Picking a
"nicer-sounding" fixture email would still be choosing a fake identity to
publish, which is the same class of problem in a different costume.

`NavBar.css`'s `@media (max-width: 480px)` rule hides `.user-info-compact`
(the name+email chip) entirely — added for issue-52's overflow fix, not for
privacy, but the effect is exact: at the mobile viewport (390px, matching
`today_screenshots.py`'s `VIEWPORTS["mobile"]`) NO name or email text renders
at all. Only the avatar `<img>` remains, pointed here at the app's own
`logo192.png` so it doesn't render as a broken-image icon. This is why both
captures use the mobile viewport rather than desktop — it isn't a stylistic
choice, it's what makes AC1 true by construction instead of by convention.

A text-scan (`assert_clean`, mirroring `tools/og/forbidden.mjs`'s two
identity patterns) still runs on the rendered body before each screenshot is
kept, fail-closed, as a second line of defence against someone reverting the
fixture to a `*.demo` address later. It deliberately does NOT reuse
forbidden.mjs's full pattern list: "recall counter" (`\\d+ of \\d+`) and
"exclude affordance" are real, expected UI on these screens (a session's
progress readout, the wordset picker's "Show Excluded" button) — flagging
them here would be a category error, not a safety net.

THREE-STATE OUTCOME, same convention as today_screenshots.py:
    0  OK     both screenshots captured, text-scan clean
    1  FAIL   rendered, but expected content (or a forbidden pattern) present
    2  BLIND  could not serve, could not navigate, or playwright is missing

Usage:
    cd ui && CI=true npx react-scripts build && cd ..
    python3 e2e/manifest_screenshots.py \\
        --build ui/build --out ui/public/images/screenshots
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import today_screenshots as ts  # noqa: E402  (serve/SPAHandler/API_ORIGIN reuse)

# Deliberately NOT a "*.demo" address and NOT "Demo User" — the two literal
# strings `assert_clean` refuses below. "Lexitrail" avoids reading as any
# individual's account, real or fake.
MANIFEST_USER = {"email": "hello@lexitrail.app", "name": "Lexitrail"}

VIEWPORT = {"width": 390, "height": 844}  # mobile — see module docstring

# `today_screenshots.py`'s `game_word()` returns the same character ("记")
# for every word_id — fine for a test fixture nobody looks at, but two
# identical cards side by side in a *published* screenshot reads as a bug,
# not a demo-account leak, but still not "a genuine app capture" (AC2). A
# handful of real, distinct HSK1-ish words instead.
PRACTICE_WORDS = [
    ("你好", "nǐ hǎo", "hello"),
    ("谢谢", "xiè xiè", "thank you"),
    ("学习", "xué xí", "to study"),
    ("朋友", "péng yǒu", "friend"),
    ("水", "shuǐ", "water"),
    ("书", "shū", "book"),
]

FORBIDDEN = [
    ("demo-account address", re.compile(r"\S*@lexitrail\.demo\b", re.I)),
    ("demo user label", re.compile(r"\bdemo\s+user\b", re.I)),
    # AC1 names this explicitly. `innerText` excludes `visibility: hidden`
    # elements, so with the Timer hidden below this is a defense-in-depth
    # check, not the primary one — it still catches a regression if the
    # hide ever stops applying before the screenshot is taken.
    ("session timer", re.compile(r"\b\d{1,2}:\d{2}\b")),
]


def assert_clean(text, where):
    hits = [(label, m.group(0)) for label, pat in FORBIDDEN if (m := pat.search(text))]
    if hits:
        detail = "; ".join(f"{label}: {matched!r}" for label, matched in hits)
        raise RuntimeError(f"{where}: capture-environment artifact(s) found — {detail}")


def _stub_wordsets_route(ctx, unexpected):
    def route(r):
        url = r.request.url
        if url.rstrip("/").endswith("/wordsets"):
            return r.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"data": ts.WORDSETS}))
        unexpected.append(url)
        return r.abort()
    ctx.route(f"{ts.API_ORIGIN}/**", route)
    ctx.route("**/*google-analytics*/**", lambda r: r.abort())
    ctx.route("**/*googletagmanager*/**", lambda r: r.abort())


def capture_wordsets(browser, base, out, unexpected, failures):
    """The wordset picker (`/wordsets`) — replaces `wordsets.png`."""
    ctx = browser.new_context(viewport=VIEWPORT)
    _stub_wordsets_route(ctx, unexpected)
    page = ctx.new_page()
    page.add_init_script("window.gtag = window.gtag || function () {};")
    page.goto(base, wait_until="domcontentloaded")
    page.evaluate(
        "u => sessionStorage.setItem('user', JSON.stringify(u))",
        {**MANIFEST_USER, "picture": f"{base}/logo192.png"},
    )
    page.goto(f"{base}/wordsets", wait_until="networkidle")

    from playwright.sync_api import Error as PlaywrightError
    try:
        page.wait_for_selector(".wordsets-grid, .wordsets-status", timeout=15000)
    except PlaywrightError:
        failures.append("wordsets: page never rendered")
        ctx.close()
        return

    if not page.query_selector(".wordset-tile"):
        failures.append("wordsets: no .wordset-tile rendered — stub route mismatch?")
        ctx.close()
        return

    body = page.inner_text("body")
    try:
        assert_clean(body, "wordsets")
    except RuntimeError as e:
        failures.append(str(e))
        ctx.close()
        return

    path = os.path.join(out, "wordsets.png")
    page.screenshot(path=path)
    print(f"captured {path}")
    ctx.close()


def capture_practice(browser, base, out, unexpected, failures):
    """A live PRACTICE session, a few cards in — replaces `hsk2-practice.png`.

    Mid-session, not completed: the ORIGINAL leak's `recalled 0 out of 149`
    was embarrassing because it was zero. A `.progress-info` reading e.g.
    "3 of 10" is real, honest session-progress UI (`today_screenshots.py`'s
    own game captures show the same text) — the fix is a non-zero count, not
    the absence of a counter.
    """
    from playwright.sync_api import Error as PlaywrightError

    wordset_id = 2  # HSK2 — matches the replaced file's name
    n_words = len(PRACTICE_WORDS)

    def word_for(i, word, pinyin, gloss):
        return {
            "word_id": i, "wordset_id": wordset_id, "word": word,
            "def1": pinyin, "def2": gloss,
            "quiz_options": [[w2, p2, g2] for w2, p2, g2 in PRACTICE_WORDS if w2 != word][:3],
        }

    words = [word_for(i, *w) for i, w in enumerate(PRACTICE_WORDS, start=1)]
    userwords = [ts.game_userword(i) for i in range(1, n_words + 1)]

    ctx = browser.new_context(viewport=VIEWPORT)

    def route(r):
        url = r.request.url
        if "/words" in url and "/wordsets/" in url:
            return r.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"data": words}))
        if url.rstrip("/").endswith("/wordsets"):
            return r.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"data": ts.WORDSETS}))
        if "/userwords/query" in url:
            return r.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"data": userwords}))
        if "/userwords" in url or "/users" in url:
            return r.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"data": {}}))
        unexpected.append(url)
        return r.abort()

    ctx.route(f"{ts.API_ORIGIN}/**", route)
    ctx.route("**/*google-analytics*/**", lambda r: r.abort())
    ctx.route("**/*googletagmanager*/**", lambda r: r.abort())

    page = ctx.new_page()
    page.add_init_script("window.gtag = window.gtag || function () {};")
    # Skip the modal onboarding overlay — see today_screenshots.py's identical
    # comment on run_game for why this is a returning-learner capture.
    page.add_init_script(
        "try { localStorage.setItem('lexitrail_onboarded', '1'); } catch (e) {}"
    )
    page.goto(base, wait_until="domcontentloaded")
    page.evaluate(
        "u => sessionStorage.setItem('user', JSON.stringify(u))",
        {**MANIFEST_USER, "picture": f"{base}/logo192.png"},
    )
    page.goto(f"{base}/game/{wordset_id}/PRACTICE", wait_until="networkidle")

    try:
        page.wait_for_selector(".progress-info", timeout=15000)
    except PlaywrightError:
        failures.append("practice: card view never rendered")
        ctx.close()
        return

    # AC1 names "no session timer" explicitly (the original leak was mid-
    # session at "0:17"), and a session cannot be driven without a timer
    # starting — Game.js mounts <Timer> unconditionally. Hiding it is a
    # capture-tool-only concern: it changes nothing a real user sees, the
    # same category as the onboarding-flag / sessionStorage injection above.
    page.add_style_tag(content=".timer { visibility: hidden; }")

    # Flip + mark memorized a few cards, same mechanics as
    # today_screenshots.py's run_game — but stop mid-session on purpose.
    flipped = 0
    for _ in range(3):
        try:
            page.click(".word-card-inner", timeout=4000)
            page.wait_for_timeout(200)
            page.click('[aria-label="Mark as memorized"]', timeout=4000)
            flipped += 1
        except PlaywrightError:
            break
        page.wait_for_timeout(350)

    if flipped == 0:
        failures.append("practice: could not drive a single card — "
                         "capture would still show a zero counter")
        ctx.close()
        return

    info = page.inner_text(".progress-info")
    m = re.search(r"(\d+)", info)
    if not m or int(m.group(1)) == 0:
        failures.append(f"practice: progress reads {info!r} — expected a "
                         "non-zero count after driving cards")
        ctx.close()
        return

    body = page.inner_text("body")
    try:
        assert_clean(body, "practice")
    except RuntimeError as e:
        failures.append(str(e))
        ctx.close()
        return

    path = os.path.join(out, "hsk2-practice.png")
    page.screenshot(path=path)
    print(f"captured {path}  [{info}]")
    ctx.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="ui/build")
    ap.add_argument("--out", default="ui/public/images/screenshots")
    args = ap.parse_args()

    if not os.path.isfile(os.path.join(args.build, "index.html")):
        print(f"BLIND: no build at {args.build} -- run `react-scripts build` first",
              file=sys.stderr)
        return 2
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("BLIND: playwright for Python is not installed", file=sys.stderr)
        return 2

    os.makedirs(args.out, exist_ok=True)
    httpd, port = ts.serve(args.build)
    base = f"http://127.0.0.1:{port}"
    unexpected, failures = [], []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            capture_wordsets(browser, base, args.out, unexpected, failures)
            capture_practice(browser, base, args.out, unexpected, failures)
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
    print("OK: both manifest screenshots captured, text-scan clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
