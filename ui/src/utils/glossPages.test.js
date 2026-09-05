import fs from 'fs';
import path from 'path';
import {
  PHASE1_QUERIES,
  toNumberedPinyin,
  collectGlossGroup,
  renderGlossPage,
  renderGlossSitemap,
  glossUrl,
} from './glossPages';

const ROWS = [
  { word_id: '437', word: '决定', wordset_id: '3', def1: 'juédìng', def2: 'Decision' },
  { word_id: '7434', word: '决定', wordset_id: '8', def1: 'juédìng', def2: 'Decision' }, // combined set, excluded
  { word_id: '1050', word: '网球', wordset_id: '4', def1: 'wǎngqiú', def2: 'Tennis' },
  { word_id: '330', word: '乒乓球', wordset_id: '4', def1: 'pīngpāngqiú', def2: 'Table Tennis' },
  { word_id: '1525', word: '模糊', wordset_id: '5', def1: 'móhu', def2: 'vague' },
  { word_id: '739', word: '含糊', wordset_id: '6', def1: 'hánhu', def2: 'vague' },
  { word_id: '1270', word: '名誉', wordset_id: '6', def1: 'míngyù', def2: 'reputation' },
  { word_id: '2019', word: '信誉', wordset_id: '6', def1: 'xìnyù', def2: 'reputation' },
  { word_id: '2771', word: '澄清', wordset_id: '6', def1: 'chéngqīng', def2: 'clarify' },
  { word_id: '2772', word: '表态', wordset_id: '6', def1: 'biǎotài', def2: "clarify one's position" },
];

// ------------------------------------------------------- PHASE1_QUERIES: the seed set itself ---

test('PHASE1_QUERIES is the 5-query GSC-proven seed named in the issue body', () => {
  expect(PHASE1_QUERIES.map((q) => q.slug).sort()).toEqual([
    'clarify-in-chinese', 'decision-in-chinese', 'reputation-in-chinese',
    'tennis-in-chinese', 'vague-in-chinese',
  ]);
  for (const q of PHASE1_QUERIES) {
    expect(q.slug).toBe(`${q.gloss}-in-chinese`);
  }
});

// --------------------------------------------------------------- toNumberedPinyin: THE hazard ---
// The segmenter has no ground truth to check itself against, so these are the ONLY guard against
// a wrong digit landing on a live page. Each is a real Phase-1 word's real CSV pinyin string.

describe('toNumberedPinyin — Phase-1 words, hand-verified', () => {
  test('juédìng (2 syllables) -> jue2 ding4', () => {
    expect(toNumberedPinyin('juédìng', 2)).toBe('jue2 ding4');
  });
  test('wǎngqiú (2 syllables) -> wang3 qiu2', () => {
    expect(toNumberedPinyin('wǎngqiú', 2)).toBe('wang3 qiu2');
  });
  test('móhu (2 syllables, second is NEUTRAL tone) -> mo2 hu5', () => {
    expect(toNumberedPinyin('móhu', 2)).toBe('mo2 hu5');
  });
  test('chéngqīng (2 syllables) -> cheng2 qing1', () => {
    expect(toNumberedPinyin('chéngqīng', 2)).toBe('cheng2 qing1');
  });
  test('míngyù (2 syllables) -> ming2 yu4', () => {
    expect(toNumberedPinyin('míngyù', 2)).toBe('ming2 yu4');
  });
  test('single-syllable word: wǒ -> wo3', () => {
    expect(toNumberedPinyin('wǒ', 1)).toBe('wo3');
  });
  test('a syllable count that has NO valid segmentation at all returns null, not a guess', () => {
    // A pinyin string containing a character sequence no valid initial+final combination can
    // read (here: a stray digit) must refuse outright rather than emit a partial/garbage answer.
    expect(toNumberedPinyin('xx9yy', 2)).toBeNull();
  });
  test('an all-neutral-tone word still segments and reports tone 5 throughout', () => {
    // "mĭfan" style words without marks on either syllable: contrived but exercises the
    // "no marks in this segment at all" branch independent of the mixed case above.
    expect(toNumberedPinyin('mifan', 2)).toBe('mi5 fan5');
  });
});

// ------------------------------------------------------------------------ collectGlossGroup ---

describe('collectGlossGroup', () => {
  test('exact single match: decision -> 决定, HSK3, and the combined-wordset duplicate excluded', () => {
    const g = collectGlossGroup(ROWS, 'decision');
    expect(g.primary).toMatchObject({ word: '决定', level: 3 });
    expect(g.alternates).toEqual([]);
  });

  test('NEGATIVE: exact match only, "clarify" does not pull in "clarify one\'s position"', () => {
    // This is the discipline #365's quality gate #1 names directly: a substring/phrase match
    // would pad the page with a different phrase nobody searched for.
    const g = collectGlossGroup(ROWS, 'clarify');
    expect(g.primary.word).toBe('澄清');
    expect(g.alternates).toEqual([]);
  });

  test('collision: two hanzi share the gloss "vague" -> lower HSK level is primary', () => {
    const g = collectGlossGroup(ROWS, 'vague');
    expect(g.primary).toMatchObject({ word: '模糊', level: 5 });
    expect(g.alternates).toHaveLength(1);
    expect(g.alternates[0]).toMatchObject({ word: '含糊', level: 6 });
  });

  test('collision at the SAME HSK level: tie-break by lower word_id', () => {
    const g = collectGlossGroup(ROWS, 'reputation');
    expect(g.primary).toMatchObject({ word: '名誉', id: 1270 });
    expect(g.alternates[0]).toMatchObject({ word: '信誉', id: 2019 });
  });

  test('no match at all -> null, not an empty/fabricated group', () => {
    expect(collectGlossGroup(ROWS, 'nonexistent-gloss-xyz')).toBeNull();
  });

  test('case- and whitespace-insensitive gloss matching', () => {
    const g = collectGlossGroup(ROWS, '  TENNIS  ');
    expect(g.primary.word).toBe('网球');
  });
});

