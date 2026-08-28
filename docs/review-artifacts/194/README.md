# lexitrail#194 — signed-out wordset grid restyle + above-fold CTA

Before/after screenshots for the `/` (signed-out) landing page, captured
from a real `react-scripts build` of each state (base commit vs. this PR's
head) with a scratch Playwright script serving the build statically and
stubbing `GET /wordsets` — the same shape `e2e/today_screenshots.py` and
`e2e/manifest_screenshots.py` already use, just standalone rather than
reusing their SPAHandler (this is a one-off comparison capture, not part of
the e2e suite).

## What changed

| | before | after |
|---|---|---|
| wordset tile | dotted-gray box, 4 saturated-color buttons (blue/purple/black/green), Test! spans 3 button-heights | white card matching `.feature-card`/`.login-card`, ONE primary action (Practice, `#1a73e8`), Due Today/Show Excluded/Test as equal-weight muted secondary actions |
| first CTA | bottom of page, ~4.5 viewport-heights down on mobile | second CTA + one-line SRS value prop right after the hero copy, above the wordset grid |
| tile heading | 2rem — larger than any surrounding page heading | 1.3rem, matches page hierarchy |
| `.cta-button` color | `#007bff` (Bootstrap blue — a third, unrelated blue on this page) | `#1a73e8` (the app's real palette, matches `.start-button`/`.login-card h2`) |

## Viewports

- mobile 390×844
- desktop 1440×900

## Files

- `before-mobile.png` / `before-desktop.png` — base commit
- `after-mobile.png` / `after-desktop.png` — this PR's head
