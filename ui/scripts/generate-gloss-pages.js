#!/usr/bin/env node
// lexitrail#365 — regenerate ui/public/<slug>.html for the Phase-1 "<gloss> in Chinese" queries.
//
// Thin I/O shell, same shape as generate-word-pages.js: every decision lives in
// ui/src/utils/glossPages.js, which is pure and unit-tested. This file only reads inputs and
// writes files.
//
//   node ui/scripts/generate-gloss-pages.js            # write
//   node ui/scripts/generate-gloss-pages.js --check    # exit 1 if any committed file is stale
const fs = require('fs');
const path = require('path');
const Papa = require('papaparse');

const UI = path.resolve(__dirname, '..');
const CSV = path.resolve(UI, '..', 'terraform', 'csv', 'words.csv');
// A DEDICATED subdirectory, not `sentences/*.json` directly -- generate-word-pages.js globs
// `sentences/sentences-*.json` non-recursively for the per-HANZI pages' example blocks. Keeping
// this file one level down means adding Phase-1 example sentences does not also mark all 4,999
// existing word pages stale, which would be an unrelated regeneration this PR did not review.
const SENTENCES_DIR = path.resolve(UI, '..', 'sentences', 'gloss-phase1');
const OUT = path.resolve(UI, 'public');

// Same eval-and-bind trick as generate-word-pages.js: these utils are ESM (`export const`) for
// CRA/jest; plain `require` cannot consume that syntax, so each file's body is evaluated with its
// exports stripped to bare `const` and bound explicitly. Injected params make a future import
// nobody wires here fail LOUDLY ("X is not defined") instead of resolving to undefined.
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

const hsk = evalModule('hskPages.js',
  ['HSK_LEVELS', 'ORIGIN', 'isHskWordset', 'PAGE_STYLE', 'SITE_HEADER']);
const gp = evalModule('glossPages.js',
  ['PHASE1_QUERIES', 'collectGlossGroup', 'renderGlossPage', 'renderGlossSitemap',
   'GLOSS_PAGES_LASTMOD', 'glossUrl'],
  { HSK_LEVELS: hsk.HSK_LEVELS, ORIGIN: hsk.ORIGIN, isHskWordset: hsk.isHskWordset,
    PAGE_STYLE: hsk.PAGE_STYLE, SITE_HEADER: hsk.SITE_HEADER });

function main() {
  const check = process.argv.includes('--check');
  const rows = Papa.parse(fs.readFileSync(CSV, 'utf8'), { header: true, skipEmptyLines: true }).data;

  const bankFiles = fs.existsSync(SENTENCES_DIR)
    ? fs.readdirSync(SENTENCES_DIR).filter((f) => /^sentences-.*\.json$/.test(f)).sort()
    : [];
  const examplesByWord = new Map();
  for (const f of bankFiles) {
    const bank = JSON.parse(fs.readFileSync(path.join(SENTENCES_DIR, f), 'utf8'));
    for (const e of bank.sentences || []) {
      const hanzi = e && e.word && e.word.chinese;
      if (!hanzi || !e.chinese) continue;
      if (!examplesByWord.has(hanzi)) examplesByWord.set(hanzi, []);
      examplesByWord.get(hanzi).push({ chinese: e.chinese, pinyin: e.pinyin || '', english: e.english || '' });
    }
  }

  let stale = 0;
  let written = 0;
  const generated = [];
  // PHASE 1 SCOPE, printed every run: this is the GSC-proven seed named in the issue, NOT the
  // full top-100-by-impressions export the spec describes -- that export requires Search Console
  // API access this repo does not have. See glossPages.js's header comment for the full account.
  console.log(`note: generating ${gp.PHASE1_QUERIES.length} Phase-1 gloss page(s) -- the issue's `
    + `named 5-query seed, not the full GSC top-100 (no Search Console credentials in this repo; `
    + `flagged to hcl@ on lexitrail#365)`);

  for (const query of gp.PHASE1_QUERIES) {
    const group = gp.collectGlossGroup(rows, query.gloss);
    if (!group) {
      // Per the spec's own phasing logic: "intersected with words we have complete data for". A
      // gloss with no matching word is NOT phase-1 material -- print and skip, never fabricate.
      console.error(`  SKIP ${query.slug}: no word in words.csv has def2 == "${query.gloss}" `
        + `(exact match) -- not in Phase 1`);
      continue;
    }
    const examples = examplesByWord.get(group.primary.word) || [];
    if (!examples.length) {
      // hcl@'s review Q on the PR: does a future drop-in slug with no matching sentence entry
      // get skipped, or ship a thin page? Skipped -- "complete data" (the spec's own phasing
      // filter) means a matching word AND example sentences, not just the word. A thin page here
      // is exactly the "thin-content demotion" risk the phasing exists to avoid, and it is a
      // silent one: nothing else about the page looks wrong.
      console.error(`  SKIP ${query.slug}: matched ${group.primary.word} but has no example `
        + `sentences in ${SENTENCES_DIR} -- not "complete data" per the spec's own phasing `
        + `filter, not in Phase 1 until sentences are added`);
      continue;
    }
    const html = gp.renderGlossPage(query, group, { examples });
    const file = path.join(OUT, `${query.slug}.html`);
    if (check) {
      const committed = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : null;
      if (committed !== html) { stale += 1; console.error(`  stale: ${path.relative(OUT, file)}`); }
    } else {
      fs.writeFileSync(file, html);
      written += 1;
    }
    generated.push(query);
  }

  if (!generated.length) {
    console.error('REFUSING: 0 of the Phase-1 queries matched a word in words.csv -- either the '
      + 'CSV path is wrong or every gloss in PHASE1_QUERIES needs re-checking against def2. '
      + 'Shipping silently here would mean the whole feature generates nothing.');
    process.exit(2);
  }

  const sitemap = gp.renderGlossSitemap(generated, gp.GLOSS_PAGES_LASTMOD);
  const smFile = path.join(OUT, 'sitemap-gloss.xml');
  if (check) {
    const committedSm = fs.existsSync(smFile) ? fs.readFileSync(smFile, 'utf8') : null;
    if (committedSm !== sitemap) { stale += 1; console.error('  stale: sitemap-gloss.xml'); }
  } else {
    fs.writeFileSync(smFile, sitemap);
  }

  if (check) {
    if (stale) {
      console.error(`${stale} gloss page(s) stale or missing — run: node ui/scripts/generate-gloss-pages.js`);
      process.exit(1);
    }
    console.log(`ok: ${generated.length} gloss pages match the CSV + sentence bank`);
    return;
  }
  console.log(`wrote ${written} gloss page(s): ${generated.map((q) => q.slug).join(', ')}`);
  console.log(`wrote sitemap-gloss.xml (${generated.length} urls, lastmod ${gp.GLOSS_PAGES_LASTMOD})`);
}

main();
