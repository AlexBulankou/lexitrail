// lexitrail#365 — "<gloss> in Chinese" landing pages, one per English gloss.
//
// WHY THIS EXISTS. lexitrail.com already ranks ~position 10-11 for dozens of "<word> in chinese"
// queries (2.87K impressions / 4 clicks over 3mo per Search Console) and has NO page matching the
// query — Google is offering the traffic and there is nothing to click. #184's per-word pages
// (wordPages.js) are keyed by HANZI at `/hskN/<hanzi>.html`; these are keyed by GLOSS at the query
// verbatim, root-level (`/clarify-in-chinese`), because that is what the searcher typed and what
// the title/h1 must match exactly to be the obvious click.
//
// Sibling of wordPages.js/hskPages.js and deliberately shaped the same way: every decision lives
// here and is unit-tested; the generator script only does I/O. Same reason the OUTPUT is COMMITTED
// rather than build-time-generated -- the Docker build context is `ui/`, so `terraform/csv/words.csv`
// (one directory up) does not exist inside the image.
//
// PHASE 1 SCOPE (zz1's spec, decided not proposed): the GSC-proven query set, intersected with
// words we have complete data for. The issue body names 5 concrete queries with real impression
// counts (clarify/tennis/vague/reputation/decision); the full top-100-by-impressions GSC export was
// NOT available to the implementer (no Search Console API credentials in this repo, no prior
// integration to reuse -- grepped, found nothing). PHASE1_QUERIES below is that 5-query seed, not
// the full set the spec describes. Widening it to the real top-100 is a data-drop-in, not a code
// change: add rows here (or move this to a JSON file once the export exists) and re-run the
// generator. Flagged to hcl@ on the issue rather than silently treated as "done" -- #365's own
// quality-gate #3 says a scope change comes back to zz1, and this is the honest size of what
// shipped, not a decision to widen or shrink it.
import { HSK_LEVELS, ORIGIN, isHskWordset } from './hskPages';

