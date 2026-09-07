// lexitrail#183 — the six crawlable HSK word-list pages.
//
// WHY. "HSK N vocabulary list" is this product's highest-intent query family and its SERP is held
// entirely by small content sites; no high-authority domain locks it. LexiTrail is absent because
// it has **no crawlable page containing a single Chinese word** — every route serves the same
// ~2,871-byte shell.
//
// 🔴 THE URLS END IN `.html`, AND THAT IS NOT A STYLE CHOICE. Measured against a real `serve`
// (this issue's premise said otherwise and was wrong):
//
//     /hsk2.html        REAL FILE ✅   an EXACT filesystem match
//     /hsk3/index.html  REAL FILE ✅   also exact
//     /hsk2             301 -> /hsk2.html   ⚠️ CORRECTED 2026-09-03, see below
//     /hsk3/            301 -> /hsk3.html   ⚠️ CORRECTED 2026-09-03, see below
//
// `serve-handler` serves an exact file BEFORE applying rewrites; anything needing *resolution* is
// caught first. So `cleanUrls: false` is required, or `/hsk2.html` 301s to `/hsk2`.
//
// 🔴 CORRECTED, NOT APPENDED TO (issue-342). The two rows above read `SPA SHELL ✗ needs
// cleanUrls resolution`, which was measured and true when `serve.json` carried a catch-all
// `{"source": "**", "destination": "/index.html"}`. That catch-all is GONE — unknown paths now
// 404 — and with it the thing that was absorbing `/hskN`. What actually happened next was worse
// than an SPA shell: `directoryListing` is absent from `serve.json` and `serve-handler` defaults
// it ON, so `build/hsk2/` is a real directory and prod served a RAW FILE INDEX
// (`<title>Files within build/hsk2/</title>`, 200) on all six bare paths for an unknown period.
// #342 sets `directoryListing: false` and adds explicit `/hskN -> /hskN.html` 301s.
//
// ⚠️ The old rows are rewritten rather than annotated because both readings survive an append and
// the stale one is the reassuring one — a reader who stops at the table gets the superseded
// answer. This is the same failure the docstring itself was written to prevent.
//
// lexitrail#76 — PER-PAGE og/twitter METADATA, which is possible HERE and nowhere else on this
// site. #76's finding stands for SPA routes: `<SEO>` is react-helmet, applied client-side, and the
// social crawlers do not execute JS, so mounting it on more routes changes nothing a crawler sees.
// These six pages are the exception BY CONSTRUCTION — they are static HTML, so whatever is in
// their <head> IS what the crawler gets.
//
// ⚠️ Before this they had NO og tags at all, which is worse than the generic card #76 complains
// about: a share of /hsk2.html produced no card, on the six pages most likely to be shared.
// og:image stays the one canonical landscape asset (there is no per-level artwork in the repo —
// checked); the TITLE and DESCRIPTION are what become per-page, and they are the half that says
// which page you are looking at.
//
// PURE ON PURPOSE. Nothing here touches the filesystem, so every claim below is unit-testable and
// the generator script is a thin shell around it. The committed HTML is checked against these
// functions by a drift test — a generated artifact nobody re-generates is a stale artifact.
//
// 🔴 revamp-2026-09 CHANGES PAGE_STYLE AND renderPage. Every committed page under build/ and
// public/ is therefore stale until `generate-hsk-pages` / `generate-word-pages` /
// `generate-gloss-pages` are re-run — the drift test will red until they are. That is the cost
// the design-system doc (§ "any static change costs ~5,000 regenerated files") priced in.

export const HSK_LEVELS = [1, 2, 3, 4, 5, 6];

export const ORIGIN = 'https://lexitrail.com';

