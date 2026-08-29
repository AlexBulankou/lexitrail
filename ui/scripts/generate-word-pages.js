#!/usr/bin/env node
// lexitrail#184 — regenerate ui/public/hsk{1..6}/<hanzi>.html from terraform/csv/words.csv.
//
// A THIN SHELL on purpose, exactly like generate-hsk-pages.js: every decision lives in
// ui/src/utils/wordPages.js, which is pure and unit-tested. This file only does I/O.
//
// 🔴 WHY THE OUTPUT IS COMMITTED RATHER THAN BUILT. The Docker build context is `ui/`
// (`gcloud builds submit ui/`), so `terraform/csv/words.csv` — one directory UP — does not exist
// inside the image. A build-time generator would work locally, pass review, and produce nothing in
// production. That is not a hypothetical: lexitrail#184's own Proposal says "extend the same
// build-time generator", and the generator it names says in its header that it cannot be one.
//
//   node ui/scripts/generate-word-pages.js            # write
//   node ui/scripts/generate-word-pages.js --check    # exit 1 if ANY committed file is stale
//
// `--check` is EXHAUSTIVE where the jest drift test samples: 5,000 byte-compares are too slow for
// every CI run but are exactly right for a pre-merge gate, and a sampled guard that nobody knows is
// sampled is worse than one that says so.
const fs = require('fs');
const path = require('path');
const Papa = require('papaparse');

const UI = path.resolve(__dirname, '..');
const CSV = path.resolve(UI, '..', 'terraform', 'csv', 'words.csv');
// lexitrail#184 AC1: the example-sentence corpus. Same reason as the CSV for why the output is
// COMMITTED -- `sentences/` is one directory UP from the Docker build context, so a build-time
// read produces nothing in production.
const SENTENCES_DIR = path.resolve(UI, '..', 'sentences');
const OUT = path.resolve(UI, 'public');

// hskPages.js and wordPages.js are ESM (`export const`) because CRA/jest consume them that way;
// plain `require` cannot. Evaluate each body and bind the exports EXPLICITLY.
//
// 🔴 The obvious transform -- `export const X` -> `exports.X` -- is WRONG (generate-hsk-pages.js
// shipped it for one run before it threw): it rewrites the DECLARATIONS, so every internal
// reference becomes undefined. Strip the keyword, keep the consts, then assign.
//
// wordPages.js additionally IMPORTS from hskPages.js. The import line is stripped and the needed
// bindings are injected as parameters instead — so a new import that nobody wires here fails LOUDLY
// as "X is not defined" at eval time, rather than arriving as undefined three steps later.
const evalModule = (file, exportNames, injected = {}) => {
  const src = fs.readFileSync(path.resolve(UI, 'src', 'utils', file), 'utf8')
    .replace(/^import .*?;$/gm, '')
    .replace(/^export \{[^}]*\};$/gm, '')
    .replace(/^export /gm, '');
  const mod = {};
  const names = Object.keys(injected);
  // eslint-disable-next-line no-new-func
  new Function('exports', ...names,
    `${src}\nObject.assign(exports, { ${exportNames.join(', ')} });`)(
    mod, ...names.map((n) => injected[n]));
  return mod;
};

const hsk = evalModule('hskPages.js', [
  'HSK_LEVELS', 'ORIGIN', 'isHskWordset', 'groupByLevel',
  'pageFilename', 'pageUrl', 'renderPage', 'renderSitemapEntries']);
const wp = evalModule('wordPages.js',
  ['wordFilename', 'wordUrl', 'collectWords', 'renderWordPage', 'renderWordSitemapEntries',
   'renderWordSitemap', 'WORD_PAGES_LASTMOD', 'collectExamples'],
  { HSK_LEVELS: hsk.HSK_LEVELS, ORIGIN: hsk.ORIGIN, isHskWordset: hsk.isHskWordset });

