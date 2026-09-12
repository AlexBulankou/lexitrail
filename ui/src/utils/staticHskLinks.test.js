/**
 * zz3 /lighthouse e6 (2026-09-11) — pins the STATIC `<a>` link block in
 * `public/index.html` that gives Googlebot a crawlable path from "/" to the six
 * `hsk{1..6}.html` level lists.
 *
 * WHY IT EXISTS. Same mechanism as staticGlossLinks.test.js, different destination
 * set. issue-367 chose static-only indexing: robots.txt blocks `/static/js/` and
 * `/*.js$`, so Googlebot never runs the bundle and never sees any anchor React
 * renders. `public/index.html` is the SPA shell served for every unmatched route, so
 * a link placed there is the only one a JS-blocked crawler can parse.
 *
 * WHY A SEPARATE NAV, NOT MORE <a>s IN #lx-static-links. That block is documented and
 * test-pinned as a hand-copied mirror of `PHASE1_QUERIES`; its tripwire asserts the
 * block names exactly those slugs. Adding HSK hrefs there would survive the regex
 * (it only collects `*-in-chinese.html`) but would quietly destroy the contract the
 * tripwire is protecting. Two link sets, two blocks, two tests.
 *
 * WHAT MOTIVATED IT, measured rather than assumed: the six level pages carry the
 * property's largest LOW-competition demand cluster ('hsk 1 vocabulary' 5,400/mo,
 * 'hsk 3 vocabulary' 3,600/mo, 'hsk 1 vocabulary pdf' 2,400/mo — Google Ads Keyword
 * Planner, control keyword passed) and their on-page work is already correct. They
 * ranked 52–65 because nothing linked to them; hsk4.html had never been crawled.
 */
import fs from 'fs';
import path from 'path';

const INDEX_HTML = path.join(__dirname, '..', '..', 'public', 'index.html');
const LEVELS = [1, 2, 3, 4, 5, 6];

// Scope to #root and strip comments first — this file's own prose and the block's
// explanatory comment both mention the hrefs by name, and a whole-file match would be
// satisfied by a comment rather than by real markup.
const stripComments = (html) => html.replace(/<!--[\s\S]*?-->/g, '');

const readRootBlock = () => {
  const html = fs.readFileSync(INDEX_HTML, 'utf8');
  const start = html.indexOf('<div id="root">');
  expect(start).toBeGreaterThan(-1);
  const end = html.indexOf('</body>', start);
  expect(end).toBeGreaterThan(start);
  return stripComments(html.slice(start, end));
};

const readNavBlock = () => {
  const rootBlock = readRootBlock();
  const navStart = rootBlock.indexOf('id="lx-static-hsk"');
  expect(navStart).toBeGreaterThan(-1);
  const navEnd = rootBlock.indexOf('</nav>', navStart);
  expect(navEnd).toBeGreaterThan(navStart);
  return rootBlock.slice(navStart, navEnd);
};

describe('zz3-lighthouse-e6 static homepage links to the HSK level lists', () => {
  test('index.html carries a static <nav> block inside #root, not merely somewhere in the file', () => {
    expect(readRootBlock()).toContain('id="lx-static-hsk"');
  });

  test('every HSK level 1-6 has a real static <a href> in the block', () => {
    const navBlock = readNavBlock();
    for (const n of LEVELS) {
      expect(navBlock).toContain(`href="/hsk${n}.html"`);
    }
  });

  test('the block names exactly hsk1-6 -- no more, no fewer', () => {
    const hrefs = [...readNavBlock().matchAll(/href="\/hsk(\d+)\.html"/g)]
      .map((m) => Number(m[1]))
      .sort((a, b) => a - b);
    expect(hrefs).toEqual(LEVELS);
  });

  test('links are plain <a>, not <Link> -- the destinations are static files outside the SPA router', () => {
    expect(readNavBlock()).not.toContain('<Link');
  });

  test('does NOT pollute #lx-static-links, whose own tripwire pins it to PHASE1_QUERIES', () => {
    const rootBlock = readRootBlock();
    const glossStart = rootBlock.indexOf('id="lx-static-links"');
    expect(glossStart).toBeGreaterThan(-1);
    const glossBlock = rootBlock.slice(glossStart, rootBlock.indexOf('</nav>', glossStart));
    expect(glossBlock).not.toContain('/hsk');
  });

  test('is a sibling of #lx-premount inside #root, so createRoot removes it on mount too', () => {
    const rootBlock = readRootBlock();
    const premountIdx = rootBlock.indexOf('id="lx-premount"');
    const navIdx = rootBlock.indexOf('id="lx-static-hsk"');
    expect(premountIdx).toBeGreaterThan(-1);
    expect(navIdx).toBeGreaterThan(premountIdx);
  });
});
