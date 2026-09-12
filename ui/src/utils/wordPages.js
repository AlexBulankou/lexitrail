// lexitrail#184 — pure renderer for the ~5,600 per-word pages.
//
// Sibling of hskPages.js and deliberately shaped the same way: every decision lives here and is
// unit-tested; ui/scripts/generate-word-pages.js only does I/O. See hskPages.js for why the output
// is COMMITTED rather than built (the Docker build context is `ui/`, so terraform/csv/words.csv —
// one directory UP — does not exist inside the image; a build-time generator would work locally,
// pass review, and produce nothing in production).
//
// revamp-2026-09 — what changed on the page (see docs/design-system.md and the handoff README):
//   * breadcrumb (HSK N › word i of N) under the wordmark, replacing the bare wordmark line
//   * pinyin tone-coloured per vowel (hskPages.pinyinHtml — the practice screen's mapping)
//   * example sentences as cards, with the headword <mark>ed inside the sentence
//   * "Related words" = the neighbours in the level, as chips, so a reader has somewhere to go
//     besides prev/next; these are the SAME URLs the nav already links, so the crawl graph is
//     unchanged and no new soft-404 risk is introduced
//   * prev / list / next as a three-column nav with 44px targets (was inline text, 29px)
//   * 44px HSK badge and CTA (were 29px / 39px)
// Not added, and why: audio (needs a TTS decision — the SPA uses speechSynthesis; a static page
// can too, but that is a product call), character breakdown and stroke order (no data source in
// the repo). The prototypes show where they go.
import { HSK_LEVELS, ORIGIN, isHskWordset, PAGE_STYLE, GA4_SNIPPET, SITE_HEADER, SITE_FOOTER, pinyinHtml } from './hskPages';

