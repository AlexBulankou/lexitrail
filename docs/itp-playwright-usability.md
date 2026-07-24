# ITP — Playwright Usability Exploration: Lexitrail (LT)

| | |
|---|---|
| **App** | Lexitrail — Chinese-vocabulary spaced-repetition flashcards |
| **Live target** | https://lexitrail.com (API: https://api.lexitrail.com) |
| **Repo** | `AlexBulankou/lexitrail` (default branch `main`) |
| **This doc lives at** | `docs/itp-playwright-usability.md` |
| **Author findings on branch** | `itp-*` (repo convention — e.g. `itp-usability-pass-YYYY-MM-DD`) |
| **Tool** | Playwright (Chromium), driving the **LIVE deployed** site |
| **Mode** | READ-ONLY · analytics-safe · both mobile **and** desktop viewports |

---

## 0. Your role

**You are an independent usability tester driving the LIVE Lexitrail app with Playwright.**

You did not write this app and you will not fix it. Your job is to open the *real, deployed* site at https://lexitrail.com in Playwright, walk its real user journeys as a first-time user would, and evaluate every screen through three lenses — **Usability**, **UI Convenience**, and **Aesthetics** — on **both a mobile and a desktop viewport**. You capture screenshot evidence for everything you find, assemble it into one shareable gallery with a live URL, and hand the whole thing off as a findings PR to the owning crew. You do **not** edit product code and you do **not** decide what to fix — you observe, evidence, and file.

This ITP exists because a prior shipping pass did **not** exercise the deployed UI with a browser, and shipped UI broke as a result. So: **test the real deployed app, in a real browser, on both form factors, with proof.** No unit tests, no local dev server, no "it should work."

---

## 1. What Lexitrail is

Lexitrail is a Chinese-vocabulary learning web app built around **spaced-repetition flashcards**. A single-page React app (Create React App / react-scripts 5, React 18, react-router-dom v6) talks to a Flask REST API at `https://api.lexitrail.com` (Python 3.9 + MySQL on GKE).

**Core loop:** pick a wordset (an HSK level) → study/review flashcards that flip from **front (hanzi)** to **back (hanzi + pinyin + English)** → mark each word **correct (✔️)** or **incorrect (❌)** → **exclude** words you already know → track mastery via **red/green per-answer history tiles**.

**Four modes** exist for each wordset: **Practice**, **Test** (multiple-choice quiz), **Due Today** (SRS queue), and **Show Excluded**.

**Auth** is Google OAuth **or** a first-class guest *"Try without signing in"* demo session — the guest path is the one you will use (see §2). **Audio** pronunciation uses the browser-native Web Speech API (zh-CN). **GA4 analytics is live** (measurement id `G-910V8PX54C`) — which is why the analytics-safe setup in §2 is mandatory.

**Language correctness is safety-critical.** This is a learning app: a wrong hanzi, wrong pinyin, wrong tone, or a quiz whose "correct" option is actually wrong *teaches the user the wrong thing*. Treat any language error as high severity.

---

## 2. Setup & access (analytics-safe)

### 2.1 The live target

- App (React SPA): **https://lexitrail.com** — returns HTTP 200, serves built static `index.html`. The landing page `/` is fully public (not auth-gated at the HTTP layer).
- API: **https://api.lexitrail.com** — `GET /wordsets` returns the wordset list JSON unauthenticated; write/user endpoints require a Bearer token.
- **Do NOT run a local dev server.** This ITP tests the *deployed* app. Every `page.goto` targets `https://lexitrail.com`.

### 2.2 The analytics-safe access path — guest *"Try without signing in"*

**No login is required and NO credential/token needs to be handled — there is nothing to expose, and there is no beta/approved-users gate.** Access works like this:

1. `/` is public and even renders the wordset grid inline.
2. Clicking any wordset action (or navigating to `/wordsets` or `/game/...`) hits the client-side `PrivateRoute`, which shows a login card headed **"Ready to Start Learning?"** with two buttons: **"Sign in with Google"** and **"Try without signing in"**. A **"Try"** button is also in the top nav.
3. **Your entry point = click "Try without signing in"** (or the nav **"Try"** button). This calls `tryWithoutSignin()` in `ui/src/contexts/AuthContext.js`, which mints a throwaway guest identity `<random5>@lexitrail.demo` and stores `sessionStorage.access_token = "UNAUTH_USER:<demoEmail>"`. The Flask backend (`backend/app/auth.py`) accepts `UNAUTH_USER:` tokens **only** for the `lexitrail.demo` domain, so guest sessions are isolated and can never impersonate a real member.

