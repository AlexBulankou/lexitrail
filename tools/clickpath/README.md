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

## Bio links — added here, and the reason they matter most

`serve.json` gained `/go/ig`, `/go/tiktok`, `/go/tt`, `/go/pinterest`, `/go/yt`.
All five were **404ing in production** (200 + the 404 component) before this change,
confirmed by navigation.

These are the paths `SUAM-channel-provisioning.md` requires every profile bio to carry,
and on Instagram and TikTok the bio link is the *only* tappable click path — captions
are not linkified. So a 404 there was not a cosmetic gap: it made every bio click on
those channels a lost, unattributed lead. Reported as P0 finding #1 of decipher#2494.

They use `utm_campaign=bio` rather than a per-post value, because a profile bio is one
link for the whole profile — per-campaign granularity is not physically available on
that surface.

**These will FAIL a production run until the app is redeployed.** That is the check
being honest, and it doubles as the post-deploy acceptance test.

## Running against a local build

`--base http://localhost:3111` (with `npx serve -s ui/build`) verifies the redirects
themselves, which are server-side and independent of what the app renders — I confirmed
all 11 that way, real 302 with the right Location.

It will **not** satisfy the controls unless `ui/build` is a current build of the
production app. `ui/build` is gitignored, so it can be arbitrarily stale — mine held an
old test-harness build, and the controls correctly reported that they could not
discriminate rather than passing quietly. Rebuild before trusting a local control run.

## What this does NOT fix

The redirects work; the **click path from IG and TikTok still doesn't exist**, for a
reason no redirect can address. See `docs/click-path.md`.
