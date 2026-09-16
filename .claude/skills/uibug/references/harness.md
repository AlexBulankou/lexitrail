# Harness reference

```
harness/
  setup.sh              idempotent install; never re-downloads browsers
  reach.js              preflight: is the target reachable (0 PASS / 1 FAIL / 2 BLIND)
  run.js                CLI front door; runs the sweep, writes findings.json
  playwright.config.js  viewport projects, external baseURL, no webServer
  sweep.spec.js         one test per route per viewport
  lib/analytics.js      GA beacon abort (regex form) + completed-beacon assertion
  lib/session.js        guest-session generator / credential manager
  lib/detectors.js      in-page geometric + logic detectors
  lib/routes.js         route list and viewport definitions
  lib/browser.js        finds an installed chromium when Playwright's pin differs
  lib/apimock.js        API fixtures -- SURROGATE RUNS ONLY (--mock-api)
```

## Commands

```bash
bash harness/setup.sh
node harness/reach.js https://lexitrail.com
node harness/run.js --url https://lexitrail.com --env both   --out /tmp/uibug/run1
node harness/run.js --url http://localhost:3000   --env mobile --out /tmp/uibug/local --skip-reach
```

Flags: `--url`, `--env desktop|mobile|both`, `--out <dir>`, `--skip-reach`,
`--mock-api` (surrogate only — stubs `api.lexitrail.com`; never use it against
the live site, and `findings.json` stamps `surrogate: true` when you do).
Env: `UIBUG_URL`, `UIBUG_ENV`, `UIBUG_OUT`, `UIBUG_STORAGE_STATE`,
`PLAYWRIGHT_BROWSERS_PATH` (defaults to `/opt/pw-browsers`).

## Exit codes — three-state, matching `e2e/tap_targets.py`

| exit | meaning |
|---|---|
| 0 | sweep completed, artifacts written |
| 1 | a test failed (today that means **an analytics beacon completed**) |
| 2 | **BLIND** — unreachable target, or zero route/viewport pairs measured |

BLIND is a distinct code so that "I could not look" can never be reported as
"the page is clean". If `run.js` exits 2, you have no findings — say so, rather
than filling the count from source reading.

## Output

```
<out>/findings.json              merged summary + every row (read this first)
<out>/findings.ndjson            append-only per-route records
<out>/screens/<viewport>/NN-slug.png        full-page
<out>/screens/<viewport>/NN-slug-fold.png   above-the-fold
<out>/dom/<viewport>/NN-slug.json           every visible box + computed style
```

Both screenshots exist because `fullPage` stretches the viewport, which hides the
clipping and overflow the detectors are looking for. Judge fit from `-fold`.

## What the detectors mean

| kind | fires when | what to check before filing |
|---|---|---|
| `tap-target` | interactive box < 44px in either axis | already tracked in bulk by `e2e/tap_targets.py` — file a specific control, not the class |
| `viewport-overflow` | a box extends past the viewport horizontally | is it a deliberate horizontal scroller? |
| `clipped` | `overflow:hidden` box with `scrollWidth > clientWidth` | *which end* is clipped — `flex-end` clips the left |
| `overlap` | two interactive boxes intersect, neither containing the other | is one genuinely untappable, or is it a decorative hit area? |
| `dead-control` | `href` empty/`#`, or a `disabled` control at full opacity | router-driven anchors are a real pattern; confirm it truly goes nowhere |
| `contrast` | text under WCAG AA for its size | the walk-up background is an approximation over images/gradients |
| `page-h-scroll` | `documentElement.scrollWidth > innerWidth` | usually one child; find it before filing the page |

Detectors find geometry. **Aesthetics and broken logic come from you reading the
screenshots** — misalignment, wrong labels, a mode rendering the wrong screen.
Both count, and both need a screenshot plus a DOM box.

## An error page is still a page

The sweep's first run reported `ok` for all four game routes at 23 elements each,
because every one of them had rendered "Error loading data. Please try again." —
a real DOM, a navbar, a footer, and nothing anybody asked to measure. The sweep
now matches known error copy and calls that route **BLIND**, with an `-ERROR.png`
capture to diagnose it.

BLIND and not a finding, deliberately: a backend that is down, or a fixture whose
shape the app rejects, is not a UI defect, and filing it as one produces a PR
against the wrong repo. If a route comes back BLIND on a surrogate run, check the
fixture envelope in `lib/apimock.js` against its consumer before believing the site.

## Things the harness deliberately does not do

- **No `webServer`.** It grades the deployed artifact; a config that can start a
  local server can silently measure a tree nobody shipped.
- **No assertions on product state.** An always-red gate gets overridden, and the
  override becomes the habit (`e2e/README.md`). The single assertion is that no
  analytics beacon completed — a harm we cause, not a defect we find.
- **No parallel workers.** Concurrent guest sessions multiply `@lexitrail.demo`
  rows in the production database for no measurement gain.
- **No `networkidle` waits.** The SPA holds a socket open, so it never settles.
