# lexitrail#107 — the Today home, rendered (PR #133)

Captured by `e2e/today_screenshots.py` against the production **build**, with
the two API calls stubbed. @ensemble-hc2 blocked #133 on "did anyone look at
the rendered thing" — these are that look.

| | desktop 1440×900 | mobile 390×844 |
|---|---|---|
| reviews due | `today-due-desktop.png` | `today-due-mobile.png` |
| all caught up | `today-caught-up-desktop.png` | `today-caught-up-mobile.png` |

```
OK: all screenshots captured, no unstubbed requests   (exit 0)
```

## What these prove, and what they do not

**Prove:** the real bundle, real CSS, real component tree, real router, at a
real viewport — everything between `Today.js` and pixels.

**Do not prove:** that the live API returns this shape, or that this renders on
prod. lexitrail has no Cloud Build trigger (#77), so nothing deploys on merge;
#107's "shipped to prod, verified live" AC stays open there. The stubs match
`getWordsets` / `getUserWordsByWordset` as the code calls them — a backend
contract change would pass here and fail live.

## Two things LOOKING found that reading the diff did not

Neither is a defect in this PR; both are visible in the shots above and are
recorded so they are not rediscovered as surprises.

1. **Desktop is top-anchored with a lot of empty page below it.** The whole
   habit screen occupies roughly the top quarter of a 1440×900 viewport. It is
   not broken — the content is centred horizontally and legible — but the mock
   in `docs/mocks/lt-redesign-decisions.html` is a fuller composition, and RD-2
   (#108) is the issue that fills that space with the session list. Deliberately
   not vertically centring it here: that decision belongs with #108's content,
   not guessed at now.

2. **The streak line shows `0/10 words today` for a learner with no streak,
   where `StreakBadge` deliberately renders nothing at 0/0** ("don't clutter the
   bar with a 0-day streak"). That divergence is intentional — on the nav bar a
   zero streak is noise, on the habit screen the daily goal IS the content, and
   a learner who has done nothing today is exactly who needs to see `0/10`. It
   is a real inconsistency between two surfaces reading one store, so it is
   named rather than left for someone to "fix" in one direction without knowing
   the other was chosen.

## Reproducing

```bash
cd ui && CI=true npx react-scripts build && cd ..
python3 e2e/today_screenshots.py --build ui/build --out docs/review-artifacts/107
```

The harness is fail-closed on the network: every request to the API origin is
either fulfilled from a fixture or aborted **and reported**, so a shot taken
while quietly talking to the real `api.lexitrail.com` cannot pass as this one.
That guard earned its keep twice while these were being made — it caught a
predicate bug of mine (`/wordsets` contains the substring `/words`) and then a
wrong stub shape, each of which would otherwise have produced a screenshot of
the error state filed as a working screen.
