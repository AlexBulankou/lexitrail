#!/usr/bin/env python3
"""Post-deploy smoke for the lexitrail BACKEND that asserts CONTENT (issue-77 AC3).

WHY A SECOND SMOKE, AND WHY THE UI ONE WILL NOT DO
--------------------------------------------------
`cloudbuild.yaml`'s own header says of the backend rollout:

    python3 scripts/smoke_served_content.py   # ...AND READ THE SERVED BYTES

and marks it "NOT OPTIONAL". It is not wired -- the backend build's steps end at
`backend-deploy` -- and wiring *that* script here would have been worse than the
gap it closes. `smoke_served_content.py` asserts the served og:image matches
`ui/public/index.html`. **No backend deploy can change that value.** It would pass
on every backend build including one that shipped a completely broken API: a check
whose result is independent of the fact it reports.

So this is the backend's own discriminator, not a re-pointing of the UI's.

WHAT THIS ASSERTS
-----------------
1. The wordsets route returns `application/json` AND a non-empty `data` list.

   🔴 The non-empty list is the load-bearing half, and it is why this route was
   chosen over `/`. `/` returns `{"message": "Welcome to the Flask API"}` -- a
   static literal that a backend which booted but CANNOT REACH MYSQL still serves
   perfectly. Rows come from the database, so an empty or absent `data` separates
   "Flask is up" from "the app works", and losing DB connectivity is exactly what
   a backend deploy can break.

2. The route is derived from `backend/app/routes/wordsets.py`'s `url_prefix`
   rather than hardcoded, so the expectation cannot drift away from the source
   that decides it -- same reasoning as the UI smoke reading `index.html`.

THE NEGATIVE CONTROL IS NOT OPTIONAL
------------------------------------
Check 1 only means something if `application/json` is a value this host can FAIL
to return. Measured 2026-09-01 against `api.lexitrail.com`:

    /wordsets                    200  application/json            386
    /definitely-not-real-xyz     404  text/html; charset=utf-8    207
    /                            200  application/json             39

The middle row is the discriminator: Flask's default 404 is HTML, so a JSON
content-type genuinely distinguishes a routed answer from an unrouted one. If a
proxy or error handler ever starts answering unknown paths in JSON, that stops
being true and every future run passes for free, silently, forever. The control
therefore runs on EVERY invocation.

Three outcomes, and the third must never render as the first:

    exit 0   PASS         the API served real rows from the database
    exit 1   FAIL         wrong or empty content -- a real finding
    exit 3   CANNOT-TELL  the control did not discriminate, or the host did not
                          answer. NOT a pass. NOT a failure. Go look.

A smoke whose instrument has died is worse than no smoke, because a green run is
exactly what a healthy deploy looks like.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

PASS, FAIL, CANNOT_TELL = 0, 1, 3

DEFAULT_BASE = "https://api.lexitrail.com"
# A path with no plausible route. If this ever resolves the control is meant to
# fail -- that is the point of it.
CONTROL_PATH = "/__smoke_control__no_such_route_5c1d7e"

_PREFIX = re.compile(r"""url_prefix\s*=\s*['"]([^'"]+)['"]""")


def _fetch(url: str, timeout: float = 20.0) -> tuple[int, str, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "lexitrail-backend-smoke/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, (r.headers.get("Content-Type") or ""), r.read()


def _wordsets_route(repo_root: Path) -> str | None:
    """The wordsets prefix the SOURCE declares.

    Read from the blueprint rather than hardcoded: a hardcoded '/wordsets' would
    keep passing against a stale deploy on the day the prefix changed, which is
    the decay this whole file exists to refuse.
    """
    src = repo_root / "backend" / "app" / "routes" / "wordsets.py"
    if not src.is_file():
        return None
    m = _PREFIX.search(src.read_text(encoding="utf-8", errors="replace"))
    return m.group(1) if m else None


def _run_control(base: str) -> tuple[int, str] | None:
    """None on success (the control discriminated); (code, message) otherwise."""
    # ⚠️ HTTPError is a SUBCLASS of URLError and must be caught first. Merging
    # them makes "the host 404'd as designed" and "the host did not answer" the
    # same branch -- two facts wearing one value, which is what this refuses.
    try:
        status, ctype, body = _fetch(base + CONTROL_PATH)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            ctype = (exc.headers.get("Content-Type") or "") if exc.headers else ""
            if "json" in ctype.lower():
                return (
                    CANNOT_TELL,
                    f"CANNOT-TELL: the control path {CONTROL_PATH} 404'd but did so "
                    f"as {ctype.split(';')[0]!r}. JSON is then NOT a value this host "
                    f"can fail to return, so the content-type assertion below would "
                    f"pass for free. Fix the probe before trusting any result.",
                )
            print(
                f"control ok: {CONTROL_PATH} -> 404 {ctype.split(';')[0]!r} "
                f"-- JSON is a value this host can fail to return, so the control "
                f"discriminates"
            )
            return None
        return (
            CANNOT_TELL,
            f"CANNOT-TELL: the control path {CONTROL_PATH} returned HTTP "
            f"{exc.code}, which is neither the expected 404 nor a reachable-host "
            f"answer.",
        )
    except (urllib.error.URLError, OSError) as exc:
        return (
            CANNOT_TELL,
            f"CANNOT-TELL: control request failed ({exc}) -- the host did not "
            f"answer at all, so this run establishes nothing about the deploy. "
            f"This is NOT the same as the expected 404.",
        )
    # No exception means 2xx/3xx: an unrouted path is being served as real.
    return (
        CANNOT_TELL,
        f"CANNOT-TELL: the control path {CONTROL_PATH} returned {status} "
        f"{ctype.split(';')[0]!r} ({len(body)}B) instead of a 404. An unknown "
        f"route is being answered, so a PASS below would be vacuous. This is a "
        f"finding about the API, not only about the probe.",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="checkout to read the expected route from",
    )
    args = ap.parse_args(argv)
    base = args.base.rstrip("/")

    # ---- control FIRST. Nothing below means anything until this discriminates.
    failed = _run_control(base)
    if failed is not None:
        code, msg = failed
        print(msg)
        return code

    route = _wordsets_route(args.repo_root)
    if route is None:
        print(
            f"CANNOT-TELL: could not read url_prefix from "
            f"{args.repo_root}/backend/app/routes/wordsets.py -- without it there "
            f"is no source-declared route to compare the deploy against."
        )
        return CANNOT_TELL

    try:
        status, ctype, body = _fetch(base + route)
    except urllib.error.HTTPError as exc:
        print(
            f"FAIL: {base}{route} returned HTTP {exc.code}. This route IS declared "
            f"in the blueprint source, so the running image is not serving what "
            f"this checkout describes."
        )
        return FAIL
    except (urllib.error.URLError, OSError) as exc:
        print(
            f"CANNOT-TELL: could not reach {base}{route} ({exc}) -- the host did "
            f"not answer, which is not the same as serving the wrong thing."
        )
        return CANNOT_TELL

    if "json" not in ctype.lower():
        print(
            f"FAIL: {base}{route} returned {status} {ctype.split(';')[0]!r} "
            f"({len(body)}B) rather than JSON -- the API route is being answered "
            f"by something that is not the API."
        )
        return FAIL

    try:
        payload = json.loads(body.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        print(f"FAIL: {base}{route} claimed JSON but did not parse ({exc}).")
        return FAIL

    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        print(
            f"FAIL: {base}{route} returned JSON with no `data` list "
            f"(got {type(rows).__name__}). Keys: {sorted(payload)[:8] if isinstance(payload, dict) else 'n/a'}"
        )
        return FAIL
    if not rows:
        print(
            f"FAIL: {base}{route} returned an EMPTY `data` list. Flask is up and "
            f"routing, but no rows came back -- which is what a lost database "
            f"connection looks like from outside. A `/` check would have passed."
        )
        return FAIL

    print(f"PASS: {route} served {len(rows)} row(s) as {ctype.split(';')[0]} ({len(body)}B)")
    return PASS


if __name__ == "__main__":
    sys.exit(main())
