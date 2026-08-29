// lexitrail#184 — the ~5,000 per-word pages.
//
// 🔴 THE DRIFT TEST IS THE POINT, for the same reason as hskPages.test.js: the pages are a
// COMMITTED artifact, and a committed generated file nobody regenerates is a stale file. Stale SEO
// content is worse than none, because it looks tended.
//
// At 5,000 files a byte-for-byte compare of every page is slow enough that someone would disable
// it, so the drift test compares a SAMPLE plus the total count and the manifest. That is a weaker
// guarantee and it is named here rather than left implicit: it catches a renderer change or a
// dropped/added word, and it would NOT catch a single corrupted page outside the sample. The
// `--check` mode of the generator does the exhaustive compare; this suite keeps CI fast.
import fs from 'fs';
import path from 'path';
import Papa from 'papaparse';
import { HSK_LEVELS, renderPage } from './hskPages';
import {
  wordFilename, wordUrl, collectWords, renderWordPage, renderWordSitemapEntries,
  renderWordSitemap, WORD_PAGES_LASTMOD,
} from './wordPages';

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

describe('filename vs URL — the distinction the 404 lives in', () => {
  test('the FILENAME is raw UTF-8, not percent-encoded', () => {
    // Encoding here would create a file literally named `%E6%88%91.html`, which then 404s for the
    // encoded request a browser actually sends. Measured against `serve` itself on 2026-08-29.
    expect(wordFilename('我')).toBe('我.html');
    expect(wordFilename('我')).not.toContain('%');
  });

  test('the URL IS percent-encoded, because href/canonical/sitemap require it', () => {
    expect(wordUrl(3, '我')).toBe('https://lexitrail.com/hsk3/%E6%88%91.html');
  });

  test('URL and filename round-trip — the property that makes both correct at once', () => {
    for (const w of ['我', '我们', '两', 'a']) {
      const seg = wordUrl(3, w).split('/').pop().replace(/\.html$/, '');
      expect(`${decodeURIComponent(seg)}.html`).toBe(wordFilename(w));
    }
  });
});

describe('collectWords', () => {
  test('keeps HSK sets, drops the internal `test` set and empty words', () => {
    const { words } = collectWords(SAMPLE);
    expect(words.map((w) => w.word)).toEqual(['我', '我们', '两']);
  });

  test('sorts by (level, word_id) so output is DETERMINISTIC', () => {
    // An intermittent drift guard gets deleted rather than fixed, so determinism is load-bearing.
    expect(collectWords(SAMPLE).words.map((w) => w.id)).toEqual([1, 2, 9]);
    expect(collectWords([...SAMPLE].reverse()).words.map((w) => w.id)).toEqual([1, 2, 9]);
  });

  test('MERGES a second sense of the same hanzi rather than dropping it, and REPORTS it', () => {
    // Two rows sharing a hanzi render to the same filename. Dropping one would lose a MEANING and
    // keep whichever gloss happened to sort first. This is real data: HSK2 `对` is word_id 301
    // ("to") and 302 ("right").
    const dup = [...SAMPLE, { word_id: '500', word: '我', wordset_id: '1', def1: 'wǒ', def2: 'myself' }];
    const { words, sensesMerged } = collectWords(dup);
    expect(sensesMerged).toBe(1);
    const merged = words.filter((w) => w.word === '我');
    expect(merged).toHaveLength(1);
    expect(merged[0].id).toBe(1);                       // headline stays the first by word_id
    expect(merged[0].english).toBe('I, me; myself');    // BOTH senses survive
    expect(merged[0].senses).toHaveLength(2);
  });

  test('a repeated READING is not repeated in the merged pinyin', () => {
    // `对` is duì in both senses; rendering "duì, duì" reads as an error.
    const dup = [...SAMPLE, { word_id: '500', word: '我', wordset_id: '1', def1: 'wǒ', def2: 'myself' }];
    expect(collectWords(dup).words.find((w) => w.word === '我').pinyin).toBe('wǒ');
  });

  test('two DIFFERENT readings are both listed', () => {
    const dup = [...SAMPLE, { word_id: '500', word: '我', wordset_id: '1', def1: 'wo3', def2: 'alt' }];
    expect(collectWords(dup).words.find((w) => w.word === '我').pinyin).toBe('wǒ, wo3');
  });

  test('the SAME hanzi at a DIFFERENT level is kept — the key is (level, word)', () => {
    const cross = [...SAMPLE, { word_id: '700', word: '我', wordset_id: '4', def1: 'wǒ', def2: 'I' }];
    expect(collectWords(cross).words.filter((w) => w.word === '我')).toHaveLength(2);
  });
});

