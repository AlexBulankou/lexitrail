# `e2e/` — render-level checks, deliberately outside the product tree

Nothing in here is a dependency of the app. `ui/package.json`,
`ui/package-lock.json`, `ui/src/**` and `backend/app/**` are untouched by
design, per `docs/itp-playwright-usability.md` §2.4.

## `tap_targets.py` — the 44px floor, measured rather than declared

```bash
python3 e2e/tap_targets.py --self-test      # validate the detector itself
python3 e2e/tap_targets.py                  # measure prod, mobile + desktop
python3 e2e/tap_targets.py --url http://localhost:3000 --viewport mobile
```

`ui/src/styles/tapTargets.test.js` checks that the CSS *declares* a ≥44px floor
and says in its own docstring that it cannot speak to the rendered box. It was
green throughout the period when 23 of 33 controls on the live mobile site
rendered under 44px. This measures the rendered box.

**Read the module docstring before changing it** — the three-state exit, the
regex-form analytics block, and the self-test are each there for a stated
reason, and each has a failure mode that looks like success if removed.

### Exit codes are three-state on purpose

| exit | meaning |
|---|---|
| 0 | `PASS` — every visible control measured at or above the floor |
| 1 | `FAIL` — at least one measured under it, or an analytics beacon completed |
| 2 | `BLIND` — could not measure (navigation failed, or zero controls found) |

`BLIND` exists so that "I could not look" can never be reported as "the page is
clean", which is the most likely way for a check like this to start lying.

### Why it is not a PR gate yet

Prod currently **fails** it (23 undersized on mobile, 16 on desktop). Turning it
into a blocking gate before the fix lands would red every PR, and a gate people
routinely override stops being a gate — the override becomes the habit. Order:
harness (this) → fix the controls → then gate.

### Scope today

The public landing page only, which needs no session and already reproduces the
defect. The authenticated/guest journeys in
`docs/itp-playwright-usability.md` are not covered yet. **Never** click
"Sign in with Google" when extending this; use the guest path, and keep the
analytics abort installed on the context before the first navigation.

## `redundant_fetches.py` — mode switches refetch identical bytes (lexitrail#91)

```bash
python3 e2e/redundant_fetches.py --self-test   # validate the detector itself
python3 e2e/redundant_fetches.py               # measure prod (nav=click, default)
python3 e2e/redundant_fetches.py --nav goto    # the deep-link/reload path
```

### `--nav click` is the default because `goto` cannot see a caching fix

`page.goto()` is a HARD navigation: it reloads the SPA and wipes
`window.userWordsetExcludedCache` every view, so no in-memory caching fix can
ever move its number. The first version of this harness used `goto` and
reported an unchanged 18 redundant against a build that had **zero** duplicate
loader payloads — a detector whose value was independent of the fact it
reports. `--nav click` uses client-side routing, which is what a user does when
switching mode, and is the only arm in which the cache can apply. `--nav goto`
is kept because deep-links and reloads are a real path, but it grades a
different thing.

`useWordsetLoader`'s cache key carries `mode`; the payloads it caches do not
(`getWordsByWordset(wordsetId)` and `getUserWordsByWordset(userId, wordsetId)`
take no mode — `mode` only drives a client-side `.filter()`). So every mode
switch is a guaranteed cache miss on bytes already in memory. Measured on prod
2026-08-10: 3 wordsets × 4 modes → **24 data requests, 7 distinct, 17
redundant**, each wordset fetched 4×.

⚠️ The data matcher is a REGEX anchored on the wordset id
(`/wordsets/<id>/words`, `/userwords/`), not the substring `/words` — which
also matches `/wordsets`, the LIST endpoint the home page refetches on every
back-navigation. That one call accounted for all 12 apparent "redundant"
requests on a build whose loader payloads were already clean.

Same three-state exit as `tap_targets.py`, for the same reason — `BLIND` (2)
exists so "I could not look" can never be reported as "no redundancy". Note
the extra BLIND trigger: **zero data requests observed** means the probe never
exercised the loader, which is not the same as the loader being efficient.

### It reports the stall but never gates on it

Item 6 in #52 is *"loading persisted several minutes"*. That is reported and
never gated, because it did not reproduce on the guest journey (~1.0s on both
arms). Gating on a symptom we cannot summon produces a check that is green for
the wrong reason.

### This one clicks, so the analytics abort is load-bearing

`tap_targets.py` never clicks and so cannot fire a beacon. This harness clicks
**Try**, which fires a GA4 `try_with_demo_account` event, so the abort is
installed on the context before the first navigation and the run **fails** if
any beacon completed. Measured 13 blocked / 0 completed.

### Why it is not a PR gate yet

Prod currently fails it (17 redundant). Same ordering as the tap-target floor:
harness → fix (#91) → then gate. A gate that reds every PR gets overridden, and
the override becomes the habit.