const esc = (s) => String(s ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

// 🔴 JSON.stringify does NOT escape `<`, so a `</script>` in source data would close the JSON-LD
// block and everything after it becomes markup. Same sink, same fix, as hskPages.js — kept as its
// own copy rather than imported, because hskPages.js does not export it and widening that module's
// API for one helper is a worse trade than eight duplicated lines.
const jsonSafe = (o) => JSON.stringify(o)
  .replace(/</g, '\\u003c').replace(/>/g, '\\u003e').replace(/&/g, '\\u0026');

/** lexitrail#433 — the 274-character closing paragraph was BYTE-IDENTICAL on all 4,999 word
 * pages (only the level digit and the hanzi varied), and the meta description was identical
 * apart from the level. Half the corpus sits at GSC position 8-11 with 2 clicks per 4,407
 * impressions; a page that is 40% shared boilerplate gives near-duplicate detection a large
 * surface to cluster on.
 *
 * These pools say the same TRUE things — the word, its level, what HSK is, what spaced
 * repetition buys — in different sentences, so the shared n-grams shrink without any page
 * losing information. Wording is varied, not shuffled: reordering clauses leaves the n-grams
 * intact and would not move a duplicate cluster.
 *
 * 🔴 Selection MUST be a pure function of the word. `generate-word-pages.js --check` compares
 * committed HTML byte-for-byte against a fresh render, so anything non-deterministic (a
 * counter, Math.random, a date) makes every page permanently stale and the check unusable. */
const variantIndex = (word, n) => {
  // FNV-1a over the UTF-16 code units. Stable across runs and Node versions; `>>> 0` keeps it
  // unsigned so the modulo cannot go negative on a 32-bit overflow.
  let h = 0x811c9dc5;
  for (let i = 0; i < String(word).length; i += 1) {
    h ^= String(word).charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h % n;
};

/** Closing paragraph. Each takes (hanziSpan, level) and returns the sentences AFTER the
 * gloss clause, which stays common because it is the page's actual subject. */
const CLOSING_VARIANTS = [
  (hz, lv) => `It belongs to the HSK ${lv} vocabulary, one of the six bands of the Hanyu Shuiping `
    + `Kaoshi, China&rsquo;s official Chinese proficiency exam. Recognising ${hz} on a page and `
    + `producing it in conversation are different skills, and only the second holds up when `
    + `someone is waiting for an answer &mdash; so LexiTrail brings it back just as your memory `
    + `of it starts to fade, not on a fixed weekly rota.`,
  (hz, lv) => `You will meet it in HSK ${lv}, a band of the Hanyu Shuiping Kaoshi &mdash; the `
    + `standard test of Chinese proficiency. Most learners can pick ${hz} out of a list long `
    + `before they can reach for it unprompted, and the gap between those two closes only with `
    + `repeated recall. LexiTrail schedules the next sighting from how well you did on the last.`,
  (hz, lv) => `HSK ${lv} is where this word sits in the Hanyu Shuiping Kaoshi, the exam used to `
    + `grade Chinese proficiency. Reading ${hz} and remembering it are not the same achievement: `
    + `the first fades within days unless the second is practised. LexiTrail times each review `
    + `to the edge of forgetting, which is where a repetition is worth the most.`,
  (hz, lv) => `It is part of the HSK ${lv} word list, a level of China&rsquo;s Hanyu Shuiping `
    + `Kaoshi proficiency exam. Knowing what ${hz} means when you see it is a weaker kind of `
    + `knowing than being able to summon it; only the second survives a real conversation. `
    + `LexiTrail spaces your reviews so each one lands when it will do the most work.`,
  (hz, lv) => `This word appears in HSK ${lv}, one level of the Hanyu Shuiping Kaoshi &mdash; `
    + `the proficiency exam most Chinese courses are built around. Passive recognition of ${hz} `
    + `arrives quickly and leaves quickly. Active recall is slower to build and far more durable, `
    + `so LexiTrail keeps returning the word to you at widening intervals rather than on a timer.`,
  (hz, lv) => `HSK ${lv} places it in the Hanyu Shuiping Kaoshi, the standardised measure of `
    + `Chinese proficiency. There is a real difference between having seen ${hz} and being able `
    + `to use it, and cramming a list flatters the first while doing little for the second. `
    + `LexiTrail shows you the word again at the point your recall of it is about to lapse.`,
];

/** Meta description tail. The word, pinyin and gloss lead; only this closer was shared. */
const DESC_VARIANTS = [
  (lv) => `An HSK ${lv} word &mdash; practise it with free spaced-repetition review on LexiTrail.`,
  (lv) => `Part of the HSK ${lv} vocabulary. Learn it by recall, not rereading, free on LexiTrail.`,
  (lv) => `From the HSK ${lv} word list. LexiTrail reviews it just before you forget it &mdash; free.`,
  (lv) => `HSK ${lv} vocabulary, with free spaced-repetition practice and progress tracking on LexiTrail.`,
];

/** The on-disk name for a word page. NOT url-encoded: this is a FILENAME, and the filesystem
 * takes the raw UTF-8 bytes. Encoding here would create a file literally named `%E6%88%91.html`,
 * which then 404s for the encoded request the browser actually sends. Measured 2026-08-29 against
 * `serve` itself: the raw-named file answers `/hsk3/%E6%88%91.html` with 200 and the page body. */
export const wordFilename = (word) => `${word}.html`;

/** The public URL. Percent-ENCODED, because this string goes into href/canonical/sitemap, where a
 * raw multi-byte character is not valid. `encodeURIComponent` is correct per-segment: it escapes
 * `/` too, which a hanzi never contains but a malformed row might. */
export const wordUrl = (level, word, origin = ORIGIN) =>
  `${origin}/hsk${level}/${encodeURIComponent(word)}.html`;

/** Rows -> [{level, id, word, pinyin, english}], sorted by (level, word_id).
 *
 * Determinism is load-bearing for the same reason as hskPages.groupByLevel: the drift test compares
 * generated bytes to committed bytes, and an intermittent guard gets deleted rather than fixed.
 *
 * 🔴 A hanzi can appear TWICE in one level as two SENSES, and the fix is to MERGE them, not to drop
 * one. words.csv carries HSK2 `对` as word_id 301 (`duì`, "to") and 302 (`duì`, "right") — the same
 * character, two meanings, two rows. They render to the same filename, so a first-wins rule would
 * silently keep "to" and lose "right", i.e. drop a meaning AND keep the weaker gloss, with the page
 * count disagreeing with the row count for a reason invisible in the diff.
 *
 * Merging is also the right SEO shape: one hanzi is one thing a person searches for, so it should
 * be one canonical page carrying every sense, not two pages splitting the link equity or one page
 * quietly missing half the answer.
 *
 * `sensesMerged` counts the extra rows folded in, so the generator can print why 5,000 rows became
 * 4,999 pages rather than leaving a discrepancy nobody can explain later.
 */
export const collectWords = (rows) => {
  const byKey = new Map();
  let sensesMerged = 0;
  for (const r of rows) {
    const level = Number(r.wordset_id);
    if (!isHskWordset(level)) continue;
    if (!r.word) continue;
    const key = `${level}/${r.word}`;
    const pinyin = r.def1 || '';
    const english = r.def2 || '';
    const seen = byKey.get(key);
    if (!seen) {
      byKey.set(key, {
        level, id: Number(r.word_id), word: r.word,
        pinyin, english,
        // Kept separate from `english` so the renderer can list senses without re-splitting a
        // joined string -- a join followed by a split is a lossy round trip the moment a gloss
        // legitimately contains the separator.
        senses: [{ pinyin, english }],
      });
      continue;
    }
    sensesMerged += 1;
    seen.senses.push({ pinyin, english });
    // The headline gloss stays the FIRST by word_id; additional senses are additive. Readings are
    // de-duplicated because the common case (`对` -> duì, duì) is one pronunciation, two meanings,
    // and repeating it reads as an error.
    const readings = [...new Set(seen.senses.map((x) => x.pinyin).filter(Boolean))];
    seen.pinyin = readings.join(', ');
    seen.english = seen.senses.map((x) => x.english).filter(Boolean).join('; ');
  }
  const out = [...byKey.values()].sort((a, b) => (a.level - b.level) || (a.id - b.id));
  return { words: out, sensesMerged };
};

/** Bank entries -> Map(hanzi -> [{chinese, pinyin, english}]), for the example-sentence block.
 *
 * `banks` is an ORDERED list of parsed `sentences/sentences-*.json` bodies. The caller sorts the
 * filenames; this function preserves the order it is given and the order within each bank, because
 * the drift test byte-compares generated output to committed output and an intermittent guard gets
 * deleted rather than fixed. Nothing here sorts by content.
 *
 * 🔴 Sentences are deduplicated on the CHINESE text, not on the whole object. The banks are four
 * generated files over an overlapping HSK range, so the same sentence can appear twice with a
 * different English rendering; keeping both would print what reads as an editing mistake on a
 * public page.
 *
 * The join is exact on `word.chinese` against the CSV's `word` column. Measured 2026-08-29:
 * 224 of 224 bank words match a CSV word, 0 misses -- so this block reaches 224 of 4,999 pages
 * (4.5%). That number is the point of the measurement: a join that silently matched nothing would
 * ship a feature that renders on no page at all and still passes every test written against the
 * renderer in isolation.
 */
export const collectExamples = (banks) => {
  const byWord = new Map();
  for (const bank of banks) {
    for (const e of (bank && bank.sentences) || []) {
      const hanzi = e && e.word && e.word.chinese;
      if (!hanzi || !e.chinese) continue;
      if (!byWord.has(hanzi)) byWord.set(hanzi, []);
      const list = byWord.get(hanzi);
      if (list.some((x) => x.chinese === e.chinese)) continue;
      list.push({ chinese: e.chinese, pinyin: e.pinyin || '', english: e.english || '' });
    }
  }
  return byWord;
};

// The headword highlighted inside an example sentence. Escapes first, then marks, so a `<` in the
// data cannot ride in on the mark; a word absent from its own sentence renders unmarked.
const markWord = (sentence, word) => {
  const s = esc(sentence), w = esc(word);
  return w ? s.split(w).join(`<mark class="w">${w}</mark>`) : s;
};

/** One word page. `prev`/`next` are the adjacent words IN THE SAME LEVEL, or null at the ends.
 * `position` / `count` (optional) feed the breadcrumb; `related` (optional, default = the
 * neighbours) feeds the chips.
 *
 * 🔴 The prev/next links are not decoration — they are the CRAWL PATH. Until sitemap.xml carries
 * these ~5,600 URLs, a chain of prev/next from the six level pages is the only way Googlebot can
 * reach a word page at all. They also mean the pages are discoverable in the order a human would
 * read them, which is what makes this a list rather than 5,600 orphans.
 */
export const renderWordPage = (
  w,
  { prev = null, next = null, examples = [], position = null, count = null, related = null } = {},
  origin = ORIGIN,
) => {
  const url = wordUrl(w.level, w.word, origin);
  const senses = w.senses || [{ pinyin: w.pinyin, english: w.english }];
  const levelUrl = `${origin}/hsk${w.level}.html`;
  const gloss = [w.pinyin, w.english].filter(Boolean).join(' — ');
  // lexitrail#368: English-gloss-first. GSC's 28d window shows the ranking queries are
  // "<gloss> in chinese" (English-first searchers, pos ~10-14) — a hanzi-first title like
  // "网球 (wǎngqiú — Tennis) — HSK 4 Chinese word" buries the term the searcher typed and scans
  // as unreadable at a glance, which measured CTR 0.049% on 4,110 impressions. Falls back to the
  // old hanzi-first form when there's no gloss to lead with (the "bare word" case above).
  const title = w.english
    ? `${w.english} in Chinese — ${w.word}${w.pinyin ? ` (${w.pinyin})` : ''} | HSK ${w.level}`
    : `${w.word}${gloss ? ` (${gloss})` : ''} — HSK ${w.level} Chinese word`;
  // The SAME evidence applied to the H1, which #368 left hanzi-only. The searcher types
  // "tennis in chinese"; the title now answers that and the H1 — the strongest on-page signal
  // after it — carried NONE of those words on all 4,999 pages (median GSC position 10.7).
  //
  // 🔴 The hanzi being big and bare was a VISUAL decision, not a semantic one: `.hanzi-big` is the
  // shared card vocabulary (docs/design-system.md §3.1, "dominating the fold") and the gloss
  // landers already prove the class is not tied to the H1 — there `.hanzi-big` is a <p> and the
  // English gloss is the <h1> (glossPages.js). So the fix keeps the visual and moves only the
  // semantics: the H1 WRAPS the three hero lines it used to sit above, as <span>s carrying the
  // same classes, with `.word-h1` in PAGE_STYLE neutralising the h1 element's own typography and
  // margins. Rendered result is unchanged — same order, same sizes, same collapsed margins; a <p>
  // cannot be nested in an <h1> (invalid, and the parser would unnest it), which is why they are
  // spans + `display:block` rather than the original elements.
  //
  // The hanzi keeps `lang="zh-Hans"` on ITS span only, so the gloss is never inside a Chinese
  // lang scope — that would tell a crawler the English text is Chinese, which is the bug this
  // change exists to avoid creating.
  const desc = `${w.word}${w.pinyin ? `, pinyin ${w.pinyin}` : ''}${w.english ? `, means "${w.english}"` : ''}. `
    + DESC_VARIANTS[variantIndex(w.word, DESC_VARIANTS.length)](w.level);
  const jsonLd = jsonSafe({
    '@context': 'https://schema.org',
    '@type': 'DefinedTerm',
    name: w.word,
    url,
    description: gloss,
    inDefinedTermSet: { '@type': 'DefinedTermSet', name: `HSK ${w.level}`, url: levelUrl },
  });
  const chips = (related || [prev, next].filter(Boolean)).map((r) =>
    `<li><a href="${wordUrl(r.level, r.word, origin)}"><span lang="zh-Hans" style="font-size:1.15rem;color:var(--ink)">${esc(r.word)}</span>`
    + `${r.english ? `<span>${esc(r.english)}</span>` : ''}</a></li>`).join('\n');
  const crumb = position && count
    ? `<div class="crumbs"><a href="${levelUrl}">HSK ${w.level}</a><span>&rsaquo;</span><span>${position} of ${count}</span></div>`
    : `<div class="crumbs"><a href="${levelUrl}">HSK ${w.level}</a></div>`;
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(desc)}">
<link rel="canonical" href="${url}">
${prev ? `<link rel="prev" href="${wordUrl(prev.level, prev.word, origin)}">\n` : ''}${next ? `<link rel="next" href="${wordUrl(next.level, next.word, origin)}">\n` : ''}<meta property="og:type" content="article">
<meta property="og:url" content="${url}">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(desc)}">
<meta property="og:image" content="${origin}/images/og/generated/og-landscape.png">
<meta property="twitter:card" content="summary_large_image">
<meta property="twitter:url" content="${url}">
<meta property="twitter:title" content="${esc(title)}">
<meta property="twitter:description" content="${esc(desc)}">
<script type="application/ld+json">${jsonLd}</script>
${PAGE_STYLE}
${GA4_SNIPPET}
</head>
<body>
<main class="wrap">
${SITE_HEADER}
${crumb}
<div class="word-card">
<h1 class="word-h1"><span class="hanzi-big" lang="zh-Hans">${esc(w.word)}</span>
${w.pinyin ? `<span class="pinyin">${pinyinHtml(w.pinyin)}</span>` : ''}
${w.english ? `<span class="translation">${esc(w.english)}</span>` : ''}</h1>
<p class="actions"><a class="hsk-badge" href="${levelUrl}">HSK ${w.level}</a><a class="cta" href="${origin}/game/${w.level}/PRACTICE">Practise with ${esc(w.word)} &rarr;</a></p>
</div>${senses.length > 1 ? `
<h2>Senses</h2>
<ol>
${senses.map((s) => `<li>${s.pinyin ? `${pinyinHtml(s.pinyin)} — ` : ''}${esc(s.english)}</li>`).join('\n')}
</ol>` : ''}${examples.length ? `
<h2>Example sentences</h2>
<ul class="sentences">
${examples.map((x) => `<li><span lang="zh-Hans">${markWord(x.chinese, w.word)}</span>`
    + `${x.pinyin ? `<em>${pinyinHtml(x.pinyin)}</em>` : ''}`
    + `${x.english ? `${esc(x.english)}` : ''}</li>`).join('\n')}
</ul>` : ''}
<p><span lang="zh-Hans">${esc(w.word)}</span>${w.pinyin ? ` is pronounced <em>${pinyinHtml(w.pinyin)}</em>` : ''}${w.english ? ` and means ${senses.length > 1 ? `&ldquo;${esc(senses[0].english)}&rdquo; (and ${senses.length - 1} further sense${senses.length > 2 ? 's' : ''} above)` : `&ldquo;${esc(w.english)}&rdquo;`}` : ''}. ${CLOSING_VARIANTS[variantIndex(w.word, CLOSING_VARIANTS.length)](`<span lang="zh-Hans">${esc(w.word)}</span>`, w.level)}</p>${chips ? `
<h2>Related words</h2>
<ul class="related">
${chips}
</ul>` : ''}
<nav>${prev ? `<a rel="prev" href="${wordUrl(prev.level, prev.word, origin)}">&larr; <span lang="zh-Hans">${esc(prev.word)}</span></a>` : '<span></span>'}<a href="${levelUrl}">HSK ${w.level} list</a>${next ? `<a rel="next" href="${wordUrl(next.level, next.word, origin)}"><span lang="zh-Hans">${esc(next.word)}</span> &rarr;</a>` : '<span></span>'}</nav>
${SITE_FOOTER}
</main>
</body>
</html>
`;
};

/** `<url>` entries for sitemap.xml. `lastmod` is passed in, never `new Date()` — a generator that
 * stamps today's date rewrites every entry on every run and makes the drift test unusable. */
export const renderWordSitemapEntries = (words, lastmod, origin = ORIGIN) =>
  words.map((w) => `  <url>\n    <loc>${wordUrl(w.level, w.word, origin)}</loc>\n`
    + `    <lastmod>${lastmod}</lastmod>\n    <changefreq>monthly</changefreq>\n`
    + `    <priority>0.5</priority>\n  </url>`).join('\n');

export { HSK_LEVELS };

/** The `lastmod` stamped on every word-page sitemap entry. A COMMITTED CONSTANT, bumped by hand
 * when the word content actually changes.
 *
 * 🔴 Not `new Date()`, and not "the date the generator ran". Either would rewrite all 4,999 entries
 * on every run, so the drift test would fail the day after it was written and be deleted rather
 * than fixed -- and a sitemap claiming everything changed today is a freshness signal crawlers
 * learn to discount. Bumping this by hand is the point: it is a claim about the CONTENT, and a
 * human is the only thing that knows whether the content changed.
 *
 * Bumped for the revamp: the pages' content changed (breadcrumb, related words, marked sentences),
 * not just their style.
 */
export const WORD_PAGES_LASTMOD = '2026-09-11';

/** The whole sitemap-words.xml document. Its own file rather than entries appended to sitemap.xml:
 * sitemap.xml is hand-maintained and reviewable at 7 URLs (was 21 until #367
 * dropped the 14 unrenderable SPA routes), and folding 4,999 generated entries
 * into it would make every future edit to it an unreviewable diff. robots.txt declares both, which
 * is the documented alternative to a sitemap index and has fewer moving parts. */
export const renderWordSitemap = (words, lastmod = WORD_PAGES_LASTMOD, origin = ORIGIN) =>
  `<?xml version="1.0" encoding="UTF-8"?>\n`
  + `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n`
  + `${renderWordSitemapEntries(words, lastmod, origin)}\n`
  + `</urlset>\n`;
