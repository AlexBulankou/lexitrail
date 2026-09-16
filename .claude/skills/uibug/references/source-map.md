# Route → component → style map (ground truth for source mapping)

Verified against `ui/src/App.js` on the branch this skill ships on. If a route
resolves somewhere else than this table says, trust `App.js` and fix this file.

| Route | Component | Styles | Notes |
|---|---|---|---|
| `/` | `components/Home.js` (embeds `Wordsets`) | `styles/Home.css`, `styles/Wordsets.css` | fully public |
| `/wordsets/*` | `PrivateRoute` → `components/Wordsets.js` | `styles/Wordsets.css`, `styles/PrivateRoute.css` | login card when signed out |
| `/game/:wordsetId/:mode?` | `PrivateRoute` → `components/Game.js` | `styles/Game.css`, `styles/WordCard.css` | valid modes `TEST`, `DUE_TODAY`, `SHOW_EXCLUDED`; anything else ⇒ `PRACTICE` |
| `/game` | redirect → `/wordsets` | — | |
| `/about` | `components/About.js` | `styles/About.css` | |
| `/privacy` | `components/PrivacyPolicy.js` | `styles/Policy.css` | |
| `/terms` | `components/TermsOfService.js` | `styles/Policy.css` | |
| `*` | `components/NotFound.js` | `styles/App.css` | large "404" + "Back to home" |

Chrome present on every route: `components/NavBar.js` (`styles/NavBar.css`),
`components/SiteFooter.js` (`styles/SiteFooter.css`), `styles/Global.css`.

## Inside the game screen (where most defects live)

| Element | Emitted by | Styled in |
|---|---|---|
| card grid container `.cards-area` | `Game.js` `updateLayout` | `Game.css` |
| a card (front/back, flip) | `WordCard.js` | `WordCard.css` |
| mini card (test options) | `MiniWordCard.js` | `MiniWordCard.css` |
| 🔊 speaker (card BACK only) | `SpeakButton.js` | `SpeakButton.css` |
| exclude/include toggle `.exclude-button` | `WordCard.js` | `WordCard.css` |
| red/green history tiles `.mastery-indicator` | `utils/historyTiles.js` | `WordCard.css` |
| top bar counters / Show Hints / Flip all | `Game.js` | `Game.css` |
| progress bar | `ProgressBar.js` | `Game.css` |
| results screen | `Completed.js` | `Completed.css` |
| onboarding modal | `OnboardingOverlay.js` | `OnboardingOverlay.css` |

## Layout is computed in JS, not only in CSS

`Game.js` `updateLayout()` derives columns/rows from `window` size and
`calculateFontSize()` auto-scales card text. **This is the prime
mobile-vs-desktop divergence surface** — a box that is wrong on one viewport and
right on the other is very often this function rather than a media query, and
grepping CSS alone will not find it. `utils/cardLayout.js` holds the arithmetic.

## Live data

Wordsets after the client hide-filter (`services/wordsService.js`,
`HIDDEN_DESCRIPTIONS = {'test','HSK7'}`): HSK1–HSK6 and HSK1+2+3. **HSK1 is
`wordset_id = 1`** — that is the id the sweep's routes use.

Descriptions carry a trailing `\r` from CSV import; the filter trims for
matching but tiles render `wordset.description` raw.

## Existing checks worth reading before filing a duplicate

- `e2e/tap_targets.py` — rendered tap-target floor, three-state exit
- `e2e/viewport_fit.py` — does the practice screen fit its viewport (per-rect)
- `e2e/redundant_fetches.py` — duplicate loader payloads on mode switch
- `ui/src/styles/tapTargets.test.js` — declares the floor; **cannot see the render**
