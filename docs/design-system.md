# LexiTrail design system — as shipped, 2026-09-06

Written for a design agent about to propose a comprehensive design improvement. It describes
**what is live today**, not what we intend. Every URL below was fetched and every style value was
read out of the file that produces it; where I could not establish something I say so rather than
filling the gap.

---

## 0. The one thing to read first

**LexiTrail is currently two different products wearing two different designs.**

| | Static pages | React SPA |
|---|---|---|
| What | 5,010 pre-rendered HTML pages | the actual practice app |
| Audience | search traffic (cold, first contact) | signed-in learners |
| Design | a real, deliberate system — warm paper palette, serif hanzi, dark mode, one CSS source | no token layer at all — three competing blues, four font stacks, no dark mode |
| Source of truth | `ui/src/utils/hskPages.js` → `PAGE_STYLE` (one constant, ~60 lines) | 16 hand-written CSS files, 2,738 lines, no shared variables except one tap-target floor |
| Shipped | 2026-09-05 (styles), 2026-09-06 (homepage links) | accreted over the project's life |

A visitor from Google lands on a calm, warm, serif, dark-mode-aware word page, taps **Practise**,
and arrives in a white-and-Google-blue Arial SPA. That discontinuity is, in my view, the single
largest design problem in the product, and it is the reason this document leads with it rather
than with a palette table.

⚠️ Note before designing: `.word-card` is a class name in **both** systems and means two unrelated
things — the static hero card (20px radius, warm surface, centred) and the SPA's 160px flip card
(8px radius, 3px `#d3d3d3` border). Any shared-stylesheet plan has to resolve that collision.

---

## 1. Live URLs

Verified 2026-09-06 (HTTP status in brackets; the last row is a deliberate negative control that
proves the others mean something).

| Surface | URL | |
|---|---|---|
| SPA home | `https://lexitrail.com/` | 200 |
| HSK index (×6) | `https://lexitrail.com/hsk1.html` … `hsk6.html` | 200 |
| Per-word page (×4,999) | `https://lexitrail.com/hsk1/%E4%B8%80.html` (一) | 200 |
| Gloss lander (×5) | `https://lexitrail.com/tennis-in-chinese.html` | 200 |
| Sitemaps | `/sitemap.xml` (7 urls), `/sitemap-words.xml` (4,999), `/sitemap-gloss.xml` (5) | 200 |
| SPA route | `https://lexitrail.com/about` | 200 |
| *(control)* 一 under the wrong level | `https://lexitrail.com/hsk6/%E4%B8%80.html` | **404** ✓ |

**Bare paths 301 to `.html`** — `/hsk1` → `/hsk1.html`, `/tennis-in-chinese` →
`/tennis-in-chinese.html`. Configured in `ui/public/serve.json`, which also holds 11 `/go/*`
campaign redirects (302, UTM-tagged) used by the social accounts.

**The `.html` suffix is deliberate, not legacy.** `hskPages.js` records that extensionless URLs
were measured against the real `serve` config and do not resolve. Do not "clean up" the URLs.

---

## 2. The static design system — the good one

### 2.1 Where it lives

**One constant: `PAGE_STYLE` in `ui/src/utils/hskPages.js` (line ~64).** All three page families
import it:

```
ui/src/utils/hskPages.js    -> PAGE_STYLE, SITE_HEADER, HSK_LEVELS, ORIGIN   (the source)
ui/src/utils/wordPages.js   -> imports PAGE_STYLE   (per-word pages)
ui/src/utils/glossPages.js  -> imports PAGE_STYLE   (gloss landers)
```

These are **pure, unit-tested modules**. The three files in `ui/scripts/` are thin I/O shells:

```bash
node ui/scripts/generate-hsk-pages.js            # write the 6 index pages
node ui/scripts/generate-word-pages.js           # write the 4,999 word pages
node ui/scripts/generate-gloss-pages.js          # write the 5 gloss landers
node ui/scripts/generate-word-pages.js --check   # exit 1 if any committed file is stale
```

