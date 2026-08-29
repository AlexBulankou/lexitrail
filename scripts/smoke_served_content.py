#!/usr/bin/env python3
"""Post-deploy smoke for lexitrail that asserts CONTENT, not status (issue-77 AC3).

WHY A STATUS CHECK CANNOT WORK HERE
-----------------------------------
lexitrail is a single-page app behind a catch-all: *every* path returns 200.
Measured 2026-08-28 against the live site:

    /images/og/generated/og-landscape.png   200  image/png                 202155
    /definitely-not-a-real-path-xyz         200  text/html; charset=utf-8    2871
    /images/og/hsk2-practice.png            200  image/png                 182737

The middle row is a path that does not exist and was invented for the probe. So
`assert resp.status == 200` passes on a URL that serves nothing, and #77's body
records a deploy check that reported the site healthy while a merged security fix
was absent from prod. The discriminator is `Content-Type` and body bytes.

WHAT THIS ASSERTS
-----------------
1. The og:image path the SERVED page declares matches the one the REPO declares.
   Derived from `ui/public/index.html` rather than hardcoded, so the expectation
   cannot silently decay away from source the way a pinned constant does.
2. That asset is a real image (`image/png`), not the SPA shell wearing a 200.

THE NEGATIVE CONTROL IS NOT OPTIONAL
------------------------------------
Check 2 is only meaningful if `image/png` is a value this site can FAIL to
return. If the catch-all ever starts answering `image/png` — or if a CDN starts
content-sniffing — then "it is a PNG" stops discriminating and every future run
passes for free, silently, forever. So the control runs on EVERY invocation
against a path built to not exist, and it must come back as the SPA shell.

That yields three outcomes, and the third must never render as the first:

    exit 0   PASS         served content matches source
    exit 1   FAIL         stale or wrong content -- a real finding
    exit 3   CANNOT-TELL  the control did not discriminate, or the network did
                          not answer. NOT a pass. NOT a failure. Go look.

A smoke test whose instrument has died is worse than no smoke test, because a
green run is exactly what a healthy deploy looks like.
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

DEFAULT_BASE = "https://lexitrail.com"
# A path with no plausible route. If this ever resolves to a real asset the
# control is meant to fail -- that is the point of it.
CONTROL_PATH = "/__smoke_control__no_such_path_9f3a2b"

_OG = re.compile(
    r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', re.I
)


def _fetch(url: str, timeout: float = 20.0) -> tuple[int, str, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "lexitrail-smoke/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, (r.headers.get("Content-Type") or ""), r.read()


def _og_from(text: str) -> str | None:
    m = _OG.search(text)
    return m.group(1) if m else None


def _repo_og(repo_root: Path) -> str | None:
    """The og:image the SOURCE declares, with CRA's build-time token resolved.

    `%PUBLIC_URL%` expands to the empty string for a site served at the domain
    root, which is what the live page shows. Resolving it here rather than
    comparing the raw token keeps the comparison against what is actually
    served.
    """
    idx = repo_root / "ui" / "public" / "index.html"
    if not idx.is_file():
        return None
    raw = _og_from(idx.read_text(encoding="utf-8", errors="replace"))
    return raw.replace("%PUBLIC_URL%", "") if raw else None


def _known_good_route(repo_root: Path) -> str | None:
    """A route this site is DECLARED to serve, read from `serve.json` (#240 AC5).

    Hard-coding `/` worked, and would decay silently the day the routing config
    stopped rewriting it -- the same class as hard-coding the og:image instead of
    reading it from `index.html`. `serve.json`'s `rewrites` IS the declaration of
    what this site routes, so deriving from it means the check cannot drift away
    from the config that decides the answer.

    Takes the first LITERAL source (no `:param`, no `**`), which is `/`.
    """
    cfg = repo_root / "ui" / "public" / "serve.json"
    if not cfg.is_file():
        return None
    try:
        rewrites = json.loads(cfg.read_text(encoding="utf-8")).get("rewrites") or []
    except (json.JSONDecodeError, OSError):
        return None
    for r in rewrites:
        src = (r or {}).get("source", "")
        if src.startswith("/") and ":" not in src and "*" not in src:
            return src
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="checkout to read the expected og:image from",
    )
    args = ap.parse_args(argv)
    base = args.base.rstrip("/")

    # ---- control FIRST. Nothing below means anything until this discriminates.
    #
    # issue-240: this used to require the SPA SHELL (200, text/html) back, because
    # when it was written on 2026-08-28 *every* path on this site returned 200.
    # That was issue-204's bug. #204's fix went live 2026-08-29 in the first UI
    # deploy since 08-11, unknown paths now 404, and the old control therefore
    # reported CANNOT-TELL on every run -- a permanently-red step, which is the
    # muted-alarm outcome #235 AC3 predicted.
    #
    # 🔴 The control's PURPOSE is unchanged: prove `image/png` is a value this site
    # can FAIL to return, so "it is a PNG" below is not passing for free. What
    # changed is the site's contract -- from "everything 200s" to "unknown paths
    # 404, enumerated routes 200". The control is re-pointed at the NEW contract
    # rather than patched to tolerate the new 404: a 200 here is now the ANOMALY,
    # and it means #204 regressed.
    #
    # ⚠️ HTTPError is a SUBCLASS of URLError, so it must be caught first. Merging
    # them is what made "the site 404'd as designed" and "the site did not answer"
    # the same branch -- two facts wearing one value, which is the thing this
    # script exists to refuse (#240 AC3).
    try:
        ctl_status, ctl_ctype, ctl_body = _fetch(base + CONTROL_PATH)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print(f"control ok: {CONTROL_PATH} -> 404 (unknown paths are refused, "
                  f"as issue-204 intends) -- the control discriminates")
            ctl_status = 404
        else:
            print(f"CANNOT-TELL: the control path {CONTROL_PATH} returned HTTP "
                  f"{exc.code}, which is neither the 404 issue-204 guarantees nor "
                  f"a reachable-site answer. Fix the probe before trusting any "
                  f"result below.")
            return CANNOT_TELL
    except (urllib.error.URLError, OSError) as exc:
        print(f"CANNOT-TELL: control request failed ({exc}) -- the site did not "
              f"answer at all, so this run establishes nothing about the deploy. "
              f"This is NOT the same as the expected 404.")
        return CANNOT_TELL
    else:
        # A response with no exception means a 2xx/3xx: the catch-all is back.
        print(f"CANNOT-TELL: the control path {CONTROL_PATH} returned "
              f"{ctl_status} {ctl_ctype.split(';')[0]!r} ({len(ctl_body)}B) "
              f"instead of a 404. The catch-all issue-204 removed has REGRESSED, "
              f"so an unknown path is being served as a real page again -- and a "
              f"PASS below would be vacuous. This is a finding about the site, "
              f"not only about the probe.")
        return CANNOT_TELL

    expected = _repo_og(args.repo_root)
    if not expected:
        print(f"CANNOT-TELL: no og:image found in "
              f"{args.repo_root}/ui/public/index.html -- nothing to compare the "
              f"served page against.")
        return CANNOT_TELL

    route = _known_good_route(args.repo_root)
    if route is None:
        print(f"CANNOT-TELL: could not read an enumerated route from "
              f"{args.repo_root}/ui/public/serve.json -- without one there is no "
              f"route this site GUARANTEES to serve, so a fetch failure below "
              f"could not be told apart from a route that simply is not routed.")
        return CANNOT_TELL
    try:
        _, _, home = _fetch(base + route)
    except (urllib.error.URLError, OSError) as exc:
        print(f"CANNOT-TELL: could not fetch {base}{route} ({exc}) -- and this "
              f"route IS in serve.json's rewrites, so the site should serve it.")
        return CANNOT_TELL

    served = _og_from(home.decode("utf-8", "replace"))
    if not served:
        print(f"FAIL: the served page declares no og:image at all, but the repo "
              f"declares {expected!r}.")
        return FAIL
    if served != expected:
        print(f"FAIL: served og:image {served!r} != source {expected!r}. The "
              f"served build is not this commit's -- this is the stale-deploy "
              f"signal, and a status-code check would have reported it healthy.")
        return FAIL

    asset = served if served.startswith("http") else base + served
    try:
        _, ctype, body = _fetch(asset)
    except (urllib.error.URLError, OSError) as exc:
        print(f"CANNOT-TELL: could not fetch the asset {asset} ({exc})")
        return CANNOT_TELL

    if "image/" not in ctype.lower():
        print(f"FAIL: {asset} returned {ctype!r} ({len(body)}B) -- that is the "
              f"catch-all shell, not the image. The og:image 200s and serves "
              f"nothing.")
        return FAIL

    print(f"PASS: og:image {served} matches source and serves "
          f"{ctype.split(';')[0]} {len(body)}B")
    return PASS


if __name__ == "__main__":
    sys.exit(main())
