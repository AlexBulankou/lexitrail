# Lexitrail Website Exploration — Feedback, Bugs & Feature Ideas

**Date:** 2026-07-19
**Environment:** Production — https://lexitrail.com (API: https://api.lexitrail.com)
**Method:** Automated browser walkthrough with Playwright (Chromium), desktop (1440×900) and mobile (390×844) viewports. Explored first anonymously, then with a demo ("Try") account.
**Deployed build fingerprint:** `/static/js/main.07bdc1e4.js`, `/static/css/main.b3cc0693.css`

This document is a structured record of what was tested, the bugs found, smaller improvement suggestions, and a set of feature proposals aimed specifically at increasing returning users. It is intended as a discussion starter — nothing here is a code change to the app itself.

---

## 1. What was explored

**Anonymous:**
- Home page (`/`) — hero, HSK word-set tiles, feature cards, CTA
- Private route gating (`/wordsets`, `/game/:id/:mode` while logged out)
- `/about`, `/privacy`, `/terms`
- Unknown route (`/this-route-does-not-exist`)
- Navigation bar (About dropdown, Try, Sign in) and mobile layout

**Demo account (via "Try"):**
- Account creation flow and navbar identity display
- Word Sets grid
- Practice mode (HSK1): card flip, ✔️/❌ recall, hint images, Hide Hints, Flip all, Exclude, Show Excluded
- Test mode (HSK1): multiple-choice quiz
- Show Excluded mode
- Session persistence on reload and logout

**Observed backend traffic (one short demo session):** `GET /wordsets` (200), `POST /users` (201), `GET /wordsets/:id/words` (200), `GET /userwords/query` (200), `PUT /userwords/:email/:id/recall` (200), and **37×** `GET /hint/generate_hint` (200).

---

## 2. Bugs

### BUG-1 (High) — Broken `bundle.js` script tag throws a JS error on every page load
Every page load produces an uncaught `SyntaxError: Unexpected token '<'` in the console.

Root cause: `ui/public/index.html` ends with a hardcoded script tag:

```html
<script src="%PUBLIC_URL%/static/js/bundle.js"></script>
```

The Create React App production build does **not** emit `bundle.js` (it emits a hashed `main.<hash>.js`, which is injected automatically). In production, `/static/js/bundle.js` does not exist, so the SPA fallback returns `index.html` with `Content-Type: text/html`. The browser then tries to execute HTML as JavaScript and fails.

Verified live:
- `GET /static/js/bundle.js` → `200`, `content-type: text/html`, body begins with `<!doctype html>`.
- The correct bundle `GET /static/js/main.07bdc1e4.js` → `200`, `application/javascript` (270 KB).

**Impact:** The app still renders (the real bundle loads via the auto-injected tag), but there is a guaranteed console error on 100% of loads, a wasted network round-trip, and noise that hides real errors during debugging.

**Suggested fix:** Remove the stale `<script src="%PUBLIC_URL%/static/js/bundle.js"></script>` line from `ui/public/index.html`. CRA injects the correct hashed bundle on its own.

### BUG-2 (Medium) — No catch-all / 404 route; unknown URLs render a blank page
Visiting any unmatched client route (e.g. `/this-route-does-not-exist`) renders only the navbar over an empty gray page — no "not found" message and no redirect. The router in `ui/src/App.js` has no `path="*"` fallback.

**Impact:** Dead-end for mistyped URLs, stale bookmarks, or old shared links. Looks broken.

**Suggested fix:** Add a catch-all route that redirects to `/` or renders a friendly NotFound component with a link back home.

### BUG-3 (Medium) — Word-set descriptions contain trailing carriage returns; test/HSK7 hidden via a fragile string match
The API returns descriptions with a trailing `\r`, e.g. `"HSK1\r"`, `"HSK2\r"`, … (visible in the raw `GET /wordsets` payload). This originates from CSV data with `\r\n` line endings that isn't stripped on import.

`ui/src/services/wordsService.js` hides internal word sets by matching those exact dirty strings:

```js
response.data = response.data.filter(
  wordset => wordset.description !== 'test' && wordset.description !== 'HSK7\r'
);
```

**Impact:**
- The filter is brittle: if the data were ever cleaned (`\r` removed) or re-labeled, the `test` and `HSK7` word sets would immediately leak into the production UI.
- Trailing `\r` risks subtle rendering/layout and analytics-labeling bugs elsewhere.

