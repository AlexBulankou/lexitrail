/**
 * lexitrail#367 — pins the STATIC-ONLY INDEXING decision (2026-09-05).
 *
 * robots.txt blocks Googlebot from /static/js/ and /*.js$, so every CRA SPA route
 * renders as a ~3496-byte shell with zero links. #367 chose option (b): keep the
 * block, and stop listing unrenderable shells in sitemap.xml.
 *
 * 🔴 Without this test the decision is a comment in an XML file, and a comment cannot
 * go red. The failure it guards is someone re-adding /game/* or /about to sitemap.xml
 * in good faith — which produces no error, no warning, and no discovery event; the
 * only symptom is Search Console quietly reporting "Crawled - currently not indexed"
 * months later. That is the shape a test exists for.
 *
 * NOTE ON WHAT THIS DOES *NOT* ASSERT: it does not check that the listed URLs are
 * reachable or that the static pages render. It asserts one property — that nothing
 * in sitemap.xml is a JS-dependent route. A green run here says the sitemap kept its
 * shape, never that indexing is healthy.
 */
const fs = require('fs');
const path = require('path');

const SITEMAP = path.join(__dirname, '..', '..', 'public', 'sitemap.xml');

function locs() {
  const xml = fs.readFileSync(SITEMAP, 'utf8');
  return [...xml.matchAll(/<loc>(.*?)<\/loc>/g)].map((m) => m[1]);
}

describe('sitemap.xml — static-only indexing (#367)', () => {
  test('the file parses and is non-empty (positive control: a broken read must not pass)', () => {
    const urls = locs();
    // If the regex or the path ever breaks, `urls` is [] and EVERY assertion below
    // passes vacuously by ranging over nothing. This makes that a failure instead.
    expect(urls.length).toBeGreaterThan(0);
  });

  test('every URL is the homepage or a static .html page — no JS-dependent SPA route', () => {
    const offenders = locs().filter(
      (u) => u !== 'https://lexitrail.com/' && !u.endsWith('.html')
    );
    expect(offenders).toEqual([]);
  });

  test('the 14 SPA routes removed by #367 have not been re-added', () => {
    const urls = locs();
    const removed = [
      'https://lexitrail.com/about',
      'https://lexitrail.com/wordsets',
      ...[1, 2, 3, 4, 5, 6].map((n) => `https://lexitrail.com/game/${n}/PRACTICE`),
      ...[1, 2, 3, 4, 5, 6].map((n) => `https://lexitrail.com/game/${n}/TEST`),
    ];
    expect(removed.filter((u) => urls.includes(u))).toEqual([]);
  });

  test('the homepage is still listed — #367 dropped the SPA routes, not /', () => {
    // Deliberate: / is an unrenderable shell too, but a homepage is crawled regardless
    // and omitting it signals the wrong thing. The fix for / is #365 (static links in
    // index.html), not removal from the sitemap.
    expect(locs()).toContain('https://lexitrail.com/');
  });
});
