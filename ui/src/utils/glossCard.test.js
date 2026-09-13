import {
  renderGlossCard, hanziSize, glossCardPath, glossCardUrl, CARD_W, CARD_H, CARD_TOKENS,
} from './glossCard';
import { pinyinHtml } from './hskPages';

const CARD = { gloss: 'reputation', word: '名誉', pinyin: 'míngyù', hsk: 6 };

describe('glossCard', () => {
  it('renders the kicker from the gloss, uppercased, mirroring the search query', () => {
    expect(renderGlossCard(CARD, pinyinHtml)).toContain('REPUTATION IN CHINESE');
  });

  it('uses the SHARED tone renderer, so card and page cannot drift', () => {
    const html = renderGlossCard(CARD, pinyinHtml);
    // míngyù: í is tone 2, ù is tone 4 — the same spans the practice screen emits.
    expect(html).toContain('<span class="t2">í</span>');
    expect(html).toContain('<span class="t4">ù</span>');
  });

  it('names a CJK serif that actually resolves on the build box FIRST', () => {
    // The site's CSS asks for "Noto Serif SC", which fc-match does not resolve here — it falls
    // through to a sans. A card whose hero glyph silently renders in the wrong face is the whole
    // point lost, and nothing in the PNG would say so.
    const html = renderGlossCard(CARD, pinyinHtml);
    const stack = html.match(/font-family:("Noto[^;]*)/)[1];
    expect(stack.indexOf('"Noto Serif CJK SC"')).toBe(0);
  });

  it('states the English gloss exactly once — the kicker carries it', () => {
    const html = renderGlossCard(CARD, pinyinHtml);
    expect(html.match(/reputation/gi)).toHaveLength(1);
  });

  it('scales the hero down as the word gets longer, so it cannot overflow the canvas', () => {
    expect(hanziSize('好')).toBeGreaterThan(hanziSize('名誉'));
    expect(hanziSize('名誉')).toBeGreaterThan(hanziSize('三个字'));
    expect(hanziSize('四个字的')).toBeLessThan(hanziSize('三个字'));
  });

  it('keeps the whole stack inside 630px at every hero size', () => {
    // The first render overflowed and `align-items:center` clipped the kicker off the TOP and the
    // HSK chip off the BOTTOM — with every unit test passing, because the HTML was well-formed.
    // This asserts the budget the sizes were chosen against.
    const CHROME = 24 + 28 + 20 + 62 + 24 + 38; // kicker, gaps, pinyin, chip
    for (const w of ['好', '名誉', '三个字', '四个字的']) {
      expect(CHROME + hanziSize(w) * 1.06).toBeLessThan(CARD_H - 60);
    }
  });

  it('is always dark, independent of the build machine theme', () => {
    // No prefers-color-scheme in the card: a preview that changed with the renderer's theme
    // would be a defect, and it would only show up in production.
    const html = renderGlossCard(CARD, pinyinHtml);
    expect(html).not.toContain('prefers-color-scheme');
    expect(html).toContain(CARD_TOKENS.bg);
  });

  it('escapes untrusted text rather than interpolating it', () => {
    const html = renderGlossCard({ ...CARD, gloss: 'a<script>x</script>' }, pinyinHtml);
    expect(html).not.toContain('<script>x');
  });

  it('points at the same path the generator writes', () => {
    expect(glossCardPath('reputation-in-chinese')).toBe('/images/og/words/reputation-in-chinese.png');
    expect(glossCardUrl('x', 'https://lexitrail.com')).toBe('https://lexitrail.com/images/og/words/x.png');
  });

  it('declares the OG dimensions the page advertises', () => {
    expect([CARD_W, CARD_H]).toEqual([1200, 630]);
  });
});