function main() {
  const check = process.argv.includes('--check');
  const rows = Papa.parse(fs.readFileSync(CSV, 'utf8'), { header: true, skipEmptyLines: true }).data;
  const { words, sensesMerged } = wp.collectWords(rows);

  // Filenames sorted so the bank ORDER is stable across machines: readdir order is not
  // guaranteed, and an unstable order would rewrite pages on every run and make --check
  // fail for a reason that has nothing to do with the content.
  const bankFiles = fs.readdirSync(SENTENCES_DIR)
    .filter((f) => /^sentences-.*\.json$/.test(f)).sort();
  const banks = bankFiles.map((f) =>
    JSON.parse(fs.readFileSync(path.join(SENTENCES_DIR, f), 'utf8')));
  const examplesByWord = wp.collectExamples(banks);
  // Printed, never silent: this join reaching ZERO words would render a feature on no page at
  // all while every renderer test still passed. The number is the control.
  const covered = words.filter((w) => (examplesByWord.get(w.word) || []).length).length;
  console.log(`note: ${bankFiles.length} sentence bank(s), ${examplesByWord.size} word(s) with `
    + `examples -> ${covered} of ${words.length} pages carry an Example sentences block`);
  if (covered === 0) {
    console.error('REFUSING: the sentence join matched 0 pages. Either sentences/ is empty or\n'
      + 'the bank word key no longer matches words.csv `word`. Shipping silently here would\n'
      + 'remove every example from the live pages with a clean exit code.');
    process.exit(2);
  }

  // Reported, never silent: merged senses make the PAGE count disagree with the ROW count, and a
  // discrepancy nobody prints is one nobody can explain later.
  if (sensesMerged) {
    console.log(`note: ${sensesMerged} extra sense row(s) merged into an existing word page `
      + `(e.g. HSK2 对 = "to" + "right") — ${words.length} pages from ${words.length + sensesMerged} rows`);
  }

  const byLevel = new Map();
  for (const w of words) {
    if (!byLevel.has(w.level)) byLevel.set(w.level, []);
    byLevel.get(w.level).push(w);
  }

  let stale = 0;
  let written = 0;
  for (const level of hsk.HSK_LEVELS) {
    const lvl = byLevel.get(level) || [];
    const dir = path.join(OUT, `hsk${level}`);
    if (!check) fs.mkdirSync(dir, { recursive: true });
    for (let i = 0; i < lvl.length; i += 1) {
      const html = wp.renderWordPage(lvl[i], {
        prev: lvl[i - 1] || null,
        next: lvl[i + 1] || null,
        examples: examplesByWord.get(lvl[i].word) || [],
      });
      const file = path.join(dir, wp.wordFilename(lvl[i].word));
      if (check) {
        // A MISSING file is stale too — reading it would throw, and a generator whose check mode
        // crashes on the very condition it exists to report is not a check.
        const committed = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : null;
        if (committed !== html) { stale += 1; if (stale <= 5) console.error(`  stale: ${path.relative(OUT, file)}`); }
      } else {
        fs.writeFileSync(file, html);
        written += 1;
      }
    }
  }

  // sitemap-words.xml — its own file, declared alongside sitemap.xml in robots.txt.
  const sitemap = wp.renderWordSitemap(words, wp.WORD_PAGES_LASTMOD);
  const smFile = path.join(OUT, 'sitemap-words.xml');
  if (check) {
    const committedSm = fs.existsSync(smFile) ? fs.readFileSync(smFile, 'utf8') : null;
    if (committedSm !== sitemap) { stale += 1; console.error('  stale: sitemap-words.xml'); }
  } else {
    fs.writeFileSync(smFile, sitemap);
  }

  if (check) {
    if (stale) {
      console.error(`${stale} word page(s) stale or missing — run: node ui/scripts/generate-word-pages.js`);
      process.exit(1);
    }
    console.log(`ok: ${words.length} word pages match the CSV`);
    return;
  }
  console.log(`wrote ${written} word pages across ${hsk.HSK_LEVELS.length} levels`);
  console.log(`wrote sitemap-words.xml (${words.length} urls, lastmod ${wp.WORD_PAGES_LASTMOD})`);
}

main();
