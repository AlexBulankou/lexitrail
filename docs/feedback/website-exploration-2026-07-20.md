# Lexitrail Website Exploration — Round 2: Fix Validation, New Bugs & Engagement Review

**Date:** 2026-07-20
**Environment:** Production — https://lexitrail.com (API: https://api.lexitrail.com)
**Method:** Automated browser walkthrough with Playwright (Chromium), desktop (1440×900), mobile (iPhone 13, 390×844 portrait + landscape). Anonymous first, then demo ("Try") accounts. Six scripted phases: fix validation, desktop demo walkthrough, mobile demo walkthrough, cross-cutting checks (multi-tab, PWA, perf, data), focused repros, hit-testing probes.
**Deployed build fingerprint:** `/static/js/main.07bdc1e4.js`, `/static/css/main.b3cc0693.css` — **identical to the 2026-07-19 run.**

This is a follow-up to `docs/feedback/website-exploration-2026-07.md` from [PR #21](https://github.com/AlexBulankou/lexitrail/pull/21) (that file lives on PR #21's branch, not yet on `main`). It (1) validates what was fixed since yesterday, (2) reports new bugs found today, (3) gives a top-10 diagnosis of why engagement/retention is low, and (4) proposes what would make the product more interesting and encourage exploration.

---

## 1. Fix validation: what actually changed since yesterday?

**Headline: nothing has been deployed.** The production bundle hash is unchanged (`main.07bdc1e4.js`), and every bug and UX issue from yesterday's report reproduces today. Twelve fix/feature PRs were opened after yesterday's report (#23–#34, covering BUG-1..4, SUG-1/2/3/5/6/7, `/go/<shape>` redirects, and a "Due Today" queue), but **all are still open and unmerged**, so none of them has reached users.

### 1.1 Per-item validation (live site, desktop + mobile)

| ID (from 2026-07-19) | Status today | Evidence from this run |
|----|----|----|
| **BUG-1** — stale `bundle.js` script tag → JS parse error on every load | **Still present** | `GET /static/js/bundle.js` → `200`, `content-type: text/html`, body starts `<!doctype html>`; page error `SyntaxError: Unexpected token '<'` fired on load (desktop and mobile). Fix exists in PR #23, unmerged. |
| **BUG-2** — no catch-all/404 route | **Still present** | `/this-route-does-not-exist` renders only the navbar (`Lexitrail | About | Try | Sign in`) over an empty page, both viewports. Fix in PR #24, unmerged. |
| **BUG-3** — trailing `\r` in wordset descriptions + fragile hide-filter | **Still present** | Raw `GET /wordsets` still returns `"HSK1\r"` … `"HSK7\r"`; the `test`/`HSK7` sets are still hidden only by matching the dirty strings. Fix in PR #25, unmerged. **New observation:** the `\r` pollution extends into word definitions too — e.g. wordset 1 word 你 has `def2: "you\r"`. |
| **BUG-4** — duplicate divergent auth (`hooks/useAuth.js` vs `AuthContext`) | **Still present in `main`** | `App.js` still imports from `hooks/useAuth`; `NavBar`/`PrivateRoute` from `AuthContext`. Fix in PR #26, unmerged. |
| **BUG-5** — transient 503 on cold routes | **Not reproduced** | 10 consecutive `GET /about` → all `200`. Consistent with yesterday's "transient cold-start" hypothesis; keep an eye on it, but no action provable from outside. |
| **SUG-1** — raw recall/debug metadata on cards | **Still present** | Every practice card shows `Exclude`, red/green recall-state number, and the `time • ✅/❌ • 0 → 0 • 🔄` history row. PR #28 unmerged. |
| **SUG-2** — hint images generic + fetched eagerly | **Still present, worse than measured yesterday** | Hints still auto-load for every card; one desktop session generated **181** `GET /hint/generate_hint` calls (yesterday: 37). Images remain generic stock-style (e.g. 妈妈 "mom" → clasped hands; 不 "no" → a brush stroke). PR #30 unmerged. |
| **SUG-3** — nonsense concatenated quiz distractors + mid-syllable wrapping | **Still present** | Distractors like `dàdiànhuà`, `zěnme`-fragments render wrapped mid-syllable (`diàny/ng`, `zěnm/e`, `lǐmiàn` broken across lines) in narrow option buttons. PR #29 unmerged. |
| **SUG-4** — Test mode is character→pinyin only | **Still present** | All quiz cards show a character and four pinyin options; no meaning/audio/typing variants. |
| **SUG-5** — no onboarding | **Still present** | Practice drops straight into a 16-card grid with unexplained controls. PR #33 unmerged. |
| **SUG-6** — thin Completed screen | **Still present** | Completed screen = time, %, a wall of all 150 characters, "Play again". PR #32 unmerged. |
| **SUG-7** — accessibility gaps | **Still present** | `<html lang="en">` with **0** nodes marked `lang="zh"`; recall state still color-only. PR #31 unmerged. |
| `/go/<shape>` short links (PR #27) | **Not deployed** | `GET /go/panda` → `200` SPA index (blank route), no redirect. |
| "Due Today" queue (PR #34) | **Not deployed** | `/wordsets` shows only the 7 set tiles; no due-today entry point. |

### 1.2 What *is* working well (confirmed today)

- Private-route gating works and the deep link is preserved: visiting `/game/1/TEST` logged-out shows the sign-in card, and after "Try without signing in" the user lands directly in that game. 
- Demo-account flow works end to end on both viewports: `POST /users` → 201, recall PUTs persist (`PUT /userwords/:email/:id/recall` → 200), excluded words round-trip correctly into "Show Excluded".
- Per-card ✔️/❌ taps work on mobile; no horizontal overflow on `/wordsets`, Test mode, or landscape practice.
- Performance is decent: TTFB ~81 ms, DOMContentLoaded ~700 ms, cold home load ~1.4 s / ~1.15 MB (1.05 MB of it JS).
- No console errors other than the known BUG-1 parse error.

---

## 2. New bugs found today (NEW-1 … NEW-9)

### NEW-1 (High, mobile) — Practice screen overflows horizontally; score counters and right card column are clipped
On iPhone-13-sized portrait, `/game/:id/PRACTICE` has **88 px of horizontal overflow** (`scrollWidth` 478 vs `clientWidth` 390). Offenders (measured): `nav.navbar` (478 px wide), the logged-in user block (`.user-info-compact`, email extends to x=462), and `.memorized` — i.e. the **✔️ score counter extends to x=478 and is cut off**, the timer is partially clipped, and the right-hand column of cards is truncated at the viewport edge. The user's demo email is also clipped in the navbar on `/wordsets` even where the page itself doesn't scroll.

**Impact:** Core game HUD (score, timer) is partially invisible on the most common phone width; the page wobbles sideways when swiping.
**Suggested fix:** Make the navbar and `.progress-stats` wrap/shrink under 480 px (hide the email, collapse the user chip to the avatar); give the cards grid `max-width: 100%` and let the HUD flex-wrap.

### NEW-2 (Medium, mobile) — Continuous layout shift while hint images stream in makes bottom controls unreliable to tap
While hint images load (which happens for many seconds after entering Practice, and again every time cards advance), card heights toggle between hint/no-hint layouts and the grid keeps reflowing. Concretely: Playwright's actionability check on the "✔️ to all N" button **failed for over 30 seconds** on mobile because a moving `.word-card-front` / ❌ button kept intercepting the click point; a raw coordinate tap in a quiet moment succeeded. A human sees the same thing as buttons shifting under their finger mid-tap and taps landing on the wrong element (e.g. flipping a card or marking ❌ instead of pressing the bottom button).

**Impact:** Mis-taps during the highest-frequency interaction loop; also makes the app hard to test with automation.
**Suggested fix:** Reserve fixed space for the hint image area regardless of load state (skeleton box), so cards never change height after mount; combined with hint opt-in/caching (PR #30) this eliminates the reflow storm.

### NEW-3 (Medium) — Demo identity is per-tab; a second tab silently logs you out and mints another user
The demo user lives in `sessionStorage`, which is **per tab**. Verified: after creating a demo user in tab 1, opening `/wordsets` in a second tab of the *same browser* shows the "Ready to Start Learning?" sign-in wall; pressing Try there creates a *new* `xxxxx@lexitrail.demo` user. Every one of today's six automated sessions minted a fresh demo user (`s2lja@`, `hmet2@`, `bp3if@`, `7n280@`, `u6t7j@`, `vwot6@` …), each doing `POST /users` → 201.

**Impact:** (a) Users who middle-click/duplicate a tab lose their progress and get a confusing logged-out state; (b) the users table accumulates an unbounded pile of orphaned demo accounts and their hint/recall rows.
**Suggested fix:** Store the demo identity in `localStorage` (shared across tabs) with the same lifetime semantics, and add a server-side cleanup job for stale `@lexitrail.demo` accounts. Longer-term, the demo→Google account merge (yesterday's FEAT-6).

### NEW-4 (Medium, UX/game design) — A practice "session" is the entire word set, and session progress resets on reload
Practice for HSK1 is one monolithic session of **150 words** ("recalled 0 out of 150"); the combined HSK1+2+3 set is **599 words**. There is no way to do a short session, and no session checkpointing: reloading mid-game resets the counter to `recalled 0 out of 150`, the timer to 0:00, and re-deals the full set (per-word recall history persists server-side, but the *session* does not, and completing a set is not recorded anywhere).

**Impact:** A realistic 5-minute mobile session can never reach the (only) reward screen; an accidental reload wipes visible progress. This is a direct retention killer (see §3).
**Suggested fix:** Deal practice in rounds of 10–20 cards with a mini-summary between rounds; persist session state (or at least surface "N of 150 mastered all-time" from recall data instead of a per-session counter).

### NEW-5 (Medium, UX) — Test mode never shows the correct answer or the word's meaning
When you answer in Test mode — right or wrong — the card flashes a color and is immediately replaced by a new word. You are never shown the correct pinyin after a miss, and the English meaning appears nowhere in the whole mode.

**Impact:** Zero learning from mistakes; Test mode trains recognition of pinyin spellings only. Combined with SUG-3's fake distractors, a wrong answer teaches nothing and can even reinforce a fake word.
**Suggested fix:** On answer, briefly reveal the correct pinyin + meaning (auto-advance after ~1.5 s, tap to skip); add missed words to the mini-card rail like Practice does.

### NEW-6 (Medium, mobile) — Test/Show-Excluded layouts waste ~45% of the phone screen on an empty dark sidebar
On mobile, the `.incorrect-cards-container` rail renders as a large empty dark-gray column (~180 px of a 390 px viewport) even when there are no missed words, squeezing Test mode to a single visible card. Show Excluded with one word has the same giant empty band. (Screenshots: one quiz card beside a big black rectangle.)

**Impact:** Cramped cards, more scrolling, and a broken-looking first impression of the game screen on phones.
**Suggested fix:** Collapse the rail to zero width (or a thin badge strip) when empty on narrow viewports; expand only when it has content.

### NEW-7 (Low, game design/data integrity) — "✔️ to all N" marks words as memorized sight-unseen
The blue "✔️ to all 16" button instantly marks every visible card memorized without the user ever flipping/seeing an answer. Today's run "completed" all 150 HSK1 words in 36 seconds with a **99%** score, and each blind click wrote real `PUT …/recall` records (130 recall writes in one session).

**Impact:** One tap poisons the entire recall dataset that any future SRS/"due today" scheduling depends on, and lets users hollow out their own progress signal.
**Suggested fix:** Remove it, restrict it to already-flipped cards, or reframe it as "skip these words" that doesn't count as a successful recall.

### NEW-8 (Low, visual) — Completed screen: attempts badge overlaps, and the layout ignores mobile
On the Completed screen the red "(2 attempts)" superscript renders overlapping the neighboring character (desktop screenshot), and the screen is a fixed-width wall of 150 characters with a single "Play again" button (no back-to-wordsets; PR #32 addresses this but is unmerged).

### NEW-9 (Low, SEO/PWA) — No canonical link; manifest exists but no service worker
`index.html` has title/description/OG tags but **no `rel="canonical"`**, and `navigator.serviceWorker.getRegistrations()` returns 0 despite `manifest.json` being served — the PWA story is half-installed (relevant to yesterday's FEAT-10).

---

## 3. Top 10 reasons this product has low engagement / retention

Ranked diagnosis, each tied to concrete observed behavior:

1. **There is no reason to come back tomorrow.** No streaks, no daily goal, no "due today" queue, no reminders, no email/push. Once a session ends, the product offers literally nothing that expires or accrues. (The one PR that would change this, #34, is unmerged.)
2. **Progress feels — and often is — lost.** Session counters reset on reload (NEW-4); finishing a set is not recorded; demo progress evaporates per tab (NEW-3) and permanently when the session ends. Users learn quickly that investment here doesn't stick, which is the opposite of the sunk-cost loop that retains learners.
3. **Sessions are oversized and unrewarding.** The only "win" screen sits behind grinding 150–599 cards in one sitting (NEW-4). A commuter with five minutes can never finish anything, so every session ends mid-grind with no closure.
4. **One-and-a-half learning modes, no audio.** Flip-cards plus a character→pinyin quiz is the entire product. No listening, speaking, typing, tone drills, or meaning recall — and for a *tonal language* there is no audio anywhere. Variety is what makes daily practice tolerable; its absence caps session count.
5. **No visible sense of mastery.** What users see is debug internals (red/green `0`, `0 → 0` history rows) instead of "you know 37 of 150 words" or a progress ring per set. The wordsets page looks identical on day 1 and day 100 — nothing reflects the work you've put in.
6. **The first session is confusing.** No onboarding (SUG-5), a 16-button grid of unexplained controls, hint images that pop in and shove the layout around (NEW-2), and a console error on every load (BUG-1). Most retention is decided in the first session; this one starts with friction.
7. **Weak feedback loops.** Test mode never shows the right answer or meaning (NEW-5); wrong-answer distractors are fake words (SUG-3); the Completed screen is a character dump with "Play again" (NEW-8). Correct/incorrect feels arbitrary rather than instructive, so the core loop doesn't feel like learning.
8. **The marketing over-promises and the product under-delivers.** Home page sells "clever memory aids and etymology explanations", "example sentences and usage notes", "cultural context", "create custom word sets" — none of which exist in the app (hints are generic stock-style images; there's no sentence, etymology, or create flow). The gap breeds distrust exactly when a new user is deciding whether to return.
9. **Mobile — where habitual learning happens — is the roughest surface.** Clipped score counters and sideways wobble (NEW-1), one visible card beside a dead sidebar (NEW-6), moving tap targets (NEW-2), no installable PWA/offline/push (NEW-9). Language-app retention is overwhelmingly mobile; this experience discourages exactly that usage.
10. **Nothing is yours and nobody else is here.** No account-worthy identity (demo progress dies, Google sign-in starts from zero), no custom word sets, no stats page, no social proof, leaderboards, friends, or shared sets. There's no accumulating asset and no community pull — the two forces that bring people back when motivation dips.

---

## 4. What would make it more interesting / encourage exploration

### 4.1 First: ship what's already built
The single highest-leverage action is to **merge and deploy the existing open PRs** (#23–#34). They already address BUG-1..4 and SUG-1/2/3/5/6/7 plus the Due-Today queue — a second exploration a day later found users still experiencing 100% of yesterday's issues.

### 4.2 Make the wordsets page a map, not a menu (encourages exploration directly)
- Show **per-set progress** on each tile: a mastery ring ("42/150 known"), last-practiced date, and a "Continue" primary action. The page becomes a visual record of your journey, and half-finished rings beg to be completed.
- Add **preview and count** to each tile (e.g. "150 words · 你 · 好 · 谢谢 …") so anonymous visitors can see what's inside before signing in — today the tiles are opaque buttons.
- Add a light **progression frame**: HSK1 → HSK6 as a trail (the product is literally named Lexitrail) with the next level visually "unlocking" at e.g. 80% mastery. Locked-but-visible content is a proven exploration driver.
- Add a **placement quiz** ("Where should I start?") for newcomers who don't know HSK levels.

### 4.3 Give every day a reason (retention loop)
- **Due-today SRS queue** (PR #34) as the primary CTA everywhere: "12 words due — 3 min".
- **Streak + daily goal** with a calendar heat-map; a demo-friendly version can live in `localStorage` immediately.
- **Daily challenge / word of the day** on the home page — one fresh card even for anonymous visitors, shareable, and a soft on-ramp to Try.

### 4.4 Deepen each card so words are worth revisiting (exploration within content)
- **Audio (TTS)** on every card — the biggest single content gap for a Mandarin product.
- **Character breakdown & mnemonic text** per word (the home page already demos this format for 记忆); pair or replace the generic hint images with it.
- **Example sentence** on the card back (the repo has a `sentences/` module) — this also delivers the "Cultural Context" promise.
- Tapping a word anywhere (Completed list, mini-rail, quiz reveal) should open a **word detail view** — right now the app has no way to just *look up* or browse a word, so there is nothing to explore between drills.

### 4.5 Make sessions feel finishable and instructive
- **Rounds of 10–20 cards** with a micro-summary (accuracy, new words, streak tick) between rounds; "Completed" becomes reachable in 3 minutes.
- **Answer reveal in Test mode** (NEW-5) and real-word distractors (PR #29); alternate character→pinyin with character→meaning.
- Richer **Completed screen** (PR #32): missed-word review with meanings, next-set suggestion, share card.

### 4.6 Make investment durable
- **Demo → Google account merge** ("Sign in to keep these 26 words") at the end of the first session — the single best conversion moment; plus `localStorage` demo persistence now (NEW-3).
- **Stats page** (words known, accuracy trend, time practiced) and simple badges.
- Finish the **PWA**: service worker, offline review of cached sets, install prompt, and later web-push for streak reminders.

---

## 5. Quick-reference summary

| ID | Type | Severity | One-line | Status |
|----|------|----------|----------|--------|
| BUG-1..4 (2026-07-19) | Bug | High→Low | See §1.1 | **Still live; fixes in PRs #23–#26, unmerged** |
| BUG-5 (2026-07-19) | Bug | Transient | Cold-route 503 | Not reproduced today |
| SUG-1..7 (2026-07-19) | UX | — | See §1.1 | **All still live; PRs #28–#33 unmerged** |
| NEW-1 | Bug | High (mobile) | Practice screen 88 px horizontal overflow; ✔️ counter/timer clipped | New today |
| NEW-2 | Bug | Medium (mobile) | Hint-image loading causes continuous layout shift; bottom button untappable for 30 s+ in automation | New today |
| NEW-3 | Bug | Medium | Demo identity per-tab; second tab = logged out + new demo user; orphan account buildup | New today |
| NEW-4 | Bug/UX | Medium | Session = whole set (150–599 words); progress resets on reload; completion never recorded | New today |
| NEW-5 | UX | Medium | Test mode never reveals correct answer or meaning | New today |
| NEW-6 | Bug | Medium (mobile) | Empty incorrect-words sidebar consumes ~45% of phone width in Test/Show-Excluded | New today |
| NEW-7 | UX/data | Low | "✔️ to all" records blind recalls (99% in 36 s), poisoning SRS data | New today |
| NEW-8 | Visual | Low | Completed screen attempts-badge overlap; no mobile layout | New today |
| NEW-9 | SEO/PWA | Low | No canonical tag; manifest without service worker | New today |
| §3 | Analysis | — | Top-10 low-retention diagnosis | — |
| §4 | Proposals | — | Ship open PRs; wordsets-as-map; daily loop; card depth; finishable sessions; durable investment | — |