🔴 **The generated HTML is COMMITTED to the repo on purpose.** The Docker build context is `ui/`,
so `terraform/csv/words.csv` and `sentences/` — one directory up — do not exist inside the image.
A build-time generator works locally, passes review, and produces nothing in production. **A design
change means editing `PAGE_STYLE` and re-running the generators, then committing ~5,000 changed
files.** Budget for that in any proposal.

### 2.2 Tokens (verbatim from `PAGE_STYLE`)

```css
:root{
  color-scheme: light dark;
  --bg:#fbf9f4;        /* warm paper            */
  --surface:#fff;      /* cards, tables, dl     */
  --ink:#1d1a16;       /* body text             */
  --muted:#6d6558;     /* labels, captions, nav */
  --line:#eae3d6;      /* all borders/rules     */
  --accent:#b23b2e;    /* terracotta — links, pinyin, CTAs */
  --accent-ink:#fff;   /* text on accent        */
  --accent-soft:#fbeeeb; /* HSK badge fill      */
  --shadow:0 1px 2px rgba(40,30,20,.06), 0 8px 24px rgba(40,30,20,.06);
}
@media (prefers-color-scheme:dark){:root{
  --bg:#141310; --surface:#1f1c17; --ink:#f2ede2; --muted:#a79e8e; --line:#332f27;
  --accent:#e6796a; --accent-ink:#1a0f0c; --accent-soft:#2b1d19;
  --shadow:0 1px 2px rgba(0,0,0,.3), 0 10px 30px rgba(0,0,0,.35);
}}
```

There is no blue anywhere in the static system. The accent is a terracotta red that shifts to a
lighter coral in dark mode so it keeps contrast against the near-black surface.

### 2.3 Typography

```css
body   font-family: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif
       font-size: 17px;  line-height: 1.65;  -webkit-font-smoothing: antialiased

:lang(zh-Hans), .hanzi-big, td[lang]
       font-family: "Noto Serif SC","Songti SC","STSong","Source Han Serif SC","SimSun",serif

h1     clamp(1.5rem, 5vw, 2rem)   line-height 1.2   letter-spacing -.02em
h2     1.15rem                    letter-spacing -.01em
.hanzi-big   clamp(4.2rem, 26vw, 7.5rem)  line-height 1  letter-spacing .02em
.pinyin      1.5rem, --accent, weight 500
.translation 1.25rem, --ink
.word-h1     font: inherit — a SEMANTIC wrapper with no typography of its own (see §3.1)
```

**The serif/sans split is the system's strongest idea and should survive any redesign:** Latin text
is a neutral system sans, Chinese is always a Song/Ming serif. It is applied by `:lang(zh-Hans)`
and by `td[lang]`, so it works on table cells without extra classes.

⚠️ Every one of those families is a **local** font. No webfont is loaded on any static page, which
is why they render instantly and why a Chinese glyph falls back to whatever the OS has. A proposal
that introduces a webfont should say what it costs on the cold-search-traffic path these pages
exist to serve.

### 2.4 Layout and components

```css
.wrap        max-width: 660px; margin: 0 auto; padding: 20px 20px 72px
.site        the header — flex, 8px gap, weight 700; a 10px rounded --accent square + "LexiTrail"
.word-card   --surface, 1px --line, radius 20px, padding 34/28/30, centred, --shadow
.hsk-badge   pill (radius 999px), --accent-soft on --accent, .8rem, uppercase, letter-spacing .03em
.cta,button  pill (radius 999px), --accent on --accent-ink, weight 600, padding 13px 22px
             :hover brightness(1.05)   :active translateY(1px)
dl           2-col grid (auto 1fr), gap 6/18, --surface card, radius 16, padding 18/20
             dt = --muted, .85rem, uppercase, letter-spacing .04em
table        full width, collapsed, --surface, 1px --line, radius 16, overflow hidden
             thead th = .78rem uppercase --muted; tbody tr:nth-child(odd) tinted via color-mix()
             td[lang] = 1.3rem (the hanzi column)
ul.other-ways  flex-wrap chip row, radius 12
h2 + ul        stacked cards, radius 14, em rendered as --accent non-italic
nav            top-rule, --muted, .95rem, flex-wrap, gap 6/14
```

