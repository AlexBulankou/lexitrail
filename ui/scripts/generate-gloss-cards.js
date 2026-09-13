#!/usr/bin/env node
// Regenerate ui/public/images/og/words/<slug>.png — the per-word social/search card for the
// Phase-1 "<gloss> in Chinese" pages.
//
// Thin I/O shell, same shape as generate-gloss-pages.js: the card's design lives in the pure,
// unit-tested ui/src/utils/glossCard.js and this file only reads inputs, drives a browser, and
// writes files.
//
//   node ui/scripts/generate-gloss-cards.js            # write
//   node ui/scripts/generate-gloss-cards.js --check    # exit 1 if any committed card is stale
//
// 🔴 WHY THE OUTPUT IS COMMITTED, same reason as the pages it serves: the Docker build context is
// `ui/`, and `terraform/csv/words.csv` is one directory UP, so a build-time generator would work
// locally, pass review, and produce nothing in production.
//
// 🔴 WHY HEADLESS CHROME AND NOT PLAYWRIGHT. tools/og/ uses playwright, and that is right for it —
// it runs rarely and by hand. This runs in the same breath as the page generator, and adding a
// ~300MB browser download to that path would make regenerating five PNGs the slowest step in the
// repo. Chrome is already on the box. If it is not on yours, set CHROME to the binary; the error
// says so rather than leaving you to guess that a missing browser is what a non-zero exit meant.
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync } = require('child_process');
const Papa = require('papaparse');

const UI = path.resolve(__dirname, '..');
const CSV = path.resolve(UI, '..', 'terraform', 'csv', 'words.csv');
const OUT_DIR = path.resolve(UI, 'public', 'images', 'og', 'words');

const CHROME_CANDIDATES = [process.env.CHROME, 'google-chrome', 'chromium', 'chromium-browser']
  .filter(Boolean);

// Same eval-and-bind trick the sister generators use; see generate-gloss-pages.js for why.
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

const hsk = evalModule('hskPages.js', ['isHskWordset', 'pinyinHtml']);
const gp = evalModule('glossPages.js', ['PHASE1_QUERIES', 'collectGlossGroup'],
  { isHskWordset: hsk.isHskWordset });
const gc = evalModule('glossCard.js',
  ['renderGlossCard', 'glossCardPath', 'CARD_W', 'CARD_H', 'hanziSize', 'CARD_TOKENS']);

function resolveChrome() {
  for (const bin of CHROME_CANDIDATES) {
    try {
      execFileSync(bin, ['--version'], { stdio: 'ignore', timeout: 20000 });
      return bin;
    } catch { /* try the next candidate */ }
  }
  throw new Error(
    `no Chrome found (tried: ${CHROME_CANDIDATES.join(', ')}). This is a MISSING BROWSER, not a `
    + 'render failure — set CHROME=/path/to/chrome and re-run.');
}

function shoot(chrome, html, outPath) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'gloss-card-'));
  const htmlPath = path.join(tmp, 'card.html');
  const pngPath = path.join(tmp, 'card.png');
  fs.writeFileSync(htmlPath, html);
  try {
    execFileSync(chrome, [
      '--headless', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
      '--force-device-scale-factor=1',
      `--window-size=${gc.CARD_W},${gc.CARD_H}`,
      `--screenshot=${pngPath}`,
      `file://${htmlPath}`,
    ], { stdio: 'ignore', timeout: 120000 });
    const png = fs.readFileSync(pngPath);
    // A browser that writes a 0-byte or non-PNG file has failed in a way that would otherwise
    // commit an empty card. Check the magic bytes and the dimensions we asked for.
    if (png.length < 1000 || png.readUInt32BE(0) !== 0x89504e47) {
      throw new Error(`chrome produced ${png.length} bytes that are not a PNG for ${outPath}`);
    }
    const w = png.readUInt32BE(16);
    const h = png.readUInt32BE(20);
    if (w !== gc.CARD_W || h !== gc.CARD_H) {
      throw new Error(`expected ${gc.CARD_W}x${gc.CARD_H}, chrome rendered ${w}x${h}`);
    }
    fs.writeFileSync(outPath, png);
    return png.length;
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

function main() {
  const check = process.argv.includes('--check');
  const rows = Papa.parse(fs.readFileSync(CSV, 'utf8'), { header: true, skipEmptyLines: true }).data;
  const chrome = resolveChrome();
  fs.mkdirSync(OUT_DIR, { recursive: true });

  let stale = 0;
  let written = 0;
  for (const query of gp.PHASE1_QUERIES) {
    const group = gp.collectGlossGroup(rows, query.gloss);
    // A query whose gloss no longer matches any word would silently produce no card, and the page
    // would keep pointing at a 404. Fail loudly instead — the page generator has the same contract.
    if (!group) throw new Error(`no word matches gloss "${query.gloss}" (${query.slug})`);
    const { primary } = group;
    const html = gc.renderGlossCard({
      gloss: query.gloss,
      word: primary.word,
      pinyin: primary.pinyin,
      // The QUERY's gloss, not the CSV's full sense list: the card mirrors what was searched, and
      // def2 is comma-separated ("reputation, fame") which reads as clutter at card scale.
      english: query.gloss,
      hsk: primary.level,
    }, hsk.pinyinHtml);

    const dest = path.join(OUT_DIR, `${query.slug}.png`);
    if (check) {
      const tmpOut = path.join(os.tmpdir(), `check-${query.slug}.png`);
      shoot(chrome, html, tmpOut);
      const fresh = fs.readFileSync(tmpOut);
      fs.rmSync(tmpOut, { force: true });
      const committed = fs.existsSync(dest) ? fs.readFileSync(dest) : Buffer.alloc(0);
      // Byte-compare is deliberately NOT used here: PNG encoders vary across Chrome builds, so a
      // byte diff would fail for a reason that has nothing to do with the design. Existence and
      // dimensions are what --check can honestly assert; the drift that matters (a page pointing
      // at a card that was never generated) is exactly what that catches.
      if (!committed.length) {
        console.error(`STALE: ${query.slug}.png is missing`);
        stale += 1;
      } else if (committed.readUInt32BE(16) !== fresh.readUInt32BE(16)
              || committed.readUInt32BE(20) !== fresh.readUInt32BE(20)) {
        console.error(`STALE: ${query.slug}.png has the wrong dimensions`);
        stale += 1;
      }
    } else {
      const bytes = shoot(chrome, html, dest);
      console.log(`wrote ${gc.glossCardPath(query.slug)}  ${primary.word} ${primary.pinyin}  `
        + `HSK ${primary.level}  ${bytes.toLocaleString()} bytes`);
      written += 1;
    }
  }

  if (check) {
    console.log(`checked ${gp.PHASE1_QUERIES.length} card(s), ${stale} stale`);
    if (stale) process.exit(1);
  } else {
    console.log(`${written} card(s) written to ${path.relative(UI, OUT_DIR)}`);
  }
}

main();