// lexitrail#372 — the shared, INLINE stylesheet for every static page (hsk list, per-word, gloss).
//
// 🔴 INLINE ON PURPOSE, not a <link>. These files are served as-is by serve-handler and are the
// crawlable half of the site; a stylesheet <link> would be a second request that can 404, mismatch
// the SPA's hashed bundle, or arrive after first paint — the exact "broken styles" this fixes. A
// self-contained <style> renders correctly the instant the HTML lands, for a crawler and a human
// alike. It lives HERE (the base module both wordPages.js and glossPages.js import) so the three
// page families cannot drift apart; the generate scripts inject it the same way they inject ORIGIN,
// and that wiring fails LOUDLY if a script forgets it.
//
// revamp-2026-09 — THIS IS NOW THE TOKEN LAYER, shared with the SPA. The :root block below is
// byte-identical to ui/src/styles/Global.css's (hskPages.test.js pins it), so the crawlable half
// and the app are one system. New since #372: --surface-2, --font-*, --ok/--bad, --t1..--t4
// (pinyin tone colours, the same mapping PinyinText.js uses in the practice screen), --r-*.
// No webfont: the static family stays at one request. `--font-display` therefore resolves to the
// system stack here; the SPA may override it.
export const PAGE_TOKENS = `:root{color-scheme:light dark;
  --font-latin:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --font-display:var(--font-latin);
  --font-hanzi:"Noto Serif SC","Songti SC","STSong","Source Han Serif SC","SimSun",serif;
  --r-pill:999px;--r-hero:20px;--r-card:16px;--r-item:12px;--tap:44px;
  --bg:#fbf9f4;--surface:#fff;--surface-2:#f4efe6;--ink:#1d1a16;--muted:#6d6558;--line:#eae3d6;
  --accent:#b23b2e;--accent-ink:#fff;--accent-soft:#fbeeeb;
  --ok:#397146;--ok-ink:#fff;--ok-soft:#e6f1e8;--bad:#a4133c;--bad-ink:#fff;--bad-soft:#fbe9ee;
  --t1:#c8361f;--t2:#9c5410;--t3:#2a7130;--t4:#6b3fa0;
  --shadow:0 1px 2px rgba(40,30,20,.06),0 8px 24px rgba(40,30,20,.06)}
@media (prefers-color-scheme:dark){:root{
  --bg:#141310;--surface:#1f1c17;--surface-2:#28241d;--ink:#f2ede2;--muted:#a79e8e;--line:#332f27;
  --accent:#e6796a;--accent-ink:#1a0f0c;--accent-soft:#2b1d19;
  --ok:#7fc08f;--ok-ink:#0d1a10;--ok-soft:#1d2a20;--bad:#f0899d;--bad-ink:#33202a;--bad-soft:#34222a;
  --t1:#ff8a6f;--t2:#f0b45a;--t3:#7fd08a;--t4:#c39cf0;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 10px 30px rgba(0,0,0,.35)}}`;

// issue-393: GA4 on the STATIC surface. These ~5,600 word/HSK/gloss pages are
// deliberately standalone HTML (the 404.html precedent) and were generated
// without the tag, so every arrival on the whole lighthouse-program funnel
// — #184/#365/#367 — reached a page the property never saw. GSC showed 2.87K
// impressions at pos ~10 while GA4 showed 2 Organic Search sessions total and
// zero /hsk* pagePaths: not a low number, a BLIND one.
//
// Shared here for the same reason PAGE_STYLE is: one source of truth the three
// families import, so a page cannot be generated with the style and without
// the tag. Same measurement id as the SPA shell (ui/public/index.html) so a
// visitor crossing from a word page into the app stays one session — which is
// what makes the issue's AC3 (word page -> / -> wordset_click) measurable at
// all rather than two disjoint visits.
//
// Inline and async, with NO dependency on the SPA bundle: these pages must stay
// self-contained. A page that needed the bundle to report would report nothing
// on exactly the arrivals this exists to count.
export const GA4_ID = 'G-910V8PX54C';
export const GA4_SNIPPET = `<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=${GA4_ID}"></script>
<script>
window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', '${GA4_ID}');
</script>`;