Radii are consistent and intentional: **999px** for anything tappable, **20px** hero card,
**16px** data containers, **14/12px** list items.

### 2.5 Accessibility notes on the static pages

- `color-scheme: light dark` is declared, so form controls and scrollbars follow the theme.
- `-webkit-text-size-adjust:100%` prevents iOS auto-inflation.
- Tap targets: `.cta` computes to ~48px tall, `.hsk-badge` to ~29px. **The badge is a link and is
  under the 44px WCAG 2.5.5 floor** — the SPA has an explicit floor for this and the static pages
  do not. Worth fixing in a redesign.
- I did **not** run a contrast audit. `--muted #6d6558` on `--bg #fbf9f4` is roughly 5.2:1 by
  inspection (passes AA body text), but treat that as unverified.

---

## 3. Screen-by-screen — the static pages

### 3.1 Per-word page — **the new indexed pages, shipped 2026-09-05**

This is the surface Alex asked to have covered in most detail. **4,999 pages, one per word**, one
file per word committed under `ui/public/hsk{1..6}/<hanzi>.html`.

```
hsk1  150      hsk3  300      hsk5  1300
hsk2  149      hsk4  600      hsk6  2500        total 4,999
```

**URL shape:** `https://lexitrail.com/hsk<N>/<percent-encoded-hanzi>.html`. The filename is the raw
hanzi on disk (`ui/public/hsk1/一.html`) and percent-encoded in every link, canonical and sitemap
entry. Some words carry parentheses — `这 (这儿).html` — which encode as `%E8%BF%99%20(...)`.

**Page anatomy, in order:**