describe('renderWordPage', () => {
  const w = { level: 3, id: 1, word: '我', pinyin: 'wǒ', english: 'I, me' };

  test('is self-canonical', () => {
    expect(renderWordPage(w)).toContain('<link rel="canonical" href="https://lexitrail.com/hsk3/%E6%88%91.html">');
  });

  test('escapes HTML in the visible sinks', () => {
    const evil = { ...w, english: '<script>alert(1)</script>' };
    const html = renderWordPage(evil);
    expect(html).not.toContain('<script>alert(1)</script>');
    expect(html).toContain('&lt;script&gt;');
  });

  test('escapes `<` inside the JSON-LD too — the sibling sink that gets forgotten', () => {
    // JSON.stringify does NOT escape `<`, so a `</script>` in source data would CLOSE the block and
    // everything after it becomes markup. One sink hardened and its sibling forgotten is the
    // classic split; this pins the half that has no visible symptom.
    const evil = { ...w, pinyin: '</script><img src=x onerror=1>' };
    const ld = renderWordPage(evil).split('application/ld+json">')[1].split('</script>')[0];
    expect(ld).not.toContain('</script');
    expect(ld).toContain('\\u003c');
  });

  test('prev/next render when given and are ABSENT at the ends', () => {
    const prev = { level: 3, id: 0, word: '你' };
    const next = { level: 3, id: 2, word: '他' };
    const mid = renderWordPage(w, { prev, next });
    expect(mid).toContain('rel="prev"');
    expect(mid).toContain('rel="next"');

    const first = renderWordPage(w, { next });
    expect(first).not.toContain('rel="prev"');
    expect(first).toContain('rel="next"');

    const last = renderWordPage(w, { prev });
    expect(last).toContain('rel="prev"');
    expect(last).not.toContain('rel="next"');
  });

  test('a word with no pinyin/english still renders valid, non-empty prose', () => {
    // ~A CSV row can be missing def1/def2; the page must not emit "is pronounced  and means".
    const bare = renderWordPage({ level: 1, id: 1, word: '啊' });
    expect(bare).toContain('<h1 lang="zh-Hans">啊</h1>');
    expect(bare).not.toContain('is pronounced  and');
    expect(bare).toContain('<!DOCTYPE html>');
  });
});

describe('renderWordSitemapEntries', () => {
  test('takes lastmod rather than stamping now()', () => {
    const { words } = collectWords(SAMPLE);
    expect(renderWordSitemapEntries(words, '2026-08-29')).toContain('<lastmod>2026-08-29</lastmod>');
    expect(renderWordSitemapEntries(words, '2026-08-29'))
      .toBe(renderWordSitemapEntries(words, '2026-08-29'));
  });
});

describe('the level pages link to the word pages — the two modules must agree', () => {
  // hskPages.js builds the href inline rather than importing wordUrl (that would be a circular
  // import for one template string). This test is what stops the two forms drifting apart: it is
  // the ONLY thing tying them together, so it is load-bearing rather than decorative.
  const w = { id: 1, word: '我', pinyin: 'wǒ', english: 'I, me' };

  test('the href on a level page is byte-identical to wordUrl()', () => {
    expect(renderPage(3, [w])).toContain(`href="${wordUrl(3, '我')}"`);
  });

  test('the hanzi is still escaped inside the link text', () => {
    const evil = { id: 1, word: '<b>', pinyin: '', english: '' };
    const html = renderPage(3, [evil]);
    expect(html).toContain('&lt;b&gt;</a>');
    expect(html).not.toContain('<td lang="zh-Hans"><a href="' + wordUrl(3, '<b>') + '"><b></a>');
  });
});