**Suggested fix:** Strip whitespace/`\r` from descriptions at import time (backend `dbupdate`/CSV parsing) and/or normalize in `to_dict`. Replace the hardcoded description filter with an explicit "published/visible" flag on the word set, or filter by a stable ID/attribute rather than a display string.

### BUG-4 (Low) — Duplicate, divergent auth implementations
There are two separate auth sources: `ui/src/hooks/useAuth.js` and `ui/src/contexts/AuthContext.js`. Both define `useAuth`, `login`, `logOut`, and `tryWithoutSignin`, but they hold **independent** state.
- `App.js` reads `user` from `hooks/useAuth` and passes it to `<NavBar>` as props.
- `NavBar.js` and `PrivateRoute.js` ignore those props and read from `AuthContext` instead.

**Impact:** The `hooks/useAuth.js` copy is effectively dead code that can desync from the context and mislead future contributors (a change made in one place silently has no effect). It's a latent source of "logged in here but not there" bugs.

**Suggested fix:** Delete `hooks/useAuth.js`, import `useAuth` from `contexts/AuthContext` everywhere, and stop passing auth props into `NavBar`.

### BUG-5 (Low, transient) — Occasional `503` on cold routes
One `GET /about` returned `503` during the run; immediate retries (10×) all returned `200`. Consistent with a backend/pod cold start or a brief health-check gap rather than a persistent fault.

**Impact:** Rare first-hit failures for users arriving on a cold instance.

**Suggested fix:** Confirm readiness probes and min-replica/warm-pool settings so the first request after idle doesn't 503; consider a lightweight keep-warm ping.

---

## 3. UX / content improvement suggestions

### SUG-1 — Practice cards expose developer/debug metadata to learners
Each practice card shows an `Exclude`/`Include` button, a colored numeric "recall state" box, and a full recall-history row rendered as `time • ✅/❌ • 0 → 0 • 🔄`. This is internal spaced-repetition bookkeeping, presented raw. For a first-time learner it is visual noise with no explanation, and it crowds the actual word. On the mini "excluded" card the metadata row even overflows the card width.

**Suggestion:** Hide raw recall-state internals behind an optional "details"/advanced toggle, or replace with a simple, human-readable mastery indicator (e.g. a small progress ring or "seen 3×, 2 correct"). Keep the card focused on the word + answer.

### SUG-2 — AI hint images are generic and often unrelated to the word
The AI "memory hint" images frequently look like generic stock photography with no obvious link to the word: 对不起 ("sorry") shows a flower; 医院 ("hospital") shows a dark building; 点 ("dot/point") shows a water droplet; 桌子 ("table") shows a wood grain. The home page markets "clever memory aids and etymology explanations," but the delivered hints rarely explain the character or aid recall.