1. `<header class="site">` — the dot + wordmark, links to `/`.
2. `.word-card` — the hero. Contains, centred:
   - `<h1 class="word-h1">` — a **semantic wrapper with no appearance of its own**, holding the next three lines. It exists because the ranking queries are *"<gloss> in Chinese"* and an H1 of bare hanzi carries none of the words the searcher typed (#368 fixed the `<title>` on the same evidence and stopped at the title). `.word-h1 { font: inherit; letter-spacing: inherit; margin: 0 }` cancels the `h1` rule and the UA bold, and `.word-h1 > span { display: block }` restores the block layout the three `<p>`s had — the rendered card is pixel-identical to the pre-change version, verified at three viewports in both colour schemes. The lines are `<span>`s, not `<p>`s, because a `<p>` inside an `<h1>` is invalid and the parser would unnest it.
   - `.hanzi-big` (`lang="zh-Hans"`, and the ONLY element in the H1 that carries that lang — the gloss must never sit inside a Chinese lang scope). At `clamp(4.2rem,26vw,7.5rem)` it is 68–120px, dominating the fold.
   - `.pinyin` — tone-marked, terracotta, 1.5rem.
   - `.translation` — the English gloss, 1.25rem.
   - `.hsk-badge` — a pill linking to that level's index page.
   - `.cta` — *"Practise HSK N with 一 →"* linking to `/game/<level>/PRACTICE`.
3. **One prose paragraph.** Roughly 60 words, generated per word, explaining the pinyin and gloss and then making the spaced-repetition argument (*"Recognising a word on a page and recalling it when you need it are different skills, and only the second survives a conversation"*). The hanzi is wrapped in `<span lang="zh-Hans">` inline so it picks up the serif mid-sentence.
4. `<nav>` — a **prev / index / next** triple. Ordering is the word list's own order, not Unicode; `rel="prev"`/`rel="next"` are set both in `<head>` and on the links.

**Head block** (this is where most of the page's value is): `canonical`, `rel=prev`/`rel=next`,
full Open Graph + Twitter card set, and a **`DefinedTerm` JSON-LD** block nesting the word inside a
`DefinedTermSet` for its HSK level. Total page weight ~7 KB, entirely self-contained — no external
CSS, JS, font or image request.

**Design observations for the redesign:**

- The pages are *quiet* and read well, but they are **thin**: hero, one paragraph, nav. There is no
  stroke order, no audio, no example sentence, no character breakdown, no related-words block —
  all of which exist on competitor word pages and all of which the design could hold.
- The prose paragraph is near-identical across all 4,999 pages apart from the word itself. That is
  a duplicate-content risk and a design opportunity: the space could carry per-word content.
- **The hero has no audio button**, though the gloss landers do (`ltSpeak`) and the SPA has a
  `SpeakButton` component. This is the clearest inconsistency inside the static family.
- Prev/next is the only lateral navigation. There is no breadcrumb and no search.

### 3.2 HSK index pages — `hsk1.html` … `hsk6.html`

`<h1>HSK N vocabulary list</h1>`, an intro paragraph naming the exact entry count, an inline
practice link, then a **4-column table**: `#`, `Hanzi` (a link to the word page, `td[lang]` so it
renders serif at 1.3rem), `Pinyin`, `English`. Zebra striping via `color-mix()`.

`hsk6.html` is a **2,500-row table in a single page.** Nobody has designed for that length: no
sticky header, no in-page filter, no alphabet/radical jump, no pagination. It is the most obvious
structural weakness in the static set.

### 3.3 Gloss landers — `<gloss>-in-chinese.html`

Five pages, shipped 2026-09-05: `tennis`, `clarify`, `vague`, `reputation`, `decision`. These
target *"X in Chinese"* search intent, so the **English gloss is the `<h1>`** and the hanzi sits in
the card below it. This used to be the inverse of the word pages; since the `.word-h1` change in
§3.1 both families put the gloss in the H1, and what still differs is the ORDER — here the gloss
leads, there the hanzi does, which is right for each page's own subject.

They carry two things the word pages do not:

- **An audio button.** `<button onclick="ltSpeak('网球')">🔊 Play audio</button>` backed by a 6-line
  inline script using `speechSynthesis` at `lang='zh-CN'`, `rate 0.85`. The only JavaScript on any
  static page.
- **`.tone-numbers`** — numbered pinyin (`wang3 qiu2`) in `--muted` beside the tone-marked form.
- **Example sentences** — an `h2 + ul` card stack, each item hanzi / italic pinyin / English.

They also use `.hsk-cta`, a class **not present in `PAGE_STYLE`**, so those "HSK 1 →" practice
chips currently fall back to plain `a` styling. That is a live inconsistency, not a design choice.

### 3.4 404

`ui/public/404.html`, 1.4 KB, styled from the same palette.

---

## 4. Screen-by-screen — the React SPA

`ui/src/App.js` routes. `/wordsets/*` and `/game/*` are behind `PrivateRoute` (Google sign-in).

| Route | Component | Notes |
|---|---|---|
| `/` | `Home.js` | marketing homepage, signed-out; renders `Today.js` when signed in |
| `/wordsets` | `Wordsets.js` | wordset picker — **private** |
| `/game/:wordsetId/:mode?` | `Game.js` | the practice session — **private**, 546 lines, the largest screen |
| `/about` `/privacy` `/terms` | `About.js` `PrivacyPolicy.js` `TermsOfService.js` | static content in-app |
| `*` | `NotFound.js` | |

`/game` alone redirects to `/wordsets`. All SPA routes are rewritten to `index.html` by
`serve.json`; **only 7 URLs are in `sitemap.xml`** — the unrenderable SPA routes were deliberately
dropped (issue #367), so search traffic is meant to land on static pages, never on the app shell.

### 4.1 Global — `styles/Global.css`

```css
body, html { font-family: Arial, sans-serif; background-color: #f0f0f0;
             display:flex; justify-content:center; align-items:center; height:100%; }
:root { --min-tap-target: 44px; }
```

That is the entire global layer: **Arial, a flat grey page, and one variable.** No colour tokens,
no type scale, no spacing scale, no dark mode anywhere in the SPA (`prefers-color-scheme` appears
in **zero** of the 16 CSS files — grepped, not assumed).

`--min-tap-target` is applied by an **enumerated list of ~15 class selectors** to enforce the WCAG
2.5.5 44px floor. The comments in that file are worth reading before touching any control: the
enumeration has been the gap four separate times, because a control absent from the list is
invisible to the test that guards it. **If a redesign renames or adds an interactive class, it must
be added to that list**, and component CSS may not re-declare the number (component files load
after `Global.css` at equal specificity, so a local literal silently wins).

### 4.2 The SPA palette, measured

Extracted by frequency across all 16 files:

```
#fff / #ffffff  20   surfaces
#1a73e8         11   Google blue — primary CTA          }
#4285f4          8   Google blue — a second one          } three competing blues
#007bff          6   Bootstrap blue — a third            }
#2c6cd3           6   a fourth, darker
#1557b0           5   hover state for #1a73e8
#333 #555 #666   22   three greys for text, unrelated to each other
#e0e0e0 #dadce0   9   two border greys
#2e7d32 #28a745 #1b5e20 #4caf50  15   four greens for "correct"
```

Font stacks in use: `Arial, sans-serif` (×3), `-apple-system, BlinkMacSystemFont, 'Segoe UI'…`,
`"Google Sans", Roboto, Arial` (×2), `'Times New Roman', Times, serif`, `monospace`, `inherit`.

Radii: `8px` ×18, `4px` ×12, `12px` ×7, `50%` ×6, plus one each of 6, 10, 999, 7, 5, 3px.

**This is the concrete case for a token layer.** Four blues, four greens, three greys and six
fonts are not decisions; they are accretion.

### 4.3 Home — `Home.js` / `Home.css`

Signed-out marketing page, `max-width: 800px` content with a `1000px` features band.
Sections: `.hero-section` → `.hero-value-prop` → `.hero-cta` → `.example-word` (a
`.chinese-char` + `.meaning` sample) → `.features-section` / `.features-grid` of `.feature-card`
(white, radius 12) → `.cta-section` (`#f8f9fa`, radius 12).

Primary button: `#1a73e8`, white, radius 8, hover `#1557b0`. A second CTA further down uses the
same blue at radius **4** — the same button, two radii.

**Signed in, `/` renders `Today.js` instead** — a different screen at the same URL.

As of 2026-09-06 (#377) the homepage also carries **static `<a>` links to the five gloss landers**
so Googlebot can reach them without executing JavaScript.

### 4.4 Today — `Today.js` / `Today.css`

The habit screen. `.today-headline` (or `.today-headline.today-done`), `.today-count`,
`.today-target`, `.today-streak` (a `StreakBadge`), `.today-start` as the single primary action,
`.today-secondary` ("Practice anyway") and `.today-status` / `.today-status.today-error`.

`.today-secondary` is a `<Link>` styled as 0.95rem body text — it measured **110.6 × 17.0 px** on
live production, 27px under the tap floor, the largest miss in the whole matrix. It now carries the
floor plus `display:inline-flex` in `Today.css`. A redesign should keep it looking like a real
control rather than a text link.

### 4.5 Wordsets — `Wordsets.js` / `Wordsets.css`

`.wordsets-grid` of cards, each `.wordset-header` + a `.wordset-button-group` of four:
`practice`, `due`, `test`, `excluded`. Plus `.wordsets-status` / `.wordsets-error` and
`.wordsets-retry`.

Four sibling buttons of differing importance rendered at near-equal weight; `test` is taller only
because it spans three grid rows. There is no visual hierarchy expressing that `due` is the one a
returning learner wants.

### 4.6 Game — `Game.js` / `Game.css` (the core screen)

The practice session, and the most layout-constrained screen in the product.

- `.cards-area` is `height: calc(100% - 100px)`; `.cards-container` is a CSS **grid** with
  explicit layout classes — `layout1c1r`, `layout1c2r`, `2c2r`, `3c3r` … — chosen at runtime by
  `ui/src/utils/cardLayout.js` to fit the viewport without scrolling.
- `.incorrect-cards-container` is a second strip with `:empty { display:none }` — it previously
  wasted ~45% of a phone screen when there were no incorrect cards.
- `.word-card` (SPA sense): 160px wide, `perspective: 1000px` for a flip, 3px `#d3d3d3` border,
  radius 8, white.
  - `.success` → 3px `green` + green glow; `.failure` → 3px `red` + red glow, 50ms transition.
  - `.feedback-indicator` adds a **shape/label cue** so correct/incorrect is not colour-only.
- Also present: `.progress` / `ProgressBar`, `.game-settings-button`,
  `.mark-all-memorized-button`, `.loading-spinner`, `.error-container`.

The named CSS colours `green` and `red` are the only two in the codebase and they are the app's
most-seen feedback signal. Landscape card height was a shipped bug (issue #341, still open).

### 4.7 Completed, NavBar, Onboarding

- **`Completed.js`** — end-of-session summary: `.completed-session`, `.completed-review-list` of
  word/def rows with `.completed-incorrect-indicator`, and `.completed-actions` including a
  `.completed-button-share`.
- **`NavBar.js`** — `.navbar`, `.logo-text`, `.nav-wordsets-link`, and a `.dropdown` whose trigger
  is the avatar + name. Below 480px `.user-info-compact` is hidden, so the trigger collapses to a
  24px avatar and measured **35.2 × 44.0** — width fixed by a floor, not by design.
- **`OnboardingOverlay.js`** — 30 lines: `.onboarding-card` + `.onboarding-button`. The first
  control a new learner taps; it measured 43px tall, one pixel under the floor, in every viewport.
- **`SpeakButton`**, **`PinyinText`**, **`MiniWordCard`**, **`StreakBadge`**, **`Logo`**,
  **`OptimizedImage`**, **`SEO`**, **`JsonLd`** are the shared components.

---

## 5. Where a design change has to be made

| To change | Edit | Then |
|---|---|---|
| Any static page's look | `ui/src/utils/hskPages.js` → `PAGE_STYLE` | re-run all three generators; ~5,000 files change |
| Static page *structure* | `hskPages.js` / `wordPages.js` / `glossPages.js` (pure, unit-tested) | update the matching `*.test.js`; run `--check` |
| SPA look | the 16 files in `ui/src/styles/` | there is no token layer to change first — **creating one is the recommended first move** |
| A new interactive class | `ui/src/styles/Global.css` tap-target list | `tapTargets.test.js` cannot see a control that is not listed |
| URL/redirect shape | `ui/public/serve.json` | `serveRoutes.test.js` |

**Cost note for planning:** `ui/**` is the include path for the `lexitrail-ui-deploy-main` Cloud
Build trigger, so any UI change builds and deploys on merge. Docs-only changes (like this file)
build nothing.

🔴 **The ~5,000-file commit may not be a constraint for much longer — check #379 before designing
around it.** That issue proposes generating the static pages during the Cloud Build run instead of
committing their output, which would make a static design change one edited constant plus a deploy.
It is filed and unclaimed at the time of writing; if it has landed, §2.1's "re-run the generators
and commit ~5,000 files" no longer applies and a design proposal can iterate much more freely.

---

## 6. Open design issues already filed

`#341` practice cards taller than a landscape viewport · `#365` the gloss-lander programme (Phase 1
shipped: 5 pages) · `#297` wordset list fetched 3× per arrival · `#108` finishable micro-sessions —
"end the endless list" · `#220` the acquisition/retention/search epic · `#187` server-side streak ·
`#189` due-words reminder email.

---

## 7. What this document does not establish

Stated explicitly so nothing here is over-read:

- **No contrast audit was run.** Every colour value is quoted accurately from source; none has been
  measured against WCAG contrast ratios.
- **No rendered-box measurements were taken in this pass.** The pixel figures in §4 are quoted from
  in-repo comments recording earlier E2E runs against live production, not re-measured today. The
  E2E harness lives in `e2e/` if you need fresh numbers.
- **The 200s in §1 are status codes, not visual verification.** I did not screenshot any page.
- The SPA screen descriptions are read from JSX class names and CSS, so they are accurate about
  **structure and declared style**, and say nothing about how a screen composes at a given viewport.
- I have not reviewed the `sentences/`, `matchmaker/` or `middle_layer/` surfaces at all; they do
  not render UI.

---

*Compiled by hcl@ on 2026-09-06 from the state of `main` at the time of writing. If any figure here
disagrees with the code, the code is right and this file has rotted — the generators and
`PAGE_STYLE` are the source of truth.*
