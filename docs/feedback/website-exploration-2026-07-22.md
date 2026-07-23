# Lexitrail Website Exploration — Round 3: Bugs & Ten Retention-Focused Redesign Proposals

**Date:** 2026-07-22
**Environment:** Production — https://lexitrail.com (API: https://api.lexitrail.com)
**Method:** Automated end-to-end Playwright (Chromium 149) walkthrough. Desktop (1440×900) and mobile (iPhone 13, 390×844 portrait + 844×390 landscape). Demo-mode login ("Try without signing in"), full pass through the levels (HSK wordsets), all four game modes (Practice, Test, Show Excluded, Due Today), and the AI hint system (auto-load, toggle, regenerate). Four scripted sessions with network/console JSONL recording and screenshots; **one** demo account minted (`2p164@lexitrail.demo`) and reused across sessions via token restore.
**Deployed build fingerprint:** `/static/js/main.07bdc1e4.js`, `/static/css/main.b3cc0693.css` — **identical to the 2026-07-19 and 2026-07-20 runs.**

This is a follow-up to `docs/feedback/website-exploration-2026-07.md` (PR #21) and `docs/feedback/website-exploration-2026-07-20.md` (PR #35). Per this round's brief, the deliverables are: **(1) ten redesign proposals that would dramatically improve user retention** — including experiences that significantly redesign current functionality (§4) — and **(2) a bug report from the same exploration** (§2–§3).

---

## 1. Deployment status: the fixes exist, the users still don't have them

The frontend bundle hash is unchanged for the third run in a row. Every UI-side fix merged to `main` since Round 1 — PRs #23–#34, covering BUG-1..4, SUG-1/2/3/5/6/7, the `/go/<shape>` redirects, and the FEAT-2 "Due Today" SRS queue — is **merged but not deployed**. Users still get the `bundle.js` `SyntaxError` on every page, the blank 404 page, debug internals on every card, auto-firing hint requests, no onboarding, and the thin Completed screen. `/game/1/DUE_TODAY` silently falls back to Practice (all 150 words) because the deployed bundle predates the mode.

**One genuine improvement observed (backend-side):** quiz distractor quality is much better than Round 2 measured. Only 4 of 450 HSK1 quiz options (≈1%) are non-corpus synthetic strings now (e.g. `一不东西喂飞`), and zero `[quiz_word]` placeholder options remain across all nine wordsets. The backend has evidently been updated since 07-20 even though the frontend has not.

**One correction to Round 2:** a `link[rel="canonical"]` *is* present at runtime — it is injected client-side by react-helmet. The raw served HTML still lacks it (which is what matters for non-JS crawlers), so PR #36 remains worthwhile, but the earlier "no canonical at all" claim was too strong.

The single highest-leverage engineering action remains unchanged since Round 2: **deploy `main`.**

---

## 2. New bugs found this round (R3-BUG-1 … R3-BUG-7)

### R3-BUG-1 (Critical) — Core API endpoints intermittently return 500 (~2% of calls)
Across three short sessions (~230 API calls in under an hour), four requests returned HTTP 500: `GET /userwords/query` twice (12:22:45 wordset 1; 12:30:16 wordset 8), `PUT /userwords/:user/:word/recall` once, and `GET /hint/generate_hint` once. Identical requests retried seconds later succeed (10/10 direct probes → 200, at a notably slow ~2.0–2.4 s each). A 2% failure rate on the endpoints that load the game and record every answer means a multi-minute session hits a failure almost every time. Combined with R3-BUG-2 and R3-BUG-3 below, these transient 500s turn into hard user-visible breakage.
**Suggested fix:** investigate backend/DB error logs for the 500s (they cluster on "cold" first calls — stale DB connection pool is a plausible culprit); add retry-with-backoff in `apiService` for idempotent GETs.

### R3-BUG-2 (Critical) — When the game fails to load, the error handler itself crashes, leaving an infinite "Loading..." screen — root-caused to a live `ReferenceError`
When `GET /userwords/query` 500s while opening a game, the app does **not** show its error screen. It hangs on the "Loading..." spinner forever with no retry affordance — captured twice this round on two different wordsets. Console evidence from production:

```
GET /userwords/query?user_id=2p164@lexitrail.demo&wordset_id=8  → 500
console.error: Error loading words or userword metadata: yt
pageerror:     ReferenceError: cacheKey is not defined
```

Root cause (present in the deployed bundle **and in current `main`**, `ui/src/hooks/useWordsetLoader.js`): `cacheKey` is declared inside the `try` block, but the `catch` block executes `userWordsetExcludedCache[cacheKey] = null;`. That line throws a `ReferenceError`, so the subsequent `setLoading({ status: 'error' })` never runs and the UI stays in `loading` state permanently. The only escape is a full page reload — which re-rolls the 2% dice.
**Suggested fix (two lines):** declare `includedFlag`/`cacheKey` before the `try`, and/or guard the cache cleanup; then the existing error screen renders. Worth adding a "Try again" button to that error screen at the same time.

### R3-BUG-3 (High) — Recall and exclusion writes are silently lost (fire-and-forget, no feedback, aborted on navigation)
Every answer is persisted via a fire-and-forget `PUT .../recall`. Two failure modes observed, both invisible to the user:
1. **Failed write, UI advances anyway.** The session's very first ✔️ produced `PUT .../52/recall → 500`; the card was marked memorized, progress advanced, no toast/retry/rollback. That recall never reached the server.
2. **Navigation aborts in-flight writes.** After "✔️ to all 16", reloading the page aborted **14 in-flight recall PUTs** (`net::ERR_ABORTED`) — including the exclusion PUT from an earlier card. Result verified server-side: the excluded word was *not* excluded ("Show Excluded" empty; included count back at 150). A separate controlled retest (exclude → wait for PUT 200 → check) confirmed exclusion round-trips correctly *when the write lands* — so the feature works, but the durability doesn't.

The product's core promise — "track your learning progress" — quietly fails under normal behavior (answer quickly, then navigate/close/reload).
**Suggested fix:** queue writes locally and flush with retry; use `keepalive`/`sendBeacon` (or the existing middle-layer path) for unload-safe delivery; surface failures ("1 answer not saved — retrying").

### R3-BUG-4 (High, mobile) — Landscape phone shows exactly ONE card; portrait HUD is pushed off-screen
On 844×390 landscape, Practice renders a single word card beside a large empty dark rail and a sea of gray (measured `cardCount: 1`). On 390-px portrait, the layout viewport is forced to 478 px (≈88 px horizontal overflow, matching Round 2's NEW-1): the ✔️ score counter sits entirely off-screen (measured x = 391→478), the timer is clipped, and the right card column is cut. Additionally, the per-card recall-history badges overlap the card header on small cards, and the "✔️ to all N" button was **untappable for 15+ seconds** (actionability blocked by cards reflowing as hint images stream in — Round 2's NEW-2, still live).
**Suggested fix:** PR #37 addresses the navbar/rail; the card-grid layout algorithm (`updateLayout` in `Game.js`) additionally needs a mobile-landscape branch (its row math yields ≤1 row at 390 px height) and reserved hint-image space so cards never reflow after mount.

### R3-BUG-5 (Medium) — "Hide Hints" doesn't stop hint generation traffic
With hints hidden, advancing to a new card still fires `GET /hint/generate_hint` (measured 1 request per new card while hidden). Across this round's three sessions, **114 hint requests** were issued, virtually none user-requested; Test mode also auto-loads a hint image for every quiz card (pure noise — often abstract swirls or "?" stock photos). The opt-in + caching fix (PR #30) is merged but undeployed; note it gates *rendering-time* fetches — worth re-verifying post-deploy that no hidden-state fetch path remains.
**Suggested fix:** deploy `main`; add a regression test that zero hint requests fire while hints are hidden.

### R3-BUG-6 (Low) — "Show Excluded" renders as a playable practice session
The excluded-words view shows a progress bar ("recalled 0 out of 1"), a running timer, and active ❌/✔️ recall buttons on excluded words — answers there write real recall records for words the user explicitly removed from practice. It also displays the same raw recall-history rows as practice cards.
**Suggested fix:** make Show Excluded a management list (word + meaning + "Include" button), not a game mode.

### R3-BUG-7 (Low, data quality) — Recall history rows carry `old_recall_state: null` and same-second bulk entries
`GET /userwords/query` returns history rows like `{"old_recall_state": null, "new_recall_state": 0, "recall": true}` (nullable where a number is expected downstream), and "✔️ to all" writes batches of identical same-second rows. Any future SRS scheduling built on this table inherits ambiguous transitions and blind-recall noise (see also NEW-7).
**Suggested fix:** backfill/derive `old_recall_state`; tag bulk-marked recalls (`source: "mark_all"`) so scheduling can discount them.

---

## 3. Status of previously reported issues (validated live this round)

| ID (round) | One-line | Status on prod 2026-07-22 |
|----|----|----|
| BUG-1 (R1) | Stale `bundle.js` tag → `SyntaxError` every load | **Still live** (fix merged #23, undeployed) |
| BUG-2 (R1) | Unknown routes render blank page | **Still live** (fix merged #24, undeployed) |
| BUG-3 (R1) | `\r` in wordset descriptions | **Still live**; now quantified corpus-wide: def2 carries `\r` on 293/300 HSK3, 590/600 HSK4, 1264/1300 HSK5, 2474/2500 HSK6 words (fix for the filter merged #25; data itself still dirty) |
| BUG-5 (R1) | Transient 503s on cold routes | Not reproduced (10/10 `GET /about` → 200) |
| SUG-1 (R1) | Raw recall internals on cards | **Still live** (fix merged #28, undeployed) |
| SUG-2 (R1) | Hint images eager + generic | **Still live** — 114 auto requests this round; images remain stock-photo generic (小 "small" → sunflower; 会 "can" → waterfall; 想 "think" → camera lens) (fix merged #30, undeployed) |
| SUG-3 (R1) | Fake distractors + mid-syllable wrapping | **Half-fixed server-side** (≈1% fake now); wrapping still live (`péngy/ǒu`, `diànn/ǎo`) (UI fix merged #29, undeployed) |
| SUG-4 (R1) | Test mode is char→pinyin only | **Still live** — and rendered as a 16-card wall, not question-by-question |
| SUG-5/6 (R1) | No onboarding; thin Completed screen | **Still live** (merged #33/#32, undeployed). Completed = `0:04 / 100% / character dump / Play again` |
| NEW-1/NEW-6 (R2) | Mobile overflow / empty rail eats ~30% width | **Still live**, re-measured (478-px layout viewport; rail 115 px = 29% of 390 px) (fix PR #37 open) |
| NEW-2 (R2) | Hint-load layout shift makes buttons untappable | **Still live** (markAll blocked 15 s+ on mobile) |
| NEW-3 (R2) | Demo identity per-tab; 2nd tab = logged out | **Still live** (second tab hit the sign-in wall; PR #38 open) |
| NEW-4 (R2) | Session = whole set; reload wipes progress | **Still live** (150-word HSK1 session; reload → counter 0, timer 0:00) |
| NEW-5 (R2) | Test never reveals answer/meaning | **Still live** (wrong answer → card instantly replaced) |
| NEW-7 (R2) | "✔️ to all" records blind recalls | **Still live** (0 → 17/149 recalled in seconds) |
| NEW-9 (R2) | No canonical; no service worker | **Corrected/partial**: canonical injected at runtime by react-helmet (absent in raw HTML — PR #36 open); still 0 service workers |
| FEAT-2 / Due Today (#34) | SRS queue | **Not deployed**; `/game/1/DUE_TODAY` silently runs full Practice |

Perf snapshot (desktop, cold): TTFB 217 ms, DOMContentLoaded 521 ms, load 738 ms, ~152 KB compressed transfer. Wordset census: HSK1 150, HSK2 150, HSK3 300, HSK4 600, HSK5 1300, HSK6 2500, HSK1+2+3 599 (+hidden `HSK7` 15, `test` 15).

---

## 4. Ten redesign proposals to dramatically improve retention (RD-1 … RD-10)

These deliberately go beyond bug fixes: each one redesigns a current experience (or adds a new one) around a retention mechanism, and each is grounded in a concrete failure observed this round.

### RD-1 — "The Trail": turn the wordsets menu into a progression map
**Observed:** the wordsets page is seven identical gray tiles with four unexplained buttons each; it looks exactly the same on day 1 and day 100, and a "level" is an undifferentiated wall of 150–2,500 words.
**Redesign:** the product is named Lexi*trail* — make the home surface literally a trail. Each HSK level becomes a winding path of bite-sized **stops** (10–15 words each: "Greetings", "Numbers", "Food"). Each stop shows its mastery ring; completing a stop unlocks the next; a level-boss "checkpoint quiz" gates the next HSK level (visible but locked). The page becomes a visual record of the journey with exactly one primary CTA: **Continue →** (your current stop).
**Why retention:** visible position + locked-but-visible content + a single obvious next action is the strongest habit scaffold in learning apps; half-finished rings beg to be completed. Today the product offers zero visible accumulation (§3 SUG-1/NEW-4).
**Scope:** UI restructure of `Wordsets` + a wordset→units decomposition (backend table or static grouping); mastery per unit derivable from existing `recall_state`.

### RD-2 — Finishable micro-sessions with a round summary
**Observed:** a Practice "session" is the entire set — "recalled 0 out of 150" (599 for HSK1+2+3); the only reward screen sits behind grinding all of it in one sitting; reload resets the counter and timer to zero; a 5-minute mobile session can never finish anything.
**Redesign:** deal Practice in **rounds of ~12 cards** (one screen). Every round ends in a summary: accuracy, words leveled up, streak tick, "next round" / "stop here" — both of which feel like completion. Session state checkpoints server-side, so reload/return resumes mid-round ("Welcome back — 4 cards left in this round").
**Why retention:** the current design punishes exactly the short sessions that build daily habits. Reachable endings convert "I gave up mid-grind" (a loss) into "I finished two rounds" (a win) — and the summary screen is the natural home for streaks, goals, and share moments (RD-3, RD-10).
**Scope:** slice `toShow` into rounds in `useWordsetLoader`; new RoundSummary component; small session-state API.

### RD-3 — A "Today" home: due queue, streak, and daily goal as the front door
**Observed:** the logged-in landing page is a static set menu. Nothing expires, nothing accrues, nothing asks the user to come back; the merged Due-Today queue (#34) is undeployed and, even in `main`, it's a fourth gray button on a tile.
**Redesign:** replace the logged-in landing with a **Today screen**: "🔥 6-day streak · 14 words due · goal 20/30" and one big **Start (≈3 min)** button that drains the SRS due queue as micro-rounds (RD-2). Add a calendar heat-map of practice days, a configurable daily goal, and (later) push/email nudges when the streak is at risk ("12 words due — 3 minutes to keep your streak"). Word-of-the-day card for anonymous visitors.
**Why retention:** this is the daily-loop trifecta (expiring work + loss-aversion streak + tiny goal) that turns learning products into habits; the app currently has literally none of it live.
**Scope:** deploy #34, land #41 (streaks), new Today screen composing existing due-count + streak data; notifications later.

### RD-4 — Audio-first Mandarin: TTS everywhere and a listening mode
**Observed:** a *tonal-language* learning product with **zero audio anywhere** — no pronunciation on cards, quizzes, or completions (tone information exists only as colored pinyin letters).
**Redesign:** speak every word on flip and on quiz-answer reveal (Web Speech API / pre-generated TTS; PR #39 is an open start). Then add two new drill types to the quiz engine (RD-7): **listening recall** (hear the word → pick the character) and **tone drill** (hear a syllable → pick the tone). Auto-play toggle for hands-free review ("podcast mode" for a commute).
**Why retention:** audio makes every existing rep more valuable (multi-modal encoding), unlocks eyes-free usage contexts (commute = the daily slot), and is a differentiator users mention when a product actually pronounces the words they're memorizing.
**Scope:** TTS button + auto-play (#39), audio quiz formats, tone-drill component.

### RD-5 — Replace stock-photo hints with real word depth (mnemonics, breakdowns, sentences)
**Observed:** the "AI Memory Hints" are generic stock-style photos with weak connection to the word (小 "small" → a sunflower; 会 "can" → a waterfall; 想 "think" → a camera lens; question-marks for 哪儿/怎么) — 114 of them auto-fetched per hour of use. Meanwhile the homepage *sells* "clever memory aids and etymology explanations", "example sentences and usage notes", and the repo already contains a `sentences/` generation module — none of it in the product.
**Redesign:** rebuild the hint layer as a **word-depth panel**: character decomposition + a one-line mnemonic (the homepage's 记忆 demo is exactly the right format), an example sentence with pinyin + translation, and TTS (RD-4). Images become optional decoration, generated only on demand. Every word anywhere (card, missed-word rail, quiz reveal, Completed list) taps through to this word detail view.
**Why retention:** content depth is why a learner *explores* between drills instead of leaving; mnemonic + sentence is what actually makes a word stick, so users experience faster progress — the core retention driver for a learning tool. It also closes the trust-damaging gap between the marketing and the product.
**Scope:** hint API v2 (text mnemonic + breakdown), wire `sentences/` output (#40 open), word-detail route/panel.

### RD-6 — An honest, visible mastery system (and retire blind "✔️ to all")
**Observed:** cards expose raw internals (red/green `recall_state` numbers, `0 → 0` history rows) that mean nothing to a learner; per-set progress is invisible; and one tap of "✔️ to all 16" marks a whole screen memorized sight-unseen (this round: 0→17 "recalled" in seconds; Round 2: a 99% score in 36 s) — poisoning the very data an SRS needs (see also R3-BUG-7).
**Redesign:** per-word mastery pipeline — **New → Learning → Reviewing → Mastered** — shown as a small chip on cards and aggregated everywhere: per-stop rings (RD-1), a per-level progress bar, and a stats page (words known, accuracy trend, minutes practiced, forecast "words due this week"). Replace "✔️ to all" with **"I already know these"**: it flips cards face-up first, requires one confirmation, schedules the batch for a verification quiz tomorrow, and never writes ordinary recalls.
**Why retention:** a trustworthy "you know 37 of 150" number is the product's core progress asset — the thing users come back to grow. Today it doesn't exist, and the one number shown can be hollowed out with one button.
**Scope:** mastery mapping from `recall_state` (#28 merged is step one), stats page, mark-all redesign.

### RD-7 — Rebuild Test mode as an adaptive quiz engine with answer reveals
**Observed:** "Test!" renders **all 16–20 questions simultaneously** as a grid of cards; every question is the same format (character → pick pinyin); options wrap mid-syllable (`péngy/ǒu`, `diànn/ǎo`); a wrong answer instantly swaps the card with **no reveal of the correct answer and no meaning shown anywhere in the mode** — zero learning from mistakes.
**Redesign:** one question at a time, mixed formats chosen adaptively per word's mastery (char→meaning, meaning→char, char→pinyin, audio→char (RD-4), typed pinyin). Every answer gets a 1.5-s reveal: correct answer highlighted, meaning + sentence + audio, tap-to-continue. Missed words re-queue within the quiz and land in tomorrow's due pile; the quiz ends with a review list and a score that feeds the checkpoint gates (RD-1).
**Why retention:** quizzes are the product's feedback loop; today they're a wall of identical multiple choice that teaches nothing on failure. Variety + immediate feedback is what makes "one more round" feel worthwhile.
**Scope:** new quiz flow in `Game.js`/`WordCard.js` (single-question state machine), format components, distractor API already improved server-side.

### RD-8 — First-run redesign: placement, a guided first round, and "save your progress" account merge
**Observed:** a new user faces seven HSK tiles with no idea where to start, then a 16-card grid of unexplained controls (the merged onboarding overlay #33 is undeployed); the demo identity lives in one tab's sessionStorage — a second tab shows a sign-in wall (verified again this round), and closing the browser orphans the account and all progress.
**Redesign:** first visit → a 60-second **placement quiz** ("Do you know these 8 words?") that recommends a starting stop on the trail; the first round is 5 cards with inline coach marks on flip/✔️/❌. At the first round-summary — the moment the user has something to lose — prompt **"Sign in with Google to keep these 12 words"** and merge the demo account server-side (PR #38's anon→member migration is the foundation). Demo identity moves to durable storage so tabs/restarts don't wipe it (Round 2's NEW-3).
**Why retention:** most retention is decided in session one; today's first session opens with confusion and ends with disposable progress. Placement + guided start + a perfectly-timed conversion moment turns visitors into accounts with an endowment to protect.
**Scope:** placement flow, coach marks (#33 as base), demo persistence + merge API (#38).

### RD-9 — Reliability & offline-first foundation: a local write queue and an installable PWA
**Observed:** this round's most damaging technical findings — 2% API 500s (R3-BUG-1), an infinite-loading crash on failure (R3-BUG-2), and answers silently lost to failed or navigation-aborted writes (R3-BUG-3) — plus a manifest with no service worker (0 registered).
**Redesign:** treat progress durability as a product feature. All recalls/exclusions go through a **local outbox** (IndexedDB): optimistic UI, background flush with retry/backoff, `sendBeacon` on unload, visible sync state ("all changes saved"). Add the service worker to make Lexitrail an installable PWA that can **review cached due-words offline** (perfect for flights/subways) and later carry push reminders (RD-3).
**Why retention:** users who catch a product losing their progress rarely give it a second week — and offline + home-screen install directly widens the daily-use contexts the habit loop (RD-3) depends on.
**Scope:** outbox in `apiService`/`useWordsetLoader`, service worker + caching, install prompt; fixes R3-BUG-2/3 at the root.

### RD-10 — Social & ownership: custom decks, shared trails, and friend duels
**Observed:** the homepage promises "Create and organize Chinese vocabulary lists" — the product has no create flow, no way to share anything, no leaderboard, no evidence any other human uses it. The Completed screen's only CTA is "Play again".
**Redesign:** three increments. (1) **Custom decks:** paste/import words (CSV/text) → auto-enriched with pinyin, meaning, sentences, audio; private by default. (2) **Shared trails:** publish a deck as a link anyone can study (`lexitrail.com/deck/hsk1-food`) — teachers and classmates become the growth loop, and the existing `/go/<shape>` UTM infra (#27) measures it. (3) **Duels & leagues:** challenge a friend to the same 10-word quiz (RD-7) via link; weekly league among people you've dueled; round summaries (RD-2) get a share card ("I mastered 12 words today — beat my 94%?").
**Why retention:** external accountability (a teacher's deck, a friend's challenge) retains users through the motivation dips that streaks alone can't cover, and every shared artifact doubles as acquisition.
**Scope:** deck CRUD + enrichment pipeline (backend), share routes, duel = seeded quiz + result compare; ship in the numbered order.

**Sequencing note:** RD-9 and the §2 fixes are the foundation (progress must be trustworthy before it's worth gamifying); RD-1/2/3 form the core loop; RD-4/5/6/7 deepen it; RD-8/10 grow it.

---

## 5. Quick-reference summary

| ID | Type | Severity | One-line |
|----|------|----------|----------|
| R3-BUG-1 | Bug (backend) | Critical | ~2% of core API calls (query/recall/hint) intermittently return 500 |
| R3-BUG-2 | Bug (frontend, also in `main`) | Critical | `catch` references try-scoped `cacheKey` → `ReferenceError` → infinite "Loading..." with no retry |
| R3-BUG-3 | Bug (frontend) | High | Recall/exclusion writes silently lost: failed PUTs don't roll back UI; reload aborts in-flight writes (14 aborted after "✔️ to all") |
| R3-BUG-4 | Bug (mobile) | High | Landscape shows exactly 1 card; portrait HUD off-screen (478-px layout viewport); mark-all untappable 15 s+ |
| R3-BUG-5 | Bug (frontend) | Medium | "Hide Hints" doesn't stop hint generation; 114 involuntary hint requests/round; Test mode auto-loads hint images too |
| R3-BUG-6 | UX/data | Low | "Show Excluded" is a playable game that records recalls on excluded words |
| R3-BUG-7 | Data quality | Low | `old_recall_state: null` history rows; same-second bulk recalls pollute SRS data |
| §1 | Deployment | Critical | Third consecutive round on bundle `main.07bdc1e4.js`; merged fixes #23–#34 unreleased; backend distractors did improve |
| §3 | Validation | — | BUG-1/2/3, SUG-1..6, NEW-1..7 all still live on prod; BUG-5 not reproduced; NEW-9 canonical claim corrected |
| RD-1..RD-10 | Redesign proposals | — | Trail map · micro-sessions · Today screen · audio-first · word depth · honest mastery · adaptive quizzes · first-run/placement/merge · offline-first reliability · social decks & duels |

**Evidence appendix (this round):** 4 scripted sessions; ~230 API calls logged (4× HTTP 500); 114 hint requests; 1 demo account (`2p164@lexitrail.demo`); ~40 screenshots (desktop/mobile/landscape) and JSONL network+console logs captured for every claim above. Key artifacts: infinite-loading screen after query 500 (twice), aborted recall PUT storm after reload, one-card landscape practice, off-screen ✔️ counter on portrait, syllable-broken quiz options, stock-photo hints, `0:04 / 100%` Completed screen.