export const PAGE_STYLE = `<style>
${PAGE_TOKENS}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font-latin);
  line-height:1.65;font-size:17px;-webkit-font-smoothing:antialiased}
:lang(zh-Hans),.hanzi-big,td[lang]{font-family:var(--font-hanzi)}
.wrap{max-width:660px;margin:0 auto;padding:16px 20px 72px}
.wrap-wide{max-width:1000px;margin:0 auto;padding:16px 24px 64px}
.site{display:flex;align-items:center;gap:8px;min-height:var(--tap);font-weight:700;letter-spacing:-.01em}
.site a{color:var(--ink);text-decoration:none;display:inline-flex;align-items:center;gap:8px;min-height:var(--tap)}
.site .dot{width:10px;height:10px;border-radius:3px;background:var(--accent);display:inline-block}
.crumbs{display:flex;flex-wrap:wrap;gap:6px;align-items:center;color:var(--muted);font-size:.85rem;margin:2px 0 8px}
.crumbs a{color:var(--muted);display:inline-flex;align-items:center;min-height:var(--tap)}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
h1{font-family:var(--font-display);font-size:clamp(1.5rem,5vw,2rem);line-height:1.2;letter-spacing:-.02em;margin:.5em 0 .3em}
h2{font-family:var(--font-display);font-size:1.05rem;letter-spacing:-.01em;margin:1.6em 0 .6em}
p{margin:0 0 1em}
.word-card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-hero);
  padding:30px 24px 26px;text-align:center;box-shadow:var(--shadow);margin:8px 0 8px}
.hanzi-big{font-size:clamp(4.2rem,26vw,7.5rem);line-height:1;margin:0 0 .12em;letter-spacing:.02em;font-weight:400}
.pinyin{font-family:var(--font-display);font-size:1.5rem;color:var(--ink);margin:0 0 .1em;font-weight:500;white-space:nowrap}
.t1{color:var(--t1);font-weight:700}.t2{color:var(--t2);font-weight:700}.t3{color:var(--t3);font-weight:700}.t4{color:var(--t4);font-weight:700}
.tone-numbers{color:var(--muted);font-size:.95rem;font-weight:400}
.translation{font-size:1.25rem;color:var(--ink);margin:.3em 0 1em}
.actions{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin:0}
.hsk-badge{display:inline-flex;align-items:center;min-height:var(--tap);background:var(--accent-soft);color:var(--accent);
  font-size:.8rem;font-weight:700;letter-spacing:.03em;text-transform:uppercase;
  padding:0 16px;border-radius:var(--r-pill);text-decoration:none}
.cta,button{display:inline-flex;align-items:center;min-height:var(--tap);background:var(--accent);color:var(--accent-ink);
  font:inherit;font-weight:600;border:0;cursor:pointer;
  padding:0 22px;border-radius:var(--r-pill);text-decoration:none;transition:transform .06s ease,filter .15s ease}
.cta:hover,button:hover{filter:brightness(1.05);text-decoration:none}
.cta:active,button:active{transform:translateY(1px)}
.word-card button{background:var(--surface);color:var(--accent);border:1.5px solid var(--line);font-weight:600;padding:0 16px}
mark.w{background:var(--accent-soft);color:var(--accent);border-radius:4px;padding:0 2px}
dl{display:grid;grid-template-columns:auto 1fr;gap:6px 18px;margin:0 0 22px;
  background:var(--surface);border:1px solid var(--line);border-radius:var(--r-card);padding:18px 20px}
dt{color:var(--muted);font-size:.85rem;text-transform:uppercase;letter-spacing:.04em;align-self:center}
dd{margin:0;font-size:1.1rem}
.filter-bar{position:sticky;top:0;z-index:2;background:var(--bg);padding:10px 0 8px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.filter-bar label{flex:1 1 240px;display:flex;align-items:center;gap:10px;min-height:var(--tap);padding:0 16px;
  border:1px solid var(--line);border-radius:var(--r-pill);background:var(--surface);color:var(--muted)}
.filter-bar input{flex:1;min-width:0;border:0;background:transparent;font:inherit;color:var(--ink);outline:none}
.filter-bar input::placeholder{color:var(--muted)}
.filter-count{color:var(--muted);font-size:.9rem}
table{width:100%;border-collapse:separate;border-spacing:0;font-size:1rem;margin:6px 0 20px;
  background:var(--surface);border:1px solid var(--line);border-radius:var(--r-card);overflow:hidden}
thead th{position:sticky;top:62px;z-index:1;background:var(--surface);text-align:left;font-size:.78rem;text-transform:uppercase;letter-spacing:.04em;
  color:var(--muted);padding:12px 14px;border-bottom:1px solid var(--line)}
td{padding:9px 14px;border-top:1px solid var(--line)}
tbody tr:nth-child(odd){background:color-mix(in srgb,var(--surface) 100%,var(--bg) 55%)}
tbody tr:hover{background:var(--accent-soft)}
tbody tr[hidden]{display:none}
td[lang]{font-size:1.3rem}
td a{font-weight:500;color:var(--ink);display:inline-flex;align-items:center;min-height:32px}
ul.other-ways{list-style:none;padding:0;margin:0 0 18px;display:flex;flex-wrap:wrap;gap:8px}
ul.other-ways li{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-item);padding:8px 13px}
ul.sentences{list-style:none;padding:0;margin:0 0 18px;display:grid;gap:10px}
ul.sentences li{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:13px 16px}
ul.sentences li [lang]{font-size:1.25rem;line-height:1.5;display:block}
ul.sentences li em{font-style:normal;color:var(--muted);font-size:.95rem;display:block}
ul.related{list-style:none;padding:0;margin:0 0 18px;display:flex;flex-wrap:wrap;gap:8px}
ul.related a{display:inline-flex;align-items:center;gap:8px;min-height:var(--tap);padding:0 14px;background:var(--surface);
  border:1px solid var(--line);border-radius:var(--r-item);color:var(--ink)}
ul.related a span{color:var(--muted);font-size:.85rem}
ol{padding-left:1.2em}
nav{margin-top:28px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);
  font-size:.95rem;display:grid;grid-template-columns:1fr auto 1fr;gap:8px;align-items:center}
nav a{display:inline-flex;align-items:center;min-height:var(--tap);gap:6px}
nav a[rel="next"]{justify-content:flex-end}
nav a:not([rel]){color:var(--muted);justify-content:center}
.site-footer{margin-top:8px;color:var(--muted);font-size:.9rem;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}
.site-footer a{color:var(--muted);text-decoration:underline;display:inline-flex;align-items:center;min-height:var(--tap)}
</style>`;

