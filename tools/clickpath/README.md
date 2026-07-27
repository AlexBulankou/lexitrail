# Click-path verification

Browser-navigation check for the `/go/*` short links. Closes the verification half
of lexitrail#64.

```bash
cd tools/clickpath
npm install
npm run verify                              # against production
npm run verify -- --base http://localhost:3000
```

Exits non-zero on any failure, so it can gate a deploy.

## Why a navigation and not a curl

Production serves the SPA with `"rewrites": [{ "source": "**", "destination":
"/index.html" }]`, so **every path returns 200** — including paths that render the
404 component. A status-code assertion cannot distinguish a working link from a
dead one here.

This is not hypothetical. `/hsk2` was referenced as a destination, has never
existed as an SPA route, and returns `200` while rendering *"404 — We couldn't find
that page."* Issue #51's acceptance criterion was "assert `/hsk2` resolves 200",
which passes today, on a page that is broken.

So the check navigates in a real browser from a clean context and asserts what
*rendered*: that a 3xx hop actually happened, that the landing URL kept its UTM
parameters, and that the body is a real page rather than the 404 shell.

## The controls are the point

`MUST_BE_BROKEN` holds paths that should render 404. The run fails if one of them
starts looking healthy.

Without that, a verifier can quietly lose its ability to tell the two apart and
every green line above becomes meaningless — you would be reading "6 redirects OK"
from a check that would say the same thing if the site were down. Verified in both
directions when written:

| path | HTTP | rendered | verdict |
|---|---|---|---|
| `/go/ig-hsk` | 302 → 200 | 1508 chars, real homepage, UTM intact | works |
| `/hsk2` | **200** | 74 chars, "404 We couldn't find that page" | broken |
| `/go/this-route-does-not-exist` | **200** | 74 chars, same shell | broken |

Pointing a `MUST_REDIRECT` entry at `/hsk2` produces five specific failures (no 3xx
hop, 404 component, shell-sized body, both UTM params missing) rather than a bare
"failed" — so a real regression tells you which property broke.

## Current state

All six redirects in `ui/public/serve.json` work in production: real 302, one hop,
UTM preserved, real page rendered. **The premise in #64 — "SPA-served with no
server-side redirect" — is disproven.** Prod runs `serve -s build` (`ui/Dockerfile`),
which is precisely the package that *does* read `serve.json`; the earlier diagnosis
assumed nginx.

`MUST_REDIRECT` is kept in sync with `serve.json` by hand, deliberately. Parsing the
file would make a deleted redirect silently shrink the test's own scope instead of
failing it.

## What this does NOT fix

The redirects work; the **click path from IG and TikTok still doesn't exist**, for a
reason no redirect can address. See `docs/click-path.md`.
