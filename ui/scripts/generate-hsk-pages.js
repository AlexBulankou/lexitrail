#!/usr/bin/env node
// lexitrail#183 — regenerate ui/public/hsk{1..6}.html from terraform/csv/words.csv.
//
// A THIN SHELL on purpose: every decision lives in ui/src/utils/hskPages.js, which is pure and
// unit-tested. This file only does I/O.
//
// 🔴 WHY THE OUTPUT IS COMMITTED RATHER THAN BUILT. The Docker build context is `ui/`
// (`gcloud builds submit ui/`), so `terraform/csv/words.csv` — one directory UP — does not exist
// inside the image. A build-time generator would work locally, pass review, and produce nothing in
// production. Committing the artifact also puts the actual indexed copy in the diff, which for
// SEO content is the thing a reviewer should be reading.
//
// Drift is guarded: hskPages.test.js regenerates from the CSV and compares against the committed
// bytes. Run this after editing words.csv or the renderer, and commit the result.
//
//   node ui/scripts/generate-hsk-pages.js            # write
//   node ui/scripts/generate-hsk-pages.js --check    # exit 1 if the committed files are stale
const fs = require('fs');
const path = require('path');
const Papa = require('papaparse');

const UI = path.resolve(__dirname, '..');
const CSV = path.resolve(UI, '..', 'terraform', 'csv', 'words.csv');
const OUT = path.resolve(UI, 'public');

// hskPages.js is ESM (`export const`) because CRA/jest consume it that way; plain `require` cannot.
// So evaluate its body and bind the exports EXPLICITLY.
//
// 🔴 The obvious transform -- `export const X` -> `exports.X` -- is WRONG and I shipped it for one
// run before it threw: it rewrites the DECLARATIONS, so every internal reference (`HSK_LEVELS`
// inside `groupByLevel`) becomes undefined. Strip the keyword, keep the consts, then assign.
//
// The export list is spelled out rather than scraped: a new export that nobody adds here fails
// LOUDLY at the call site instead of arriving as `undefined is not a function` three steps later.
const src = fs.readFileSync(path.resolve(UI, 'src', 'utils', 'hskPages.js'), 'utf8');
const mod = {};
// eslint-disable-next-line no-new-func
new Function('exports', src.replace(/^export /gm, '') + `
Object.assign(exports, { HSK_LEVELS, ORIGIN, isHskWordset, groupByLevel,
                         pageFilename, pageUrl, renderPage, renderSitemapEntries });`)(mod);

function main() {
  const check = process.argv.includes('--check');
  const rows = Papa.parse(fs.readFileSync(CSV, 'utf8'), { header: true, skipEmptyLines: true }).data;
  const byLevel = mod.groupByLevel(rows);
  let stale = 0;
  for (const level of mod.HSK_LEVELS) {
    const html = mod.renderPage(level, byLevel[level]);
    const dest = path.join(OUT, mod.pageFilename(level));
    const current = fs.existsSync(dest) ? fs.readFileSync(dest, 'utf8') : null;
    if (current === html) { console.log(`ok    ${mod.pageFilename(level)}  ${byLevel[level].length} words`); continue; }
    if (check) { console.error(`STALE ${mod.pageFilename(level)}`); stale += 1; continue; }
    fs.writeFileSync(dest, html);
    console.log(`write ${mod.pageFilename(level)}  ${byLevel[level].length} words`);
  }
  if (stale) {
    console.error(`\n${stale} file(s) stale -- run: node ui/scripts/generate-hsk-pages.js`);
    process.exit(1);
  }
}
main();
