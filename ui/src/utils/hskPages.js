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

export const HSK_LEVELS = [1, 2, 3, 4, 5, 6];

export const ORIGIN = 'https://lexitrail.com';

// lexitrail#369 — the shared, INLINE stylesheet for every static page (hsk list, per-word, gloss).
//
// 🔴 INLINE ON PURPOSE, not a <link>. These files are served as-is by serve-handler and are the
// crawlable half of the site; a stylesheet <link> would be a second request that can 404, mismatch
// the SPA's hashed bundle, or arrive after first paint — the exact "broken styles" this fixes. A
// self-contained <style> renders correctly the instant the HTML lands, for a crawler and a human
// alike. It lives HERE (the base module both wordPages.js and glossPages.js import) so the three
// page families cannot drift apart; the generate scripts inject it the same way they inject ORIGIN,
// and that wiring fails LOUDLY if a script forgets it.
//
// Design vocabulary is the gloss page's: .word-card / .hanzi-big / .pinyin / .translation /
// .hsk-badge, now shared by all three so a share of any of them looks like the same product.
export const PAGE_STYLE = `<style>
:root{color-scheme:light dark;
  --bg:#fbf9f4;--surface:#fff;--ink:#1d1a16;--muted:#6d6558;--line:#eae3d6;
  --accent:#b23b2e;--accent-ink:#fff;--accent-soft:#fbeeeb;--shadow:0 1px 2px rgba(40,30,20,.06),0 8px 24px rgba(40,30,20,.06)}
@media (prefers-color-scheme:dark){:root{
  --bg:#141310;--surface:#1f1c17;--ink:#f2ede2;--muted:#a79e8e;--line:#332f27;
  --accent:#e6796a;--accent-ink:#1a0f0c;--accent-soft:#2b1d19;--shadow:0 1px 2px rgba(0,0,0,.3),0 10px 30px rgba(0,0,0,.35)}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  line-height:1.65;font-size:17px;-webkit-font-smoothing:antialiased}
:lang(zh-Hans),.hanzi-big,td[lang]{font-family:"Noto Serif SC","Songti SC","STSong","Source Han Serif SC","SimSun",serif}
.wrap{max-width:660px;margin:0 auto;padding:20px 20px 72px}
.site{display:flex;align-items:center;gap:8px;padding:18px 0 8px;font-weight:700;letter-spacing:-.01em}
.site a{color:var(--ink);text-decoration:none}
.site .dot{width:10px;height:10px;border-radius:3px;background:var(--accent);display:inline-block}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
h1{font-size:clamp(1.5rem,5vw,2rem);line-height:1.2;letter-spacing:-.02em;margin:.6em 0 .4em}
h2{font-size:1.15rem;letter-spacing:-.01em;margin:1.8em 0 .5em}
p{margin:0 0 1em}
.word-card{background:var(--surface);border:1px solid var(--line);border-radius:20px;
  padding:34px 28px 30px;text-align:center;box-shadow:var(--shadow);margin:8px 0 26px}
.hanzi-big{font-size:clamp(4.2rem,26vw,7.5rem);line-height:1;margin:0 0 .12em;letter-spacing:.02em}
.pinyin{font-size:1.5rem;color:var(--accent);margin:0 0 .2em;font-weight:500}
.tone-numbers{color:var(--muted);font-size:1rem;font-weight:400}
.translation{font-size:1.25rem;color:var(--ink);margin:0 0 .8em}
.hsk-badge{display:inline-block;background:var(--accent-soft);color:var(--accent);
  font-size:.8rem;font-weight:700;letter-spacing:.03em;text-transform:uppercase;
  padding:5px 11px;border-radius:999px;text-decoration:none}
.cta,button{display:inline-block;background:var(--accent);color:var(--accent-ink);
  font:inherit;font-weight:600;border:0;cursor:pointer;
  padding:13px 22px;border-radius:999px;text-decoration:none;transition:transform .06s ease,filter .15s ease}
.cta:hover,button:hover{filter:brightness(1.05);text-decoration:none}
.cta:active,button:active{transform:translateY(1px)}
.word-card button{margin-top:6px;background:var(--surface);color:var(--accent);border:1.5px solid var(--line);font-weight:600;padding:9px 16px}
dl{display:grid;grid-template-columns:auto 1fr;gap:6px 18px;margin:0 0 22px;
  background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:18px 20px}
dt{color:var(--muted);font-size:.85rem;text-transform:uppercase;letter-spacing:.04em;align-self:center}
dd{margin:0;font-size:1.1rem}
table{width:100%;border-collapse:collapse;font-size:1rem;margin:8px 0 20px;
  background:var(--surface);border:1px solid var(--line);border-radius:16px;overflow:hidden}
thead th{text-align:left;font-size:.78rem;text-transform:uppercase;letter-spacing:.04em;
  color:var(--muted);padding:12px 14px;border-bottom:1px solid var(--line)}
td{padding:11px 14px;border-top:1px solid var(--line)}
tbody tr:nth-child(odd){background:color-mix(in srgb,var(--surface) 100%,var(--bg) 55%)}
td[lang]{font-size:1.3rem}
td a{font-weight:500}
ul.other-ways{list-style:none;padding:0;margin:0 0 18px;display:flex;flex-wrap:wrap;gap:8px}
ul.other-ways li{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:8px 13px}
h2 + ul:not(.other-ways){list-style:none;padding:0;margin:0 0 18px}
h2 + ul:not(.other-ways) li{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:13px 16px;margin:0 0 10px}
h2 + ul:not(.other-ways) em{color:var(--accent);font-style:normal}
nav{margin-top:30px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);
  font-size:.95rem;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}
</style>`;

/** The shared top wordmark, so every page reads as one product. Kept in the base module for the
 * same reason as PAGE_STYLE — one source of truth the three families share. */
export const SITE_HEADER = `<header class="site"><a href="${ORIGIN}/"><span class="dot"></span> LexiTrail</a></header>`;

/** `wordset_id` in words.csv is 1..6 for HSK1..6; 7 is the internal `test` set. */
export const isHskWordset = (id) => HSK_LEVELS.includes(Number(id));

const esc = (s) => String(s ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

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
    + `<td>${esc(w.pinyin)}</td><td>${esc(w.english)}</td></tr>`).join('\n');
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
</head>
<body>
${SITE_HEADER}
<main class="wrap">
<h1>HSK ${level} vocabulary list</h1>
<p>This page lists every word in the HSK ${level} vocabulary — ${words.length} entries, each with
its simplified hanzi, pinyin and English meaning. HSK ${level} is one of the six levels of the
Hanyu Shuiping Kaoshi, China's standardised Chinese proficiency test. Reading a list is not the
same as knowing it: the words that stick are the ones you are asked to recall just as you are about
to forget them. LexiTrail drills this list with spaced repetition, free and without an account, so
you can start on the words below straight away.</p>
<p><a href="${origin}/game/${level}/PRACTICE">Practise the HSK ${level} list now &rarr;</a></p>
<table>
<thead><tr><th>#</th><th>Hanzi</th><th>Pinyin</th><th>English</th></tr></thead>
<tbody>
${rows}
</tbody>
</table>
<p><a href="${origin}/game/${level}/PRACTICE">Start practising HSK ${level} &rarr;</a></p>
<nav><p>Other levels: ${HSK_LEVELS.filter((n) => n !== level)
    .map((n) => `<a href="${origin}/hsk${n}.html">HSK ${n}</a>`).join(' · ')}</p></nav>
</main>
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
