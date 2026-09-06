/**
 * lexitrail#365 — pins the STATIC `<a>` link block in `public/index.html` that gives
 * Googlebot a crawlable path from "/" to the "<gloss> in Chinese" landers.
 *
 * WHY IT MUST BE STATIC. Home.js already renders an equivalent "Popular words" list
 * from `PHASE1_QUERIES`, but that markup is produced by React AFTER the bundle
 * executes -- and issue-367 decided (b) static-only indexing: robots.txt blocks
 * `/static/js/` + `/*.js$`, so Googlebot never runs the bundle and never sees those
 * anchors (hcl@'s finding on this issue, measured live: `/` is a 3496-byte shell with
 * zero `<a>` tags). `public/index.html` is the SPA shell served for every unmatched
 * route, so a link placed there -- inside `#root`, alongside the existing
 * `#lx-premount` block -- is the only one a JS-blocked crawler can parse.
 *
 * WHY THIS TEST EXISTS. The static block is a second, hand-written copy of
 * `PHASE1_QUERIES` (a plain `<a href>` cannot import a JS module), so nothing stops
 * them drifting apart the moment PHASE1_QUERIES is widened for Phase 2. This file is
 * the tripwire: it reads both sources fresh and asserts they name the same slugs.
 */
import fs from 'fs';
import path from 'path';
import { PHASE1_QUERIES } from './glossPages';

const INDEX_HTML = path.join(__dirname, '..', '..', 'public', 'index.html');

// Same technique as premountIndicator.test.js: scope to the #root block, strip
// comments first -- this file's own explanatory prose mentions slugs and hrefs by
// name, and a whole-file match would be satisfied by the comment rather than the
// markup.
const stripComments = (html) => html.replace(/<!--[\s\S]*?-->/g, '');

const readRootBlock = () => {
  const html = fs.readFileSync(INDEX_HTML, 'utf8');
  const start = html.indexOf('<div id="root">');
  expect(start).toBeGreaterThan(-1);
  const end = html.indexOf('</body>', start);
  expect(end).toBeGreaterThan(start);
  return stripComments(html.slice(start, end));
};

describe('lexitrail#365 static homepage links to the gloss landers', () => {
  test('index.html carries a static <nav> block inside #root, not merely somewhere in the file', () => {
    const rootBlock = readRootBlock();
    expect(rootBlock).toContain('id="lx-static-links"');
  });

  test('CONTROL: PHASE1_QUERIES really has entries (an empty list would make the loop below vacuous)', () => {
    expect(PHASE1_QUERIES.length).toBeGreaterThan(0);
  });

  test('every PHASE1_QUERIES slug has a real static <a href> in the block', () => {
    const rootBlock = readRootBlock();
    for (const q of PHASE1_QUERIES) {
      expect(rootBlock).toContain(`href="/${q.slug}.html"`);
    }
  });

  test('the static block names exactly the PHASE1_QUERIES slugs -- no more, no fewer', () => {
    const rootBlock = readRootBlock();
    const navStart = rootBlock.indexOf('id="lx-static-links"');
    expect(navStart).toBeGreaterThan(-1);
    const navEnd = rootBlock.indexOf('</nav>', navStart);
    expect(navEnd).toBeGreaterThan(navStart);
    const navBlock = rootBlock.slice(navStart, navEnd);

    const hrefSlugs = [...navBlock.matchAll(/href="\/([a-z-]+)-in-chinese\.html"/g)]
      .map((m) => `${m[1]}-in-chinese`)
      .sort();
    const expectedSlugs = PHASE1_QUERIES.map((q) => q.slug).sort();
    expect(hrefSlugs).toEqual(expectedSlugs);
  });

  test('links are plain <a>, not <Link> -- the destination is a static file outside the SPA router', () => {
    const rootBlock = readRootBlock();
    const navStart = rootBlock.indexOf('id="lx-static-links"');
    const navEnd = rootBlock.indexOf('</nav>', navStart);
    const navBlock = rootBlock.slice(navStart, navEnd);
    expect(navBlock).not.toContain('<Link');
  });

  test('is a sibling of #lx-premount inside #root, so createRoot removes it on mount too', () => {
    const rootBlock = readRootBlock();
    const premountIdx = rootBlock.indexOf('id="lx-premount"');
    const navIdx = rootBlock.indexOf('id="lx-static-links"');
    expect(premountIdx).toBeGreaterThan(-1);
    expect(navIdx).toBeGreaterThan(premountIdx);
  });
});