// ------------------------------------------------------------------------------- renderGlossPage --

describe('renderGlossPage', () => {
  const query = { slug: 'decision-in-chinese', gloss: 'decision' };
  const group = collectGlossGroup(ROWS, 'decision');
  const html = renderGlossPage(query, group, {});

  test('title/h1 matches the query verbatim (case-normalized), per the spec\'s page model', () => {
    expect(html).toMatch(/<title>Decision in Chinese<\/title>/);
    expect(html).toMatch(/<h1>Decision in Chinese<\/h1>/);
  });

  test('canonical is the ROOT-level slug (.html, matching serve.json cleanUrls:false), not /hskN/', () => {
    expect(html).toContain('<link rel="canonical" href="https://lexitrail.com/decision-in-chinese.html">');
  });

  test('JSON-LD DefinedTerm is present and names the primary word', () => {
    expect(html).toMatch(/"@type":"DefinedTerm"/);
    expect(html).toContain('"name":"决定"');
  });

  test('the true HSK level is shown even when the primary word is HSK6+', () => {
    const q2 = { slug: 'clarify-in-chinese', gloss: 'clarify' };
    const g2 = collectGlossGroup(ROWS, 'clarify');
    const html2 = renderGlossPage(q2, g2, {});
    expect(html2).toContain('HSK 6'); // badge must not hide/cap the real level
  });

  test('HSK1/2/3 CTA buttons always render, regardless of the word\'s own level', () => {
    const q2 = { slug: 'clarify-in-chinese', gloss: 'clarify' }; // primary is HSK6
    const g2 = collectGlossGroup(ROWS, 'clarify');
    const html2 = renderGlossPage(q2, g2, {});
    expect(html2).toContain('/game/1/PRACTICE');
    expect(html2).toContain('/game/2/PRACTICE');
    expect(html2).toContain('/game/3/PRACTICE');
    expect(html2).not.toContain('/game/6/PRACTICE');
  });

  test('a gloss WITH alternates renders the "other ways to say it" row', () => {
    const q3 = { slug: 'vague-in-chinese', gloss: 'vague' };
    const g3 = collectGlossGroup(ROWS, 'vague');
    const html3 = renderGlossPage(q3, g3, {});
    expect(html3).toContain('Other ways to say it');
    expect(html3).toContain('含糊');
  });

  test('a gloss with NO alternates omits the row entirely (no empty section)', () => {
    expect(html).not.toContain('Other ways to say it');
  });

  test('example sentences render when supplied, and are absent when not', () => {
    const withEx = renderGlossPage(query, group, {
      examples: [{ chinese: '我做了一个决定。', pinyin: 'Wǒ zuò le yí gè juédìng.', english: 'I made a decision.' }],
    });
    expect(withEx).toContain('Example sentences');
    expect(withEx).toContain('我做了一个决定。');
    expect(html).not.toContain('Example sentences');
  });

  test('the audio button targets the primary hanzi via the shared Web Speech mechanism', () => {
    expect(html).toContain("ltSpeak('决定')");
    expect(html).toContain("u.lang='zh-CN'");
  });

  test('a single quote in the word cannot break out of the onclick attribute', () => {
    // No Phase-1 word actually contains one, but the escape must exist regardless -- an
    // unescaped ' would truncate the JS string and could inject markup into the attribute.
    const weird = { primary: { level: 1, id: 1, word: "a'b", pinyin: 'x', english: 'y' }, alternates: [] };
    const out = renderGlossPage({ slug: 's', gloss: 'g' }, weird, {});
    expect(out).toContain("ltSpeak('a\\'b')");
  });

  test('JSON-LD cannot be broken out of by a </script> in the data', () => {
    const evil = { primary: { level: 1, id: 1, word: '我', pinyin: 'x', english: '</script><script>1' }, alternates: [] };
    const out = renderGlossPage({ slug: 's', gloss: 'g' }, evil, {});
    expect(out).not.toContain('</script><script>1');
  });
});

// --------------------------------------------------------------------------------- sitemap ---

// ------------------------------------------------------------------------ serve.json coupling ---
// serve.json's `redirects` list is hand-maintained (same as the hskN entries it mirrors), so a
// query added to PHASE1_QUERIES without a matching redirect would 404 on the bare /<slug> URL
// while the .html file itself works fine -- a gap this drift check exists to catch immediately
// rather than on the next manual audit.

test('every PHASE1_QUERIES slug has a matching bare-path -> .html redirect in serve.json', () => {
  const serveJson = JSON.parse(fs.readFileSync(
    path.resolve(__dirname, '../../public/serve.json'), 'utf8'));
  const bySource = new Map(serveJson.redirects.map((r) => [r.source, r]));
  for (const q of PHASE1_QUERIES) {
    const r = bySource.get(`/${q.slug}`);
    expect(r).toBeDefined();
    expect(r.destination).toBe(`/${q.slug}.html`);
    expect(r.type).toBe(301);
  }
});

test('renderGlossSitemap emits one <url> per query at the root slug', () => {
  const xml = renderGlossSitemap(PHASE1_QUERIES, '2026-09-05');
  expect(xml.match(/<url>/g)).toHaveLength(5);
  expect(xml).toContain(glossUrl('clarify-in-chinese'));
  expect(xml).toContain('<lastmod>2026-09-05</lastmod>');
});