**Suggestion:** Either raise hint quality (tie the image to the character's meaning/etymology, or pair it with the text mnemonic the marketing promises) or make hints opt-in so they don't slow down the card grid. Consider caching/generating hints ahead of time — one short session issued 37 hint requests.

### SUG-3 — Test mode contains nonsensical concatenated distractor options
In Test mode, the multiple-choice distractors are sometimes machine-concatenated pseudo-words (e.g. options like "wǒmen diànnǎo", "shéi shàng", "dàshǎo diànnǎo") that are not real words. They also wrap awkwardly inside the option buttons ("dǎdiànhuà", "chūzūchē"). This comes from the backend `generate_quiz_options` fallback that concatenates syllables when the same-syllable pool is too small.

**Suggestion:** Prefer real words of matching syllable length as distractors (pull from the full corpus / other HSK levels), and only fall back to synthetic options when truly necessary. Fix button typography so multi-syllable pinyin doesn't wrap mid-word.

### SUG-4 — Test mode only asks character → pinyin
The quiz always shows the Chinese character and asks the learner to pick the pinyin. There is no meaning-based recall (character → English, English → character, or audio → character).

**Suggestion:** Add question-type variety (see FEAT-4). Even alternating character→pinyin and character→meaning would meaningfully improve learning value.

### SUG-5 — No onboarding / first-run explanation
Clicking Practice drops the user straight into a 16-card grid full of buttons (✔️, ❌, Exclude, recall-state, 🔄, Flip all, Hide Hints) with no explanation of what they do or what "recall state" means.

**Suggestion:** Add a short first-run coach-mark overlay or a one-card guided intro explaining flip, ✔️/❌, and exclude.

### SUG-6 — Completed screen and in-game navigation are thin
The Completed screen (`Completed.js`) offers only "Play again." There is no "choose another word set," no share, and no way to review missed words with their meanings.

**Suggestion:** Add "Back to Word Sets," a "review missed words" list with meanings, and a share/streak prompt.

### SUG-7 — Minor accessibility/polish
- Recall state and correct/incorrect are communicated with red/green color only; add a shape/label for color-blind users.
- Word-set tiles use custom `<div>`/`<button>` groupings; ensure each tile has an accessible name that includes the set (e.g. "Practice HSK1") rather than just "Practice."
- `<html lang="en">` is fixed even though primary content is Chinese vocabulary; ensure Chinese text nodes are marked `lang="zh"` for screen readers and correct font rendering.

---

## 4. Feature proposals to increase returning users

These are prioritized for retention (bringing users *back*), not just first-session experience. Rough ordering is by expected retention impact vs. build cost.

### FEAT-1 — Daily streaks + daily goal + reminders
Add a visible streak counter, a configurable daily goal (e.g. "20 cards/day"), and optional email/push/PWA reminders when the streak is at risk. Streaks are the single most proven driver of daily return in language apps (Duolingo-style). The app already tracks per-word recall events, so a daily "cards reviewed" tally and streak are a natural extension.
- *Why it helps retention:* creates a daily habit loop and loss-aversion pressure to come back.
- *Build notes:* needs a per-user daily activity aggregate (backend) + a streak widget (navbar/home) + reminder plumbing (the PWA manifest already exists for install/notifications).

### FEAT-2 — True spaced-repetition scheduling with a "Due today" queue
The app already stores a `recall_state` per word, but the home/word-set view doesn't surface *what is due*. Turn the recall state into an SRS schedule (SM-2/Leitner-style intervals) and add a prominent "Review N words due today" button that assembles a cross–word-set queue.
- *Why it helps retention:* gives users a concrete, finite daily reason to return ("12 words are due"), and improves learning outcomes so they feel progress.
- *Build notes:* add `next_review_at` to user-word records; a scheduler endpoint that returns due items; a "Due today" entry point on `/wordsets`.

### FEAT-3 — Audio pronunciation (TTS) for every word
There is currently no audio anywhere — a significant gap for a Mandarin app where tones are central. Add a tap-to-play pronunciation on each card (and auto-play option), using pre-generated audio or a TTS service.
- *Why it helps retention:* pronunciation/listening is a core reason learners choose (and stick with) a Chinese app; its absence pushes users to competitors.
- *Build notes:* generate/cache per-word audio (Cloud TTS) keyed by word ID; add a speaker button to `WordCard`. Pairs well with FEAT-4 listening questions.

### FEAT-4 — Multiple quiz/practice modes (typing, listening, meaning, tone)
Expand beyond flip-cards and character→pinyin. Add: English→character, character→meaning, audio→character (listening), pinyin/character typing input, and a dedicated tone-drill. Let users pick a mode per session.
- *Why it helps retention:* variety fights boredom and covers different skills, giving multiple reasons to return; typing/listening modes deepen mastery so users progress faster.
- *Build notes:* mostly frontend variations on the existing card + the improved distractor logic from SUG-3; typing mode needs answer normalization.

### FEAT-5 — Persistent progress dashboard & achievements
Add a per-user dashboard: words mastered, accuracy over time, time studied, per-HSK-level completion bars, and unlockable badges/milestones (e.g. "Finished HSK1," "100-word streak"). The `/privacy` page already states the app stores game statistics — surface them.
- *Why it helps retention:* visible progress and milestones are strong intrinsic motivators to keep coming back; badges create collection goals.
- *Build notes:* aggregate existing recall history into per-user stats endpoints; a new `/progress` route.

### FEAT-6 — Convert demo ("Try") progress into a real account
Today "Try" mints a random `xxxxx@lexitrail.demo` identity stored only in `sessionStorage`. Progress is lost when the tab/session closes, and signing in with Google starts a fresh account — so a curious first-timer's work evaporates. Offer "Sign in to save your progress" that migrates the demo user's word history to the Google account.
- *Why it helps retention:* the moment a user invests effort is the best moment to convert them to a persistent, re-engageable account; losing progress guarantees they don't return.
- *Build notes:* a backend "merge/claim demo user" operation keyed on the demo email + new Google email; a prompt after N cards.

### FEAT-7 — Custom & community word sets
Let users create their own word sets (paste a list, import CSV, or save words they struggle with into a "My hard words" set), and optionally browse sets shared by others. The home page already advertises "Create and organize Chinese vocabulary lists," but there is no create flow in the UI.
- *Why it helps retention:* personal/relevant content (exam prep, textbook chapters, a trip) gives users a reason to return that generic HSK lists don't; user-generated content compounds over time.
- *Build notes:* CRUD for user word sets (backend models for words/word-sets already exist); an editor UI; an auto-generated "words I miss most" set from recall history.

### FEAT-8 — Leaderboards / friends / weekly challenges (light social layer)
Add optional weekly XP leaderboards among friends (invite by link) or global leagues, and time-boxed challenges ("learn 50 new words this week").
- *Why it helps retention:* social accountability and competition are proven weekly-return drivers.
- *Build notes:* weekly XP aggregate per user; a leaderboard endpoint; friend/invite linking. Can reuse the daily-activity data from FEAT-1.

### FEAT-9 — Example sentences & cultural usage (deliver on the marketing promise)
The home page promotes "Cultural Context" and example sentences, but cards show only word + pinyin + short gloss. Add 1–2 example sentences per word (with pinyin + translation, and audio via FEAT-3), plus common collocations.
- *Why it helps retention:* richer content makes each word worth revisiting and supports reading practice, deepening engagement beyond rote flashcards.
- *Build notes:* the repo already has a `sentences/` module — surface that data per word on the card back or a "details" expander.

### FEAT-10 — Installable PWA with offline review + web-push reminders
A `manifest.json` already exists. Complete the PWA story: add a service worker for offline flashcard review (cache word sets already studied) and web-push notifications for streak/daily reminders (ties into FEAT-1).
- *Why it helps retention:* an installed icon on the home screen + push reminders dramatically increases repeat sessions vs. a bookmark; offline review captures commute/idle time.
- *Build notes:* add service worker + caching strategy; wire web-push (VAPID) to the reminder scheduler.

---

## 5. Quick-reference summary

| ID | Type | Severity/Impact | One-line |
|----|------|-----------------|----------|
| BUG-1 | Bug | High | Stale `bundle.js` tag → JS parse error on every page load |
| BUG-2 | Bug | Medium | No 404/catch-all route; unknown URLs render blank |
| BUG-3 | Bug | Medium | Word-set descriptions carry trailing `\r`; test/HSK7 hidden by fragile string match |
| BUG-4 | Bug | Low | Duplicate/divergent auth (`hooks/useAuth` vs `AuthContext`) |
| BUG-5 | Bug | Low/transient | Occasional `503` on cold routes |
| SUG-1 | UX | — | Debug recall metadata shown to learners |
| SUG-2 | UX | — | AI hint images generic/unrelated |
| SUG-3 | UX | — | Nonsensical concatenated quiz distractors |
| SUG-4 | UX | — | Test mode is character→pinyin only |
| SUG-5 | UX | — | No onboarding/first-run guidance |
| SUG-6 | UX | — | Thin Completed screen & in-game nav |
| SUG-7 | UX | — | Accessibility polish (color-only cues, labels, `lang`) |
| FEAT-1 | Feature | Retention | Daily streaks + goal + reminders |
| FEAT-2 | Feature | Retention | SRS "Due today" queue |
| FEAT-3 | Feature | Retention | Audio pronunciation (TTS) |
| FEAT-4 | Feature | Retention | Multiple quiz/practice modes |
| FEAT-5 | Feature | Retention | Progress dashboard & achievements |
| FEAT-6 | Feature | Retention | Convert demo progress to real account |
| FEAT-7 | Feature | Retention | Custom & community word sets |
| FEAT-8 | Feature | Retention | Leaderboards/friends/weekly challenges |
| FEAT-9 | Feature | Retention | Example sentences & cultural usage |
| FEAT-10 | Feature | Retention | Installable PWA + offline + push |