describe('sitemap-words.xml', () => {
  const { words } = collectWords(Papa.parse(fs.readFileSync(CSV, 'utf8'),
    { header: true, skipEmptyLines: true }).data);

  test('the committed sitemap matches what the generator produces today', () => {
    // ONE file, so unlike the 4,999 pages this drift check can afford to be exhaustive.
    expect(fs.readFileSync(path.join(PUBLIC, 'sitemap-words.xml'), 'utf8'))
      .toBe(renderWordSitemap(words));
  });

  test('it carries one <url> per word page, not per CSV row', () => {
    const sm = fs.readFileSync(path.join(PUBLIC, 'sitemap-words.xml'), 'utf8');
    expect((sm.match(/<url>/g) || [])).toHaveLength(words.length);
  });

  test('lastmod is the committed CONSTANT, not the day the test runs', () => {
    // If this ever equals `today`, someone has wired new Date() in and the drift test above will
    // fail tomorrow -- and an intermittent guard gets deleted rather than fixed.
    expect(renderWordSitemap(words)).toContain(`<lastmod>${WORD_PAGES_LASTMOD}</lastmod>`);
    expect(renderWordSitemap(words)).toBe(renderWordSitemap(words));
  });

  test('robots.txt declares it — a sitemap no crawler is told about does nothing', () => {
    const robots = fs.readFileSync(path.join(PUBLIC, 'robots.txt'), 'utf8');
    expect(robots).toContain('Sitemap: https://lexitrail.com/sitemap-words.xml');
    expect(robots).toContain('Sitemap: https://lexitrail.com/sitemap.xml');  // the original survives
  });

  test('it is comfortably inside the 50,000-URL / 50 MB sitemap limits', () => {
    // Pinned with headroom rather than as a tolerance: a future word list several times this size
    // would need a sitemap index, and finding that out from Search Console is expensive.
    const sm = fs.readFileSync(path.join(PUBLIC, 'sitemap-words.xml'), 'utf8');
    expect(words.length).toBeLessThan(50000);
    expect(Buffer.byteLength(sm, 'utf8')).toBeLessThan(50 * 1024 * 1024);
  });
});

describe('the committed pages are NOT stale', () => {
  const { words } = collectWords(rows());
  const byLevel = (lvl) => words.filter((x) => x.level === lvl);

  test('the CSV yields the official HSK counts, minus one MERGED sense', () => {
    // Official HSK sizes are [150,150,300,600,1300,2500] = 5000 ROWS. HSK2 carries `对` twice (two
    // senses, word_id 301/302), which is one PAGE — so level 2 has 149 pages for 150 rows. Pinned
    // as an exact expectation rather than a tolerance: if words.csv is re-keyed or truncated these
    // move, and a silently short word list is exactly what ships and is noticed by nobody.
    expect(HSK_LEVELS.map((n) => byLevel(n).length)).toEqual([150, 149, 300, 600, 1300, 2500]);
    expect(collectWords(rows()).sensesMerged).toBe(1);
  });

  test('the merged page carries BOTH senses of 对 — the one page this whole rule exists for', () => {
    const dui = byLevel(2).find((w) => w.word === '对');
    expect(dui).toBeDefined();
    expect(dui.senses).toHaveLength(2);
    const html = renderWordPage(dui);
    expect(html).toContain('<h2>Senses</h2>');
    expect(html).toContain('right');
    expect(html).toContain('to');
  });

  test('every level directory holds exactly its word count', () => {
    for (const n of HSK_LEVELS) {
      const dir = path.join(PUBLIC, `hsk${n}`);
      expect(fs.readdirSync(dir).filter((f) => f.endsWith('.html'))).toHaveLength(byLevel(n).length);
    }
  });

  test('a SAMPLE of committed pages matches what the generator produces today', () => {
    // Sample rather than all 5,000: see the header. `--check` does the exhaustive compare.
    for (const n of HSK_LEVELS) {
      const lvl = byLevel(n);
      for (const i of [0, Math.floor(lvl.length / 2), lvl.length - 1]) {
        const w = lvl[i];
        const committed = fs.readFileSync(
          path.join(PUBLIC, `hsk${n}`, wordFilename(w.word)), 'utf8');
        expect(committed).toBe(renderWordPage(w, {
          prev: lvl[i - 1] || null, next: lvl[i + 1] || null,
        }));
      }
    }
  });
});
