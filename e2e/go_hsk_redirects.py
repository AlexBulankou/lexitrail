#!/usr/bin/env python3
"""/go/* + /hskN prod-serving check -- lexitrail#51.

WHY THIS EXISTS
---------------
#51's original P0 (2026-07-23) claimed every bio-link click 404s in prod
because `serve.json`'s redirects are honored only by the `serve` npm package,
and LT prod might be served by something that ignores it. The issue's own
title later flagged that premise as disproven -- but disproven-by-someone's-
curl-once is not the same as PINNED, and #343 (the /hskN directory-listing
fix) changed the same config file these checks depend on. This is the
regression test that keeps it disproven.

WHAT IT CHECKS
--------------
Server-level behavior only -- HTTP status + Location header + response body
title. No browser: `/go/*` and `/hskN` are `serve.json` `redirects`/config
entries, resolved before any React code runs, so a Playwright page load would
just be a slower way to make the same HTTP request.

  1. Every `/go/*` bio-link source in `ui/public/serve.json["redirects"]`
     resolves 302 to its configured destination in prod -- not a 404, and not
     a directory listing (the #342/#343 failure shape: 200 with
     `<title>Files within ...</title>`).
  2. Every `/hsk1`..`/hsk6` resolves 301 to its own `/hskN.html`, and that
     page is a real lander (200, title contains "HSK"), not a directory
     listing.

THIS IS A DETECTOR, SO IT HAS CONTROLS
---------------------------------------
`--self-test` drives the pure checker functions against synthetic
(status, headers, body) tuples -- a genuine redirect, a 404, and the
directory-listing shape from #342 -- and asserts each is classified
correctly, without touching the network. Fixing a future regression does not
expire this control; only changing the checker logic can.

Outcomes are THREE-state, same convention as `redundant_fetches.py`:

    0  PASS   every configured route resolves as configured
    1  FAIL   at least one route 404s, or serves a directory listing, or
               redirects somewhere unconfigured
    2  BLIND  could not reach the server at all (network/DNS failure) --
               must never render as PASS; a check that can't reach prod has
               said nothing about prod
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

URL_DEFAULT = "https://lexitrail.com"
SERVE_JSON = Path(__file__).resolve().parent.parent / "ui" / "public" / "serve.json"

DIR_LISTING_RE = re.compile(r"<title>Files within ", re.I)
HSK_LANDER_RE = re.compile(r"<title>HSK \d", re.I)

EXIT_PASS, EXIT_FAIL, EXIT_BLIND = 0, 1, 2


class Probe:
    """One HTTP response, reduced to the fields the checkers need."""

    def __init__(self, status: int, location: str | None, body: str):
        self.status = status
        self.location = location
        self.body = body


class _NoRedirect(HTTPRedirectHandler):
    """`urlopen`'s default opener FOLLOWS 301/302 silently -- verified against
    real prod (2026-09-03): a plain `urlopen('/hsk1')` returns status 200 for
    `/hsk1.html`, with the intermediate redirect and its Location header gone
    entirely. A checker built on that default would report every redirect as
    "200, no Location" and could never distinguish a working 301 from a
    directory listing (also 200) -- the exact #342 failure shape this file
    exists to catch. Returning None here tells urllib to stop at the first
    hop instead of chasing it.
    """

    def redirect_request(self, *args, **kwargs):
        return None


_opener = build_opener(_NoRedirect)


def fetch(base_url: str, path: str) -> Probe:
    req = Request(f"{base_url}{path}", headers={"User-Agent": "lt-e2e-go-hsk/1"})
    try:
        with _opener.open(req, timeout=10) as resp:  # noqa: S310 -- fixed https base
            return Probe(resp.status, resp.headers.get("Location"), resp.read().decode("utf-8", "replace"))
    except Exception as e:  # urllib raises HTTPError (has .code) for 3xx/4xx alike here
        code = getattr(e, "code", None)
        if code is None:
            raise
        location = e.headers.get("Location") if hasattr(e, "headers") and e.headers else None
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")  # type: ignore[attr-defined]
        except Exception:
            pass
        return Probe(code, location, body)


def check_go_redirect(probe: Probe, expect_destination: str) -> tuple[bool, str]:
    """A /go/* source must 302 to its configured destination, never 404/200/listing."""
    if DIR_LISTING_RE.search(probe.body):
        return False, f"served a DIRECTORY LISTING instead of redirecting (status={probe.status})"
    if probe.status != 302:
        return False, f"expected 302, got {probe.status}"
    if probe.location != expect_destination:
        return False, f"redirected to {probe.location!r}, expected {expect_destination!r}"
    return True, "ok"


def check_hsk_redirect(probe: Probe, expect_destination: str) -> tuple[bool, str]:
    """/hskN must 301 to /hskN.html -- see check_hsk_lander for the page itself."""
    if DIR_LISTING_RE.search(probe.body):
        return False, f"served a DIRECTORY LISTING instead of redirecting (status={probe.status})"
    if probe.status != 301:
        return False, f"expected 301, got {probe.status}"
    if probe.location != expect_destination:
        return False, f"redirected to {probe.location!r}, expected {expect_destination!r}"
    return True, "ok"


def check_hsk_lander(probe: Probe) -> tuple[bool, str]:
    """/hskN.html must be a real lander page, not a directory listing or 404."""
    if DIR_LISTING_RE.search(probe.body):
        return False, f"served a DIRECTORY LISTING instead of the lander (status={probe.status})"
    if probe.status != 200:
        return False, f"expected 200, got {probe.status}"
    if not HSK_LANDER_RE.search(probe.body):
        return False, "200 but no '<title>HSK N ...' -- not the lander page"
    return True, "ok"


def load_go_redirects() -> dict[str, str]:
    """source -> destination, from serve.json's redirects list, /go/* only."""
    cfg = json.loads(SERVE_JSON.read_text())
    return {r["source"]: r["destination"] for r in cfg.get("redirects", [])
            if r["source"].startswith("/go/")}


HSK_SETS = range(1, 7)


def run(base_url: str) -> int:
    go_redirects = load_go_redirects()
    if not go_redirects:
        print("BLIND: no /go/* entries found in serve.json -- config moved or is empty",
              file=sys.stderr)
        return EXIT_BLIND

    failures: list[str] = []
    reached_anything = False

    for source, destination in sorted(go_redirects.items()):
        try:
            probe = fetch(base_url, source)
        except (URLError, TimeoutError, OSError) as e:
            failures.append(f"{source}: could not reach server ({e})")
            continue
        reached_anything = True
        ok, why = check_go_redirect(probe, destination)
        status = "PASS" if ok else "FAIL"
        print(f"{status} {source} -> {probe.location} : {why}")
        if not ok:
            failures.append(f"{source}: {why}")

    for n in HSK_SETS:
        source, dest, lander = f"/hsk{n}", f"/hsk{n}.html", f"/hsk{n}.html"
        try:
            redirect_probe = fetch(base_url, source)
            lander_probe = fetch(base_url, lander)
        except (URLError, TimeoutError, OSError) as e:
            failures.append(f"{source}: could not reach server ({e})")
            continue
        reached_anything = True

        ok, why = check_hsk_redirect(redirect_probe, dest)
        print(f"{'PASS' if ok else 'FAIL'} {source} -> {redirect_probe.location} : {why}")
        if not ok:
            failures.append(f"{source}: {why}")

        ok, why = check_hsk_lander(lander_probe)
        print(f"{'PASS' if ok else 'FAIL'} {lander} : {why}")
        if not ok:
            failures.append(f"{lander}: {why}")

    if not reached_anything:
        print("BLIND: could not reach any configured route -- network/DNS failure, "
              "not a verdict about the routes", file=sys.stderr)
        return EXIT_BLIND

    if failures:
        print(f"\nFAIL: {len(failures)} route(s) misconfigured:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return EXIT_FAIL

    print(f"\nPASS: {len(go_redirects)} /go/* + {len(HSK_SETS)} /hskN routes all resolve as configured")
    return EXIT_PASS


def self_test() -> int:
    ok = True

    def expect(name, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f"SELF-TEST FAIL {name}: got {got!r}, want {want!r}", file=sys.stderr)

    # check_go_redirect
    good = Probe(302, "/?utm_source=x", "")
    expect("go-good", check_go_redirect(good, "/?utm_source=x")[0], True)
    expect("go-404", check_go_redirect(Probe(404, None, "Not Found"), "/?utm_source=x")[0], False)
    expect("go-wrong-dest", check_go_redirect(Probe(302, "/other", ""), "/?utm_source=x")[0], False)
    listing = Probe(200, None, "<title>Files within build/go/ig-hsk/</title>")
    expect("go-dir-listing", check_go_redirect(listing, "/?utm_source=x")[0], False)

    # check_hsk_redirect
    expect("hsk-good", check_hsk_redirect(Probe(301, "/hsk1.html", ""), "/hsk1.html")[0], True)
    expect("hsk-404", check_hsk_redirect(Probe(404, None, ""), "/hsk1.html")[0], False)
    hsk_listing = Probe(200, None, "<title>Files within build/hsk1/</title>")
    expect("hsk-redirect-dir-listing (the #342 bug shape)",
           check_hsk_redirect(hsk_listing, "/hsk1.html")[0], False)

    # check_hsk_lander
    lander = Probe(200, None, "<title>HSK 1 Vocabulary List — all 150 words</title>")
    expect("lander-good", check_hsk_lander(lander)[0], True)
    expect("lander-404", check_hsk_lander(Probe(404, None, ""))[0], False)
    expect("lander-dir-listing (the #342 bug shape)",
           check_hsk_lander(Probe(200, None, "<title>Files within build/hsk1/</title>"))[0], False)
    expect("lander-wrong-page",
           check_hsk_lander(Probe(200, None, "<title>Word Sets</title>"))[0], False)

    if ok:
        print("SELF-TEST PASS")
        return EXIT_PASS
    return EXIT_FAIL


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=URL_DEFAULT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    return run(args.url)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