This is a supported, documented path: **no real Google account, no real signup, no payment** (the app is free). There is **no** `?internal=1` self-tag, **no** test-DB toggle, and **no** analytics-disable env in this build.

> **Guest writes:** guest actions (mark correct/incorrect, exclude/include) *do* write to the real prod DB, but only under the isolated `@lexitrail.demo` email — never touching real users. Treat writes as **acceptable-but-minimize**. Never complete a real Google sign-in, never attempt account deletion, and note there is no destructive/irreversible action to trigger anyway.

### 2.3 The mandatory analytics beacon block

Even on the guest path, **GA4 gtag events still fire** (`try_with_demo_account`, `wordset_click`, `recall`, login clicks, etc.). To stay **funnel-safe**, you MUST intercept and **abort** all analytics beacons **before you navigate** — set the route on the *context* (so it applies to every page/tab) and set it *first*.

gtag.js actually loads from **`www.googletagmanager.com`** and GA4 beacons hit **`www.google-analytics.com`** / **`region1.google-analytics.com`**, so the matcher MUST cover those real (subdomained) hosts. **Use the regex form below** — it substring-matches the *full request URL*, so it correctly catches the `www.` / `region1.` subdomains.

> ⚠️ Do **NOT** substitute Playwright glob patterns like `**/google-analytics.com/**`. A glob has no wildcard segment to absorb the `www.` / `region1.` subdomain (and the required `/domain/` boundary isn't present when the host is `www.domain`), so those globs silently **miss** the real hosts and let live analytics through — poisoning the GA4 funnel. If you insist on globs you must add the extra `*` segment (`**/*google-analytics.com/**`, `**/*googletagmanager.com/**`, `**/*analytics.google.com/**`); the regex is safer, so prefer it.

```js
// In a Playwright Test run, install this in test.beforeEach (or a fixture) —
// each test gets a FRESH BrowserContext, so setting it once globally is not enough.
// It MUST be installed BEFORE the first page.goto.
let analyticsBlocked = 0;
test.beforeEach(async ({ context }) => {
  await context.route(
    /googletagmanager\.com|google-analytics\.com|analytics\.google\.com/,
    route => { analyticsBlocked++; return route.abort(); }
  );
});
// After the run, log `analyticsBlocked` and confirm ZERO analytics requests
// actually completed. Report that blocked-count in the PR to PROVE the GA4
// funnel stayed clean (i.e. no *google-analytics.com/g/collect beacon left the browser).
```

Guest session + analytics abort = a **read-only, funnel-safe** test session.

### 2.4 Install & launch Playwright

No Playwright/Cypress/e2e setup exists in the repo yet (the only `playwright` string is a transitive lockfile entry). Add it fresh as **test scaffolding**, kept **entirely out of the product tree**: do **not** modify `ui/package.json`, `ui/package-lock.json`, or anything under `ui/src/**` or `backend/app/**`. Instead create a **new top-level `e2e/` folder** (on your `itp-*` branch) with **its own `package.json`**, so `@playwright/test` is a dependency of the e2e harness only and never of the product `ui/` app:

```bash
mkdir -p e2e && cd e2e
npm init -y
npm i -D @playwright/test
npx playwright install chromium
```

This adds `e2e/package.json` + `e2e/package-lock.json` (test-only, and part of the committed scaffolding — see §5.3) while leaving the product `ui/` tree completely untouched. Drive the **live** site — no `npm start`. A minimal two-viewport config:

```js
// e2e/playwright.config.js
const { devices } = require('@playwright/test');
module.exports = {
  testDir: __dirname,
  use: { baseURL: 'https://lexitrail.com', trace: 'off' },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'mobile',  use: { ...devices['iPhone 13'] } }, // 390×844, touch, mobile UA
  ],
};
```

> This is an *exploration* pass, not a fixed-assertion suite: all evidence comes from the explicit `page.screenshot()` calls in §3, so **no** `screenshot` auto-capture key is set (an assertion-free run would never trigger `only-on-failure` anyway).

Do **at least one headed pass** (`--headed`) per viewport so you can **visually verify** layout, the flip animation, and control placement (e.g. the 🔊 speaker on the card back) with your own eyes. Headless is fine for capturing evidence, but a human-visible pass catches rendering issues that screenshots alone can miss. (Headed vs headless does **not** change whether the 🔊 button renders — see Journey 4 watch-for #5.)

### 2.5 Viewports — BOTH mobile AND desktop (HARD RULE)

**Every journey and every screen below MUST be exercised on both:**

- **Desktop** — 1440×900 (Chromium, mouse).
- **Mobile** — iPhone 13 (390×844) *or* Pixel 5, using Playwright's `devices[...]` so touch + mobile UA are emulated.

Lexitrail's card grid (`Game.js` `updateLayout` computes columns/rows from `window` size) and its auto font-scaling (`calculateFontSize`) make **mobile-vs-desktop divergence the single most important thing to check**. A finding on one viewport is not a finding on the other — record the viewport for every finding, and capture the same screen on both.

---

## 3. Exploration protocol

### The three lenses — apply ALL THREE at EVERY screen, on BOTH viewports

**1. USABILITY** — Can a brand-new user accomplish the core task (study a flashcard set) without confusion? Look for: friction points, dead-ends, unclear affordances, missing feedback after an action, broken/misleading states, controls that are present but too small/ambiguous to use, and *advertised-but-missing* features.

**2. UI CONVENIENCE** — clicks/taps-to-goal, discoverability of controls, responsiveness, sensible defaults, and the completeness of **loading / empty / error** states. Note keyboard ergonomics on desktop and touch-target size on mobile.

**3. AESTHETICS** — visual hierarchy, spacing/alignment, typography (including the auto-scaled card text), color/contrast (WCAG-ish), consistency across screens, general polish, and specifically **how it holds up on the small screen**.

### Screenshot discipline

- Capture a screenshot at **every screen and every notable state** (default, loading, empty, error, after-action, completed), for **both viewports**.
- Prefer full-page: `await page.screenshot({ path, fullPage: true })`.
- Naming convention (you will fold these into the gallery in §4):
  `screens/<viewport>/<NN>-<journey-slug>-<state>.png`
  e.g. `screens/mobile/04-practice-back.png`, `screens/desktop/06-due-today-empty.png`.
- **Every finding in your table (§5) must link to at least one screenshot.** No screenshot → not a finding.

### Route / component quick-map (ground truth)

| Route | Renders | Notes |
|---|---|---|
| `/` | `Home.js` (embeds `Wordsets`) | public |
| `/wordsets/*` | `PrivateRoute` → `Wordsets.js` | login card if not signed in / not guest |
| `/game/:wordsetId/:mode?` | `PrivateRoute` → `Game.js` | `mode` optional; valid = `TEST`, `DUE_TODAY`, `SHOW_EXCLUDED`; anything else ⇒ `PRACTICE` |
| `/game` | redirect → `/wordsets` | |
| `/about`, `/privacy`, `/terms` | `About.js` / `PrivacyPolicy.js` / `TermsOfService.js` | via nav "About" dropdown |
| `*` | `NotFound.js` | 404 with "Back to home" |

Live wordsets after the client hide-filter (`ui/src/services/wordsService.js`, `HIDDEN_DESCRIPTIONS = {'test','HSK7'}`): **HSK1, HSK2, HSK3, HSK4, HSK5, HSK6, and HSK1+2+3**. HSK1 is `wordset_id = 1`.

---

Walk the ten journeys below **in order**. Each lists the exact route/steps, a 3-lens checklist, and a **Watch-for** callout naming the known high-value defect targets for that screen.

### Journey 1 — Landing → Start Learning (public home funnel)

**Route/steps:** Open `https://lexitrail.com/`. Observe the hero (logo, "Welcome to Lexitrail", value prop), the **6 feature cards** (Smart Word Sets, AI Memory Hints, Interactive Practice, **Cultural Context**, Character Breakdown, Expanding Horizons), the inline wordset grid, and the **"Start Learning Chinese"** CTA. Click the CTA → routes to `/wordsets`. (`Home.js`.)

- **Usability:** Is the value prop clear in 5 seconds? Is the primary CTA the obvious next step, and does it work? Do the 6 feature cards over-promise?
- **UI convenience:** How many clicks/taps from landing to a usable study session? Is the wordset grid on the home page redundant with the CTA (two paths to the same place)?
- **Aesthetics:** Hero hierarchy, feature-card grid alignment on mobile (do 6 cards reflow sanely?), typography scale, whitespace.
- **Watch-for:** The **"Cultural Context"** card advertises **example sentences**. `ui/public/sentences/sentences.json` (served at `/sentences/sentences.json`) exists, but check whether **any route/component actually renders those sentences** — an *advertised-but-dead* feature is a genuine usability defect (high). Screenshot the card and note whether the promise is delivered anywhere in the live UI.

### Journey 2 — Guest access via "Try without signing in" (analytics-safe entry)

**Route/steps:** From `/wordsets` (or after clicking a wordset action) the `PrivateRoute` login card appears: **"Ready to Start Learning?"** with **"Try without signing in"** and **"Sign in with Google"**. Click **"Try without signing in"** (or the nav **"Try"** button). App creates a `<random>@lexitrail.demo` guest session and re-renders in place. **DO NOT click "Sign in with Google."** (`PrivateRoute.js`, `AuthContext.js`, `NavBar.js`.)

- **Usability:** Are the two choices clearly distinguished? Is it obvious what "Try without signing in" gives up (does guest progress persist? is that communicated)? Any confusion about which button is primary?
- **UI convenience:** Is guest mode discoverable (both the card button *and* the nav "Try")? After clicking, is the transition into the app obvious (no dead click)?
- **Aesthetics:** Login card layout, button styling/hierarchy, Google button consistency, spacing on mobile.
- **Watch-for:** This is the **anon→member acquisition path Alex prioritizes** and the **only analytics-safe way to reach a session**. Any friction here is high value. Confirm the guest session actually enters the app (not a silent no-op).

### Journey 3 — Pick a wordset & mode

**Route/steps:** At `/wordsets`, view the grid of tiles. Each tile shows a **description** and **4 buttons**: **"Practice"**, **"Due Today"**, **"Show Excluded"**, **"Test!"**. Click **"Practice"** on HSK1 → `/game/1/PRACTICE` (or `/game/1`). (`Wordsets.js`, `wordsService.js`.)

- **Usability:** Four similar buttons per tile — is the primary action ("Practice") obvious, or do all four compete? Would a new user know what "Due Today" vs "Practice" means?
- **UI convenience:** Clicks-to-goal to start studying; do the mode buttons route correctly (verify each mode lands on the right `/game/1/<MODE>` and correct screen)?
- **Aesthetics:** Tile grid alignment/consistency, button crowding, description legibility, mobile reflow of a 4-button row.
- **Watch-for:** Wordset descriptions carry a **trailing carriage return** from CSV import (e.g. `"HSK1\r"`). The hide-filter trims for matching, but the tile renders `wordset.description` **raw** — watch for trailing-whitespace / stray-line rendering artifacts and screenshot any.

### Journey 4 — Practice / study flashcards (THE core task)

**Route/steps:** At `/game/1/PRACTICE`, first dismiss the **onboarding overlay** ("How it works" — `OnboardingOverlay.js`). A card shows the **hanzi (front)**. Tap/click to **flip** → back shows hanzi + **🔊 speaker** + **pinyin (tone-colored)** + **English**. Use the per-card **❌ (missed)** and **✔️ (correct)** buttons; the small **Exclude/Include** button (top-left of the card metadata) and the **red/green history tiles** (`.mastery-indicator`) beside it. Top bar: ❌ counter, **Show Hints**, **Flip all**, **Show Excluded**, timer, ✔️ counter. Bottom: **"✔️ to all N"** bulk button and a progress bar (**"recalled X out of Y"**). (`Game.js`, `WordCard.js`, `SpeakButton.js`, `MiniWordCard.js`, `OnboardingOverlay.js`.)

- **Usability:** Is the flip affordance obvious? Is the ❌/✔️ distinction clear? After marking a card, is there clear feedback? Is language content correct (**hanzi/pinyin/tone** — safety-critical; verify a few known words, e.g. HSK1 你好 → nǐ hǎo)?
- **UI convenience:** Card layout responsiveness — the dynamic grid (`updateLayout`) is the **prime mobile-vs-desktop divergence surface**; capture the *same* set on both viewports and compare columns/rows/card size. Do "Flip all", "Show Hints", and the "✔️ to all N" bulk action behave and give feedback?
- **Aesthetics:** Auto font-scaling (`calculateFontSize`) — flag inconsistent / tiny / oversized text. Tone-color contrast on pinyin. Card spacing, alignment of front vs back.
- **Watch-for (highest-value screen — most of Alex's bugs live here):**
  1. **Exclude/Include button too tiny to see** — `.exclude-button` in the metadata row (`red` when included = "exclude me", `green` when excluded = "include me"). Measure its tap target on mobile; flag if under-sized.
  2. **Mastery display** — must be **red/green per-answer history tiles** (`historyTiles.js` / `renderHistoryTiles`), NOT plain "Seen Nx, M correct" text. Verify tiles render, are legible, and read **newest-on-right**. Note: the tile row uses `flex-end + overflow:hidden`, so an over-wide row **clips the oldest (left) tile** — check whether history gets clipped.
  3. **Speaker placement** — 🔊 (`SpeakButton`) must render **only on the card BACK, next to the hanzi**. Verify placement/alignment; confirm it is *not* on the front.
  4. **MIC / record control** — Alex expects a **mic/record button right-aligned on the back card**. Verify whether it actually exists on the live back card and is right-aligned with a real (≥40px) tap target; if it is absent, flag it as **missing entirely** and note the intended right-alignment.
  5. **🔊 renders in BOTH headless and headed — do NOT misreport it as missing in headless.** `SpeakButton` calls `isSpeechSupported()`, which only checks that `window.speechSynthesis` **and** `window.SpeechSynthesisUtterance` *exist* — and both are present in Chromium **headed and headless** — so the 🔊 button **renders in both**. Only *audible playback* depends on OS-installed zh-CN voices (`getVoices()`), which the Linux test box usually lacks; going headed does **not** add voices. Treat **no sound on the test box as an environment limitation, not a shipped bug**, and do **NOT** file "control missing for real users" unless the 🔊 button is genuinely **absent from the live DOM** (it will not be, in Chromium). What you *are* verifying here is placement/alignment on the back card (see #3), not audibility.

### Journey 5 — Test / quiz mode

**Route/steps:** From a wordset tile click **"Test!"** → `/game/1/TEST`. Cards do **not** flip; each shows the hanzi with **4 multiple-choice pinyin option buttons** (limited to 20 words; words with special chars or `[quiz_word]` filtered out). Pick options; observe correct/incorrect feedback and progress. (`Game.js` `GameMode.TEST` + `WordCard.js` test-buttons branch.)

- **Usability:** Is it obvious this mode is a quiz (no flip)? Is correct/incorrect feedback clear and immediate? **Distractor quality is safety-critical** — verify the "correct" pinyin option is *actually* correct for the shown hanzi (a wrong "correct" answer teaches the wrong thing → S1).
- **UI convenience:** 4-option layout — do buttons fit/reflow on mobile? Is progress through the 20 words visible?
- **Aesthetics:** Option-button sizing/alignment (`cardHeight` is taller for TEST: 345 vs 280), consistency with Practice, contrast of the feedback state.
- **Watch-for:** Any incorrect pinyin/tone in the shown word or the options; distractors that are trivially wrong (too easy) or ambiguous.

### Journey 6 — Due Today (spaced-repetition queue)

**Route/steps:** From a tile click **"Due Today"** → `/game/1/DUE_TODAY`. Shows only *included* words whose SRS interval has elapsed (or never practiced). For a fresh guest, most/all words are "due", so it behaves like Practice; after marking words correct, re-entering should show fewer. (`ui/src/utils/srs.js` — `isDue`, `INTERVAL_DAYS [7,3,1,0,0]`; `useWordsetLoader` DUE_TODAY filter.)

- **Usability:** Is it clear *why* certain words appear (or don't)? After marking words correct, does re-entering Due Today show fewer (evidence the retention loop works)?
- **UI convenience:** **There is NO "all caught up" empty state.** In `Game.js` (~L310-320), an empty `displayWords` in any non-`SHOW_EXCLUDED` mode falls through to the **`<Completed/>` results screen** — so when nothing is due, the user is dropped onto a completion/results screen, not a purpose-built "nothing due today" state. Confirm what actually renders and judge whether that is clear/appropriate.
- **Aesthetics:** Same card surface as Practice — check consistency; and the `<Completed/>` screen's fit when it is reached via an empty Due Today queue.
- **Watch-for:** (a) Due Today and plain Practice **look identical** — a discoverability/orientation risk; flag whether the user can tell which mode they're in. (b) **File "nothing-due renders the `<Completed/>` results screen instead of a purpose-built empty state" as the finding** — do NOT hunt for "all caught up" copy that does not exist in the code. Capture whatever actually renders on both viewports.

### Journey 7 — Show Excluded (round-trip)

**Route/steps:** Click **"Show Excluded"** on a tile, or use the in-Practice **"Show Excluded"** toggle → `/game/1/SHOW_EXCLUDED`. With nothing excluded, expect the empty state **"No excluded words in this wordset."** (this is the *only* mode that renders dedicated empty-state copy). Then: in Practice, **exclude a word** (the tiny Exclude button), revisit Show Excluded to confirm it appears, and **"Include"** it back. (`Game.js` `SHOW_EXCLUDED` branch.)

- **Usability:** Is the exclude feature **reversible and discoverable**? Does the round-trip (exclude → view → include) actually work and give feedback?
- **UI convenience:** Toggle labeling (in `SHOW_EXCLUDED` the toggle reads "Show Included") — is it clear? Clicks to complete the round-trip.
- **Aesthetics:** Empty-state copy/layout polish.
- **Watch-for:** Ties back to the **tiny exclude button** (Journey 4). Confirm the empty-state copy renders and the include-back path works.

### Journey 8 — Completed / results screen

**Route/steps:** In Practice, mark every card correct (use **"✔️ to all N"** repeatedly) until the set empties. The **Completed** screen shows elapsed time, **% correct**, a **"Review missed words"** list (if any), a first-time-correct list, and **"Play again" / "Back to Word Sets" / "Share"** buttons. (`Completed.js`.)

- **Usability:** Are the stats accurate (cross-check % against what you marked)? Is the missed-words review useful and actionable?
- **UI convenience:** Do "Play again" and "Back to Word Sets" route correctly? Does **Share** (`navigator.share` / clipboard) degrade gracefully — on desktop it may fall back to "Copied result to clipboard!" — verify no dead button or error.
- **Aesthetics:** Results layout, stat prominence, button hierarchy, mobile fit.
- **Watch-for:** Share failing silently; inaccurate percentage; empty missed-list rendering awkwardly.

### Journey 9 — Static / legal pages + 404

**Route/steps:** Via the top-nav **"About"** dropdown open `/about`, `/privacy`, `/terms`. Then hit an unknown URL, e.g. `https://lexitrail.com/does-not-exist` → should render the **404** (`NotFound.js`: large "404" + **"Back to home"** link). (`About.js`, `PrivacyPolicy.js`, `TermsOfService.js`, `NotFound.js`.)

- **Usability:** Do all three static pages load with real content? Does the 404 clearly offer a way home?
- **UI convenience:** Does the About dropdown work on mobile (touch)? Does "Back to home" route to `/`?
- **Aesthetics:** Legal-page readability/typography; 404 page polish.
- **Watch-for:** An unknown route must resolve to the **404 page** — not a blank/broken screen (a prior defect per the `itp-bug2-notfound-route` branch). Confirm and screenshot.

### Journey 10 — Loading / error / empty resilience (cross-cutting)

**Route/steps:** On `/wordsets`, watch the initial load. It should reach a **grid** (or a cached grid); a failed/slow fetch must surface a **retryable error** with a **Retry** button, and a genuinely empty result must say so — never an endless spinner. (`resolveWordsetsView` → `grid` / `loading` / `error` / `empty`; `Wordsets.js` cache + Retry.) To exercise the error path safely, you may intercept the API in Playwright: `await context.route(/api\.lexitrail\.com\/wordsets/, r => r.abort())` before navigating, then reload and screenshot the error + click **Retry**.

- **Usability:** Does the error state explain what happened and offer recovery? Does Retry actually recover?
- **UI convenience:** No multi-minute hang (the root-caused bug: a `cacheKey` `ReferenceError` swallowed load errors; axios now has a **20s timeout**). Verify load resolves within a reasonable time and never spins forever.
- **Aesthetics:** Loading/empty/error states styled consistently, not raw/unstyled.
- **Watch-for:** Any spinner that never ends; Retry that doesn't retry; unstyled error text. Screenshot loading, empty, and error states.

---

## 4. Deliverable — the shareable screenshot gallery

Assemble **all** screenshots into **one self-contained HTML gallery with a live URL** so zz1 can relay it to Alex, who reviews shipped UI via screenshots (not by hand-testing). This deliverable is required — findings without the visual evidence page are not complete.

**Layout the gallery by journey, and within each journey show mobile and desktop side-by-side** (that is the whole point — Alex checks both form factors at a glance). Annotate each pair with the journey name and any finding IDs.

**Preferred host — the repo box's `:8099` static server:**

1. Write a single `index.html` that references (or inlines as data URIs) every screenshot, grouped by journey, mobile+desktop side-by-side, each captioned with screen · viewport · finding IDs.
2. Copy it plus the `screens/` folder into the directory the box serves on `:8099`, e.g. `.../lt-itp/YYYY-MM-DD/`.
3. Confirm it loads (curl the URL — the `:8099` static server can die undetected; if it's down, restart it), then record the **live URL**, e.g. `http://<bp-box>:8099/lt-itp/YYYY-MM-DD/index.html`.

**Fallback host — Google Drive:** if `:8099` is unavailable, upload the gallery (HTML + images, or a Google Doc with the images embedded) to Drive, set link-viewable, and record that URL instead.

Either way, **the gallery URL goes in the PR body** (§5) so zz1 can relay it. Note that agent-hosted artifact links can 404 for Alex if they're private to an account — prefer the `:8099`/Drive path above precisely so the link is reachable.

---

## 5. Filing results — findings table + PR handoff

Findings are a **handoff**: you file, the owning crew triages and fixes. **You do not edit product code** (`ui/src/**`, `backend/app/**`).

### 5.1 Findings table spec

Record every finding in a markdown table in the PR (and mirror it into `docs/itp-findings-YYYY-MM-DD.md`). One row per finding. **Every row must link a screenshot in the gallery.**

| # | Screen (journey) | Viewport | Lens | Severity | Issue | Suggested fix | Screenshot |
|---|---|---|---|---|---|---|---|
| 1 | Practice (J4) | mobile | Usability | S2 | Exclude button ~14px tap target, easy to miss/mistap | Enlarge `.exclude-button` hit area to ≥40px | [link] |
| 2 | Home (J1) | both | Usability | S2 | "Cultural Context" advertises example sentences; no view renders them | Hide the card or ship a sentences view | [link] |

- **Lens** = Usability / UI Convenience / Aesthetics.
- **Screen** = journey name + number.
- **Viewport** = mobile / desktop / both.
- **Suggested fix** is advisory — the crew decides. Where useful, add a repo pointer (file/component) but do **not** submit code changes.

### 5.2 Severity scale

- **S1 — Blocker:** core task impossible, data/language wrong (e.g. incorrect pinyin/tone, a quiz "correct" answer that is wrong), or a broken/blank screen.
- **S2 — Major:** significant friction, a dead-end, a missing/advertised feature, or an unusable control (e.g. tap target far too small).
- **S3 — Minor:** confusing but workable; missing feedback; empty/error state rough.
- **S4 — Polish:** spacing, alignment, typography, contrast, consistency nits.

Order the table **most-severe first**. Flag every **language-correctness** issue as **S1**.

### 5.3 PR handoff to the owning crew

1. On your `itp-*` branch (e.g. `itp-usability-pass-YYYY-MM-DD`) commit **only**: this doc (if new/updated), `docs/itp-findings-YYYY-MM-DD.md`, and the Playwright scaffolding under the new top-level **`e2e/`** folder — that is `e2e/package.json`, `e2e/package-lock.json`, `e2e/playwright.config.js`, and your driver script(s). These test-only files (including the `@playwright/test` devDependency + lockfile) are the accepted scaffolding. **Make NO changes to `ui/package.json`, `ui/package-lock.json`, `ui/src/**`, or `backend/app/**`** — Playwright lives only in `e2e/`, never in the product tree, so the tree stays clean and the PR is reproducible.
2. Open a PR to **`main`** of `AlexBulankou/lexitrail`. Title e.g. `ITP usability pass YYYY-MM-DD — findings + evidence`.
3. **PR body must contain:** the findings table (§5.1), the **live gallery URL** (§4), the viewports tested, the exact access path used (guest "Try" + analytics abort), the `analyticsBlocked` count proving the funnel stayed clean (§2.3), and a one-line summary count by severity.
4. Route to the **owning LT crew** for triage/fix: request review from the lexitrail lead/partner pair per the fleet's adversarial-collaboration model and apply the repo's usual label. The crew owns the fixes; your PR is the record + evidence. (This repo enforces PR + branch protection — no direct pushes.)
5. Do **not** self-merge fixes and do **not** fix product code yourself. Your PR carries the findings and the gallery; hand off.

---

## 6. Guardrails (read this before you touch anything)

- **READ-ONLY intent.** Observe and evidence; never perform destructive or irreversible actions. There is no destructive action in this app to trigger — keep it that way.
- **Analytics-safe, always.** Install the GA beacon **abort** route (regex form, §2.3) in `test.beforeEach` / a fixture so it applies to every fresh context, **before** the first navigation. Never use the broken bare-glob form. Never let a test session pollute the GA4 funnel; report the blocked-beacon count to prove it stayed clean.
- **Guest only.** Enter via **"Try without signing in"** / nav **"Try"**. **Never** complete a real Google sign-in; **never** attempt account deletion. Guest writes land only under `@lexitrail.demo` — acceptable but minimize them.
- **No real signup, no payment.** The app is free; there is nothing to pay for and no account to create. Do not create real accounts.
- **Never expose tokens/credentials.** There is nothing to handle here (the guest token is a throwaway `UNAUTH_USER:<random>@lexitrail.demo` string minted client-side), but as a rule: never paste, log, screenshot, or commit any token, credential, or `sessionStorage.access_token` value.
- **Test the LIVE deployed app.** `https://lexitrail.com`, in a real Chromium via Playwright. **No local dev server.** This ITP exists because the UI was not exercised in a browser before shipping.
- **Both viewports, every time.** Mobile **and** desktop for every journey and screen. A finding is scoped to a viewport.
- **Keep the product tree clean.** Playwright lives only in the top-level `e2e/` harness with its own `package.json`. No edits to `ui/package.json`, `ui/package-lock.json`, `ui/src/**`, or `backend/app/**`.
- **You don't fix.** File the findings PR + gallery and hand off to the LT crew.

---

## Appendix — pain-point index (high-value targets)

| # | Symptom | Where | Journey |
|---|---|---|---|
| 1 | Exclude/Include button too tiny | `.exclude-button` (WordCard.js / WordCard.css) | J4, J7 |
| 2 | Mastery must be red/green history tiles (not text), newest-on-right, not clipped | `historyTiles.js`, `.mastery-indicator` | J4 |
| 3 | 🔊 speaker only on card BACK next to hanzi | `SpeakButton.js` in WordCard back | J4 |
| 4 | MIC/record control expected right-aligned on back — verify it exists + ≥40px tap target | (WordCard back) | J4 |
| 5 | "Cultural Context" example sentences advertised — verify a view actually renders them | `ui/public/sentences/sentences.json` (served `/sentences/sentences.json`) | J1 |
| 6 | Multi-minute wordsets "loading" hang (root-caused) | `resolveWordsetsView`, `Wordsets.js`, axios 20s timeout | J3, J10 |
| 7 | Trailing `\r` in wordset descriptions rendered raw | `wordsService.js`, tile render | J3 |
| 8 | Dynamic card-grid layout differs sharply mobile vs desktop | `Game.js` `updateLayout` | J4, J5 |
| 9 | Auto font-scaling → tiny/huge/inconsistent text | `calculateFontSize` | J4 |
| 10 | 🔊 renders in headless AND headed (feature-detect only checks the API exists); only *audible* playback needs zh-CN voices — no-sound on the box is an env limit, NOT a bug | `SpeakButton.js` / `utils/speak.js` | J4 |
| 11 | Unknown route must hit 404, not blank | `NotFound.js`, `*` route | J9 |
| 12 | Quiz "correct" option must actually be correct (language-safety) | `Game.js` TEST branch | J5 |
| 13 | Nothing-due renders `<Completed/>`, not a purpose-built empty state | `Game.js` (~L310-320) | J6 |
