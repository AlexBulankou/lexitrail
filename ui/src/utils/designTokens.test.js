import { PAGE_TOKENS, pinyinHtml, toneOf, renderPage } from './hskPages';
import { getTone } from '../components/PinyinText';
import { readFileSync } from 'fs';
import { join } from 'path';

// revamp-2026-09 — the two halves of the product share ONE token layer and ONE tone table.
describe('token layer parity', () => {
  test('PAGE_TOKENS :root matches Global.css :root, declaration for declaration', () => {
    const css = readFileSync(join(__dirname, '..', 'styles', 'Global.css'), 'utf8');
    const decls = (s) => [...s.matchAll(/--[a-z0-9-]+\s*:\s*[^;}]+/g)]
      .map((m) => m[0].replace(/\s+/g, '').replace(/,\s*/g, ','))
      .filter((d) => !d.startsWith('--min-tap-target'));
    const fromPage = new Set(decls(PAGE_TOKENS));
    // Global.css has the active :root + dark override BEFORE the commented-out palette B block.
    const active = css.split('/* B —')[0];
    const fromGlobal = new Set(decls(active).filter((d) => !d.startsWith('--tap')));
    for (const d of fromGlobal) {
      if (d.startsWith('--font-display') || d.startsWith('--r-')) continue; // SPA may override display face
      expect(fromPage.has(d)).toBe(true);
    }
  });

  test('static tone table == PinyinText tone table', () => {
    const sample = 'āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜaeiouübpm-';
    for (const ch of sample) expect(toneOf(ch) > 0 ? toneOf(ch) : 0).toBe(getTone(ch));
  });

  test('pinyinHtml marks only toned vowels', () => {
    expect(pinyinHtml('péngyǒu')).toBe('p<span class="t2">é</span>ngy<span class="t3">ǒ</span>u');
    expect(pinyinHtml('ma')).toBe('ma');
    expect(pinyinHtml('<b>')).toBe('&lt;b&gt;');
  });

  test('list page carries the filter and tone-coloured pinyin', () => {
    const html = renderPage(1, [{ id: 1, word: '朋友', pinyin: 'péngyǒu', english: 'friend' }]);
    expect(html).toContain('id="q"');
    expect(html).toContain('class="t2"');
    expect(html).toContain('class="filter-bar"');
  });
});