const esc = (s) => String(s ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

// Same sink, same fix as wordPages.js/hskPages.js -- JSON.stringify does not escape `<`, so a
// `</script>` in source data would close the JSON-LD block early.
const jsonSafe = (o) => JSON.stringify(o)
  .replace(/</g, '\\u003c').replace(/>/g, '\\u003e').replace(/&/g, '\\u0026');

// The GSC-proven seed set (issue body, "The evidence" section). `impressions`/`clicks` are the
// 3-month Search Console figures as reported in the issue, kept here as the paper trail for WHY
// each slug was chosen -- not used by the renderer, read by a human deciding whether to widen this.
export const PHASE1_QUERIES = [
  { slug: 'clarify-in-chinese', gloss: 'clarify', impressions: 32, clicks: 9.7 },
  { slug: 'tennis-in-chinese', gloss: 'tennis', impressions: 32, clicks: 11.2 },
  { slug: 'vague-in-chinese', gloss: 'vague', impressions: 27, clicks: 9.9 },
  { slug: 'reputation-in-chinese', gloss: 'reputation', impressions: 22, clicks: 10.7 },
  { slug: 'decision-in-chinese', gloss: 'decision', impressions: 20, clicks: 10.7 },
];

// ---------------------------------------------------------------------------------------------
// Pinyin tone-number conversion.
//
// The CSV stores one marked-pinyin STRING per word with no syllable spacing ("juédìng", not
// "jué dìng"), and Mandarin syllables map 1:1 to hanzi characters with very few exceptions (none
// in the Phase-1 set). So syllable COUNT is free (count hanzi characters); syllable BOUNDARIES are
// not, and guessing them wrong would put a tone digit at the wrong index on a page whose whole
// point is correctness at position ~10 (#365's quality gate #1).
//
// Rather than a full phonetic parser, this does the same thing a Pinyin input method does: greedy
// initial + a closed table of valid WRITTEN finals (the spellings that appear after an initial --
// "iu" not the phonetic "iou", etc.), backtracking word-break style so a locally-greedy wrong guess
// doesn't strand the rest of the string. If no split of the required LENGTH exists, this returns
// null rather than a guess -- the caller must render NOTHING rather than a wrong number, same
// discipline as `unresolvable_option_letters`'s empty-set-means-could-not-tell in my-hermes.
const TONE_MARKS = {
  ā: ['a', 1], á: ['a', 2], ǎ: ['a', 3], à: ['a', 4],
  ē: ['e', 1], é: ['e', 2], ě: ['e', 3], è: ['e', 4],
  ī: ['i', 1], í: ['i', 2], ǐ: ['i', 3], ì: ['i', 4],
  ō: ['o', 1], ó: ['o', 2], ǒ: ['o', 3], ò: ['o', 4],
  ū: ['u', 1], ú: ['u', 2], ǔ: ['u', 3], ù: ['u', 4],
  ǖ: ['ü', 1], ǘ: ['ü', 2], ǚ: ['ü', 3], ǜ: ['ü', 4],
};

/** Marked pinyin -> {plain, tones}: `plain` has diacritics stripped to their base vowel, `tones`
 * is a parallel array of tone digits (or null) at the position of each toned vowel in `plain`. */
const toPlainWithTones = (pinyin) => {
  let plain = '';
  const tonePositions = [];
  for (const ch of pinyin) {
    const hit = TONE_MARKS[ch] || TONE_MARKS[ch.toLowerCase()];
    if (hit) {
      const [base, tone] = hit;
      tonePositions.push({ index: plain.length, tone });
      plain += ch === ch.toLowerCase() ? base : base.toUpperCase();
    } else {
      plain += ch;
    }
  }
  return { plain, tonePositions };
};

// Longest-first so a greedy try consumes the maximal valid chunk before backtracking.
const INITIALS = ['zh', 'ch', 'sh', 'b', 'p', 'm', 'f', 'd', 't', 'n', 'l',
  'g', 'k', 'h', 'j', 'q', 'x', 'r', 'z', 'c', 's', 'y', 'w'].sort((a, b) => b.length - a.length);
const FINALS = ['iang', 'iong', 'uang',
  'ang', 'eng', 'ing', 'ong', 'ai', 'ei', 'ao', 'ou', 'an', 'en',
  'ia', 'ie', 'iu', 'in', 'ua', 'uo', 'ui', 'uan', 'un', 'ue', 'er',
  'a', 'o', 'e', 'i', 'u', 'v'].sort((a, b) => b.length - a.length);

const norm = (s) => s.toLowerCase().replace(/ü/g, 'v');

/** All (initial, final) splits of `s` that consume it ENTIRELY as one syllable, i.e. every valid
 * way to read `s` as a single Pinyin syllable. Returns the list of split lengths of the INITIAL
 * (0 for a vowel-only syllable like "an"), for the caller to try longest-first. */
function syllableSplits(s) {
  const lower = norm(s);
  const out = [];
  for (const init of ['', ...INITIALS]) {
    if (!lower.startsWith(init)) continue;
    const rest = lower.slice(init.length);
    if (FINALS.includes(rest)) out.push(init.length);
  }
  return out;
}

/** Backtracking word-break: can `s` be read as exactly `n` valid Pinyin syllables? Returns the
 * array of syllable-end offsets (into `s`) on success, or null. Memoized on (start) only -- n is
 * fixed for the whole call, so a start position either can or cannot reach the end in the
 * remaining count, independent of how we got there. */
function segmentIntoSyllables(s, n) {
  const lower = norm(s);
  const memo = new Map();
  const rec = (start, remaining) => {
    if (remaining === 0) return start === lower.length ? [] : null;
    const key = `${start}:${remaining}`;
    if (memo.has(key)) return memo.get(key);
    // Try every prefix that is itself a valid whole syllable, longest first (greedy-correct
    // instinct, but backtracking means a wrong longest guess is just abandoned, not fatal).
    for (let end = lower.length - (remaining - 1); end > start; end -= 1) {
      const piece = lower.slice(start, end);
      if (syllableSplits(piece).length === 0) continue;
      const tail = rec(end, remaining - 1);
      if (tail !== null) {
        const result = [end, ...tail];
        memo.set(key, result);
        return result;
      }
    }
    memo.set(key, null);
    return null;
  };
  return rec(0, n);
}

/** `pinyin`, `syllableCount` -> numbered form ("jue2 ding4") or null when no valid segmentation of
 * that exact length exists. A segment with no tone mark in it is neutral tone, digit 5. */
export const toNumberedPinyin = (pinyin, syllableCount) => {
  const { plain, tonePositions } = toPlainWithTones(pinyin);
  const cleanedForSplit = plain.replace(/[^a-zA-Zü]/g, '');
  if (cleanedForSplit.length !== plain.length) return null; // spaces/punctuation: not our shape
  const ends = segmentIntoSyllables(plain, syllableCount);
  if (!ends) return null;
  const starts = [0, ...ends.slice(0, -1)];
  return starts.map((start, i) => {
    const end = ends[i];
    const seg = plain.slice(start, end);
    const marks = tonePositions.filter((t) => t.index >= start && t.index < end);
    const tone = marks.length ? marks[0].tone : 5;
    return `${seg}${tone}`;
  }).join(' ');
};

// ---------------------------------------------------------------------------------------------
// Gloss grouping.

/** rows, gloss -> {primary, alternates} | null. Match is EXACT (case/whitespace-insensitive)
 * against a single `;`-or-`,`-separated sense in `def2` -- NOT a substring match. "clarify" must
 * not pull in "clarify one's position": that is a different phrase a searcher for "clarify" did
 * not type, and padding the page with it would be the thin/wrong content #365's quality gate #1
 * calls worse than no page.
 *
 * Among matches, PRIMARY is the lowest HSK level (ties broken by word_id) -- the word a learner
 * is statistically most likely to already be studying, and the one whose CTA buttons (HSK1-3) are
 * most likely to be relevant. Everything else is an ALTERNATE, for the "other ways to say it" row.
 */
export const collectGlossGroup = (rows, gloss) => {
  const target = gloss.trim().toLowerCase();
  const matches = [];
  for (const r of rows) {
    const level = Number(r.wordset_id);
    if (!isHskWordset(level)) continue;
    if (!r.word) continue;
    const senses = String(r.def2 || '').split(/[;,]/).map((s) => s.trim().toLowerCase());
    if (!senses.includes(target)) continue;
    matches.push({ level, id: Number(r.word_id), word: r.word, pinyin: r.def1 || '', english: r.def2 || '' });
  }
  if (!matches.length) return null;
  matches.sort((a, b) => (a.level - b.level) || (a.id - b.id));
  const [primary, ...alternates] = matches;
  return { primary, alternates };
};

// ---------------------------------------------------------------------------------------------
// Rendering.

const HSK_CTA_LEVELS = [1, 2, 3]; // fixed per the spec -- not the word's own level.

// 🔴 URL carries `.html`, and that is a DEVIATION from the issue's literal "slug = the query
// verbatim at ROOT: lexitrail.com/clarify-in-chinese" (no extension) -- flagged rather than
// silently followed or silently overridden. `serve.json` sets `cleanUrls: false` (hskPages.js's
// header documents why: a real prod incident where an extensionless route fell through to
// `serve-handler`'s default directory listing, #342). Every other static lander in this repo
// (`/hsk1.html`, `/hsk1/我.html`) is canonical AT its `.html` filename, with an explicit 301 from
// the bare path for humans/bio-links. This follows that same pattern for consistency with the
// existing infra rather than opening a second URL convention on the same site -- see the matching
// `serve.json` redirects added alongside this. hcl@: confirm or override on lexitrail#365.
export const glossUrl = (slug, origin = ORIGIN) => `${origin}/${slug}.html`;

const otherWaysRow = (alternates, origin) => {
  if (!alternates.length) return '';
  const items = alternates.map((a) => {
    const gloss = [a.pinyin, a.english].filter(Boolean).join(' — ');
    const wordUrl = `${origin}/hsk${a.level}/${encodeURIComponent(a.word)}.html`;
    return `<li><a href="${wordUrl}"><span lang="zh-Hans">${esc(a.word)}</span> `
      + `(${esc(gloss)}, HSK ${a.level})</a></li>`;
  }).join('\n');
  return `\n<h2>Other ways to say it</h2>\n<ul class="other-ways">\n${items}\n</ul>`;
};

const exampleBlock = (examples) => {
  if (!examples.length) return '';
  return `\n<h2>Example sentences</h2>\n<ul>\n${examples.map((x) =>
    `<li><span lang="zh-Hans">${esc(x.chinese)}</span>`
    + `${x.pinyin ? `<br><em>${esc(x.pinyin)}</em>` : ''}`
    + `${x.english ? `<br>${esc(x.english)}` : ''}</li>`).join('\n')}\n</ul>`;
};

// Vanilla-JS audio button: these pages are plain static HTML with no React runtime, so the CTA
// reuses the SAME mechanism `ui/src/utils/speak.js` uses (Web Speech API, zh-CN, rate 0.85) rather
// than a per-word audio ASSET -- there is no server-side TTS pipeline in this repo (grepped;
// nothing under backend/ or scripts/ generates or serves word audio). Flagged to hcl@ on the issue:
// the spec's "reuse existing per-word TTS assets" line assumes an asset pipeline that does not
// exist; this reuses the existing PLAYBACK mechanism instead, which is the closest true reading of
// "existing path". No LCP cost either way -- there is no file to lazy-load, just a click handler.
const AUDIO_BUTTON_SCRIPT = `function ltSpeak(t){if(!window.speechSynthesis)return;`
  + `var u=new SpeechSynthesisUtterance(t);u.lang='zh-CN';u.rate=0.85;`
  + `window.speechSynthesis.cancel();window.speechSynthesis.speak(u);}`;

export const renderGlossPage = (query, group, { examples = [], origin = ORIGIN } = {}) => {
  const { slug, gloss } = query;
  const { primary, alternates } = group;
  const url = glossUrl(slug, origin);
  const numbered = toNumberedPinyin(primary.pinyin, [...primary.word].length);
  const levelUrl = `${origin}/hsk${primary.level}.html`;
  const title = `${gloss[0].toUpperCase()}${gloss.slice(1)} in Chinese`;
  const desc = `How to say "${gloss}" in Chinese: ${primary.word} (${primary.pinyin}). `
    + `An HSK ${primary.level} word, with example sentences and audio. Free on LexiTrail.`;
  const jsonLd = jsonSafe({
    '@context': 'https://schema.org',
    '@type': 'DefinedTerm',
    name: primary.word,
    url,
    description: [primary.pinyin, primary.english].filter(Boolean).join(' — '),
    inDefinedTermSet: { '@type': 'DefinedTermSet', name: `HSK ${primary.level}`, url: levelUrl },
  });
  const ctaRow = HSK_CTA_LEVELS.map((n) =>
    `<a class="hsk-cta" href="${origin}/game/${n}/PRACTICE">HSK ${n} &rarr;</a>`).join(' ');
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(desc)}">
<link rel="canonical" href="${url}">
<meta property="og:type" content="article">
<meta property="og:url" content="${url}">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(desc)}">
<meta property="og:image" content="${origin}/images/og/generated/og-landscape.png">
<meta property="twitter:card" content="summary_large_image">
<meta property="twitter:url" content="${url}">
<meta property="twitter:title" content="${esc(title)}">
<meta property="twitter:description" content="${esc(desc)}">
<script type="application/ld+json">${jsonLd}</script>
<script>${AUDIO_BUTTON_SCRIPT}</script>
</head>
<body>
<h1>${esc(title)}</h1>
<div class="word-card">
<p class="hanzi-big" lang="zh-Hans">${esc(primary.word)}</p>
<p class="pinyin">${esc(primary.pinyin)}${numbered ? ` <span class="tone-numbers">(${esc(numbered)})</span>` : ''}</p>
<p class="translation">${esc(primary.english)}</p>
<p><span class="hsk-badge">HSK ${primary.level}</span>
<button type="button" onclick="ltSpeak('${primary.word.replace(/'/g, "\\'")}')">&#128266; Play audio</button></p>
</div>${exampleBlock(examples)}${otherWaysRow(alternates, origin)}
<h2>Practise it</h2>
<p>${ctaRow}</p>
<nav><a href="${levelUrl}">HSK ${primary.level} word list</a> &middot; <a href="${origin}/">LexiTrail home</a></nav>
</body>
</html>
`;
};

export const renderGlossSitemapEntries = (queries, lastmod, origin = ORIGIN) =>
  queries.map((q) => `  <url>\n    <loc>${glossUrl(q.slug, origin)}</loc>\n`
    + `    <lastmod>${lastmod}</lastmod>\n    <changefreq>monthly</changefreq>\n`
    + `    <priority>0.7</priority>\n  </url>`).join('\n');

// A committed constant, same reasoning as wordPages.WORD_PAGES_LASTMOD -- bumped by hand when the
// content actually changes, never `new Date()`.
export const GLOSS_PAGES_LASTMOD = '2026-09-05';

export const renderGlossSitemap = (queries, lastmod = GLOSS_PAGES_LASTMOD, origin = ORIGIN) =>
  `<?xml version="1.0" encoding="UTF-8"?>\n`
  + `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n`
  + `${renderGlossSitemapEntries(queries, lastmod, origin)}\n`
  + `</urlset>\n`;

export { HSK_LEVELS };
