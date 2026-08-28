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
    try:
        _, ctl_ctype, ctl_body = _fetch(base + CONTROL_PATH)
    except (urllib.error.URLError, OSError) as exc:
        print(f"CANNOT-TELL: control request failed ({exc}) -- the site did not "
              f"answer, so this run establishes nothing about the deploy.")
        return CANNOT_TELL

    if "text/html" not in ctl_ctype.lower():
        print(f"CANNOT-TELL: the control path {CONTROL_PATH} returned "
              f"{ctl_ctype!r}, not the SPA shell. 'is it an image' has stopped "
              f"discriminating on this site, so a PASS below would be vacuous. "
              f"Fix the probe before trusting any result.")
        return CANNOT_TELL
    print(f"control ok: {CONTROL_PATH} -> {ctl_ctype.split(';')[0]} "
          f"{len(ctl_body)}B (SPA shell, as required)")

    expected = _repo_og(args.repo_root)
    if not expected:
        print(f"CANNOT-TELL: no og:image found in "
              f"{args.repo_root}/ui/public/index.html -- nothing to compare the "
              f"served page against.")
        return CANNOT_TELL

    try:
        _, _, home = _fetch(base + "/")
    except (urllib.error.URLError, OSError) as exc:
        print(f"CANNOT-TELL: could not fetch {base}/ ({exc})")
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