/** The shared top wordmark, so every page reads as one product. Kept in the base module for the
 * same reason as PAGE_STYLE — one source of truth the three families share. */
export const SITE_HEADER = `<header class="site"><a href="${ORIGIN}/"><span class="dot"></span> LexiTrail</a></header>`;

/** The shared bottom strip, same one-source-of-truth rationale as SITE_HEADER: every static page
 * shows the support address prominently (pigeon 2026-09-07). */
export const SITE_FOOTER = `<footer class="site-footer"><a href="mailto:support@lexitrail.com">Support: support@lexitrail.com</a><span>&copy; LexiTrail</span></footer>`;

/** `wordset_id` in words.csv is 1..6 for HSK1..6; 7 is the internal `test` set. */
export const isHskWordset = (id) => HSK_LEVELS.includes(Number(id));

const esc = (s) => String(s ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

// revamp-2026-09 — tone-coloured pinyin for STATIC pages, the same table PinyinText.js uses.
//
// Alex, 2026-09-06: "I want multi color rendering of tones in the indexed pages just like in
// practice screen." Emits one <span class="tN"> per toned vowel and leaves everything else as
// text, so the HTML cost is ~20 bytes per syllable. Mirrors PinyinText.getTone character for
// character; hskPages.test.js pins the two tables equal so they cannot drift.
const TONE_MARKS = ['', 'āēīōūǖĀĒĪŌŪǕ', 'áéíóúǘÁÉÍÓÚǗ', 'ǎěǐǒǔǚǍĚǏǑǓǙ', 'àèìòùǜÀÈÌÒÙǛ'];
export const toneOf = (ch) => TONE_MARKS.findIndex((set, i) => i > 0 && set.includes(ch));
export const pinyinHtml = (text) => Array.from(String(text ?? '')).map((ch) => {
  const t = toneOf(ch);
  return t > 0 ? `<span class="t${t}">${esc(ch)}</span>` : esc(ch);
}).join('');

/** Rows -> {1: [...], ... 6: [...]}, each sorted by word_id so output is DETERMINISTIC.
 *
 * Determinism is load-bearing: the drift test compares generated bytes against committed bytes,
 * and a map-iteration-order render would fail it intermittently, which is worse than not having
 * the test — an intermittent guard gets deleted.
 */
export const groupByLevel = (rows) => {
  const out = Object.fromEntries(HSK_LEVELS.map((n) => [n, []]));
  for (const r of rows) {
    const lvl = Number(r.wordset_id);
    if (!isHskWordset(lvl)) continue;
    if (!r.word) continue;
    out[lvl].push({ id: Number(r.word_id), word: r.word, pinyin: r.def1 || '', english: r.def2 || '' });
  }
  for (const n of HSK_LEVELS) out[n].sort((a, b) => a.id - b.id);
  return out;
};

export const pageFilename = (level) => `hsk${level}.html`;
export const pageUrl = (level, origin = ORIGIN) => `${origin}/hsk${level}.html`;

// revamp-2026-09 — the ONE script on a static page, inline and ~600 bytes: a client-side filter
// for the list. hsk6.html is 2,500 rows; without this the page is a scroll, with it every word is
// two keystrokes away. Progressive: the table is complete HTML before the script runs, so a
// crawler and a no-JS reader see the whole list. Matches hanzi, pinyin with OR without tone marks
// (NFD + strip combining marks), and English; hides rows with the `hidden` attribute and updates
// the count. No framework, no fetch, no state outside the DOM.
const FILTER_SCRIPT = `<script>(function(){var i=document.getElementById('q'),c=document.getElementById('n'),r=[].slice.call(document.querySelectorAll('tbody tr'));if(!i)return;function s(t){return t.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase()}var d=r.map(function(x){return s(x.textContent)});i.addEventListener('input',function(){var q=s(i.value.trim()),k=0;r.forEach(function(x,j){var h=q&&d[j].indexOf(q)<0;x.hidden=h;if(!h)k++});c.textContent=k+' shown'})})();</script>`;

/** The full page. Self-canonical, unique title, the whole table, ItemList JSON-LD, one CTA.
 *
 * ⚠️ NO links to per-word pages, though this issue's proposal lists them: those are #184 and do
 * not exist. Linking them now would hand Googlebot ~5,600 soft-404s from the six pages meant to
 * establish the site's crawlability — the opposite of the goal. Add them WITH #184.
 */
export const renderPage = (level, words, origin = ORIGIN) => {
  const url = pageUrl(level, origin);
  const title = `HSK ${level} Vocabulary List — all ${words.length} words with pinyin and English`;
  const desc = `The complete HSK ${level} word list: all ${words.length} words with pinyin and `
    + `English meanings, free and in one page. Practise them with spaced repetition on LexiTrail.`;
  // lexitrail#184: the hanzi links to its own page. The URL is built here rather than imported
  // from wordPages.js, which imports FROM this module -- a circular import for one template string
  // is a worse trade than four duplicated characters. wordPages.test.js pins that the two agree, so
  // they cannot drift silently.
  //
  // 🔴 These links are added WITH the pages, never before. #183 deliberately shipped without them
  // ("Add them WITH #184") because linking pages that do not exist hands Googlebot ~5,000 soft-404s
  // from the six pages meant to establish the site's crawlability -- the exact opposite of the goal.
  const rows = words.map((w, i) => `<tr><td>${i + 1}</td>`
    + `<td lang="zh-Hans"><a href="${origin}/hsk${level}/${encodeURIComponent(w.word)}.html">`
    + `${esc(w.word)}</a></td>`
    + `<td class="pinyin-cell">${pinyinHtml(w.pinyin)}</td><td>${esc(w.english)}</td></tr>`).join('\n');
  // 🔴 `JSON.stringify` does NOT escape `<`, so a `</script>` in the source data would CLOSE this
  // block and everything after it becomes markup. My own escape test caught this before merge:
  // the table cells were escaped and the JSON-LD was not, which is the classic split -- one
  // sink hardened, its sibling forgotten. `\u003c` is valid JSON *and* inert in HTML.
  const jsonSafe = (o) => JSON.stringify(o)
    .replace(/</g, '\\u003c').replace(/>/g, '\\u003e').replace(/&/g, '\\u0026');
  const jsonLd = jsonSafe({
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    name: `HSK ${level} vocabulary list`,
    url,
    numberOfItems: words.length,
    itemListElement: words.map((w, i) => ({
      '@type': 'ListItem', position: i + 1, name: w.word,
      description: `${w.pinyin} — ${w.english}`,
    })),
  });
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(desc)}">
<link rel="canonical" href="${url}">
<meta property="og:type" content="website">
<meta property="og:url" content="${url}">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(desc)}">
<meta property="og:image" content="${origin}/images/og/generated/og-landscape.png">
<meta property="twitter:card" content="summary_large_image">
<meta property="twitter:url" content="${url}">
<meta property="twitter:title" content="${esc(title)}">
<meta property="twitter:description" content="${esc(desc)}">
<meta property="twitter:image" content="${origin}/images/og/generated/og-landscape.png">
<script type="application/ld+json">${jsonLd}</script>
${PAGE_STYLE}
${GA4_SNIPPET}
</head>
<body>
<main class="wrap-wide">
${SITE_HEADER}
<h1>HSK ${level} vocabulary list</h1>
<p>All ${words.length} words with pinyin and English. HSK ${level} is one of the six levels of the
Hanyu Shuiping Kaoshi, China's standardised Chinese proficiency test. Reading a list is not the
same as knowing it: the words that stick are the ones you are asked to recall just as you are about
to forget them. <a href="${origin}/game/${level}/PRACTICE">Practise the HSK ${level} list &rarr;</a></p>
<div class="filter-bar">
<label><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path></svg><input id="q" type="search" autocomplete="off" placeholder="Filter ${words.length} words — hanzi, pinyin or English" aria-label="Filter the word list"></label>
<span class="filter-count" id="n" aria-live="polite">${words.length} shown</span>
<a class="cta" href="${origin}/game/${level}/PRACTICE">Practise &rarr;</a>
</div>
<table>
<thead><tr><th>#</th><th>Hanzi</th><th>Pinyin</th><th>English</th></tr></thead>
<tbody>
${rows}
</tbody>
</table>
<p><a href="${origin}/game/${level}/PRACTICE">Start practising HSK ${level} &rarr;</a></p>
<nav style="display:flex;flex-wrap:wrap;gap:6px 14px"><span>Other levels:</span> ${HSK_LEVELS.filter((n) => n !== level)
    .map((n) => `<a href="${origin}/hsk${n}.html">HSK ${n}</a>`).join(' ')}</nav>
${SITE_FOOTER}
</main>
${FILTER_SCRIPT}
</body>
</html>
`;
};

/** `<url>` entries for sitemap.xml. `lastmod` is passed in, never `new Date()` — a generator that
 * stamps "now" produces a diff on every run and trains reviewers to ignore its output. */
export const renderSitemapEntries = (lastmod, origin = ORIGIN) =>
  HSK_LEVELS.map((n) => `  <url>\n    <loc>${pageUrl(n, origin)}</loc>\n`
    + `    <lastmod>${lastmod}</lastmod>\n    <changefreq>monthly</changefreq>\n`
    + `    <priority>0.8</priority>\n  </url>`).join('\n');
