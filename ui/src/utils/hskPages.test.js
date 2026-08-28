// lexitrail#183 — the six crawlable HSK list pages.
//
// 🔴 THE DRIFT TEST IS THE POINT. The pages are a COMMITTED artifact (the Docker build context is
// `ui/`, so `terraform/csv/words.csv` does not exist inside the image and a build-time generator
// would silently produce nothing in production). A committed generated file that nobody
// regenerates is a stale file, and stale SEO content is worse than none because it looks tended.
// So the suite regenerates from the CSV and compares BYTES.
import fs from 'fs';
import path from 'path';
import Papa from 'papaparse';
import {
  HSK_LEVELS, isHskWordset, groupByLevel, renderPage, pageUrl, pageFilename,
  renderSitemapEntries,
} from './hskPages';

const REPO = path.resolve(__dirname, '..', '..', '..');
const CSV = path.join(REPO, 'terraform', 'csv', 'words.csv');
const PUBLIC = path.join(REPO, 'ui', 'public');

const rows = () => Papa.parse(fs.readFileSync(CSV, 'utf8'),
  { header: true, skipEmptyLines: true }).data;

const SAMPLE = [
  { word_id: '2', word: '我们', wordset_id: '1', def1: 'wǒmen', def2: 'we, us (pl.)' },
  { word_id: '1', word: '我', wordset_id: '1', def1: 'wǒ', def2: 'I, me' },
  { word_id: '9', word: '两', wordset_id: '2', def1: 'liǎng', def2: 'two' },
  { word_id: '99', word: 'ignored', wordset_id: '7', def1: '', def2: '' },  // the `test` set
];

describe('grouping', () => {
  test('only wordsets 1-6 are HSK; 7 is the internal test set', () => {
    expect(HSK_LEVELS.map(isHskWordset)).toEqual([true, true, true, true, true, true]);
    expect(isHskWordset(7)).toBe(false);   // CONTROL: it discriminates
    expect(isHskWordset(0)).toBe(false);
  });

  test('rows are grouped by level and the `test` set is excluded', () => {
    const g = groupByLevel(SAMPLE);
    expect(g[1].map((w) => w.word)).toEqual(['我', '我们']);
    expect(g[2].map((w) => w.word)).toEqual(['两']);
    expect(Object.values(g).flat().map((w) => w.word)).not.toContain('ignored');
  });

  test('output is sorted by word_id, not by input order', () => {
    // Determinism is load-bearing: the byte-comparison below cannot tolerate an
    // input-order-dependent render, and an intermittent guard gets deleted rather than fixed.
    expect(groupByLevel(SAMPLE)[1].map((w) => w.id)).toEqual([1, 2]);
  });
});

describe('the rendered page meets #183 acceptance', () => {
  const g = groupByLevel(SAMPLE);
  const html = renderPage(2, g[2]);

  test('unique title containing "HSK 2"', () => {
    expect(html).toMatch(/<title>HSK 2 Vocabulary List[^<]*<\/title>/);
    expect(renderPage(5, g[2])).toMatch(/<title>HSK 5 /);  // CONTROL: the level varies
  });

  test('SELF-canonical, not the homepage — #186 is the bug this must not repeat', () => {
    expect(html).toContain('<link rel="canonical" href="https://lexitrail.com/hsk2.html">');
  });

  test('the words are in server-rendered HTML with pinyin and English', () => {
    expect(html).toContain('两');
    expect(html).toContain('liǎng');
    expect(html).toContain('two');
  });

  test('ItemList JSON-LD whose count matches the table', () => {
    const ld = JSON.parse(html.match(/<script type="application\/ld\+json">(.*?)<\/script>/s)[1]);
    expect(ld['@type']).toBe('ItemList');
    expect(ld.numberOfItems).toBe(g[2].length);
    expect(ld.itemListElement).toHaveLength(g[2].length);
  });

  test('a CTA into the practice route that actually exists in App.js', () => {
    // `/game/:wordsetId/:mode?` -- a CTA to a route the SPA does not have would 404 the one
    // click this page exists to produce.
    expect(html).toContain('/game/2/PRACTICE');
  });

  test('🔴 NO links to per-word pages — those are #184 and do not exist yet', () => {
    // The issue's proposal lists them. Shipping them now hands Googlebot ~5,600 soft-404s from
    // the six pages meant to establish that this site is crawlable at all.
    expect(html).not.toMatch(/href="[^"]*\/word\//);
  });

  test('HTML in the source data is escaped, not interpolated', () => {
    const evil = renderPage(1, [{ id: 1, word: '<script>x</script>', pinyin: '"', english: '&' }]);
    expect(evil).not.toContain('<script>x</script>');
    expect(evil).toContain('&lt;script&gt;');
  });
});

describe('urls are .html — verified against a real `serve`, not assumed', () => {
  test('pageUrl and pageFilename both carry the extension', () => {
    // `/hsk2` serves the SPA shell: serve-handler serves an EXACT filesystem match before
    // applying rewrites, and `serve.json`'s `{"source":"**"}` catches anything needing cleanUrls
    // or directory-index resolution. Measured; see hskPages.js's header for the full matrix.
    expect(pageUrl(2)).toBe('https://lexitrail.com/hsk2.html');
    expect(pageFilename(6)).toBe('hsk6.html');
  });

  test('serve.json disables cleanUrls, or /hsk2.html 301s into the shell', () => {
    const cfg = JSON.parse(fs.readFileSync(path.join(PUBLIC, 'serve.json'), 'utf8'));
    expect(cfg.cleanUrls).toBe(false);
  });
});

describe('the committed pages are NOT stale', () => {
  const byLevel = groupByLevel(rows());

  test.each(HSK_LEVELS)('hsk%i.html matches what the generator produces today', (level) => {
    const committed = fs.readFileSync(path.join(PUBLIC, pageFilename(level)), 'utf8');
    expect(committed).toBe(renderPage(level, byLevel[level]));
  });

  test('the levels carry the official HSK counts, as a sanity check on the CSV', () => {
    // If words.csv is ever truncated or re-keyed, these move -- and a silently short word list
    // is exactly the kind of thing that ships and is noticed months later by nobody.
    expect(HSK_LEVELS.map((n) => byLevel[n].length)).toEqual([150, 150, 300, 600, 1300, 2500]);
  });

  test('all six pages are in sitemap.xml', () => {
    const sm = fs.readFileSync(path.join(PUBLIC, 'sitemap.xml'), 'utf8');
    for (const n of HSK_LEVELS) expect(sm).toContain(pageUrl(n));
  });

  test('renderSitemapEntries takes lastmod rather than stamping now()', () => {
    // A generator that stamps `new Date()` produces a diff on every run and trains reviewers to
    // ignore its output.
    expect(renderSitemapEntries('2026-08-28')).toContain('<lastmod>2026-08-28</lastmod>');
    expect(renderSitemapEntries('2026-08-28')).toBe(renderSitemapEntries('2026-08-28'));
  });
});
