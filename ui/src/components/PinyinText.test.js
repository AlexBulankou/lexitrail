// lexitrail#190 — pinyin must not break mid-syllable.
//
// `renderPinyin` emits ONE <span> per CHARACTER so each vowel can carry its tone colour, and
// sibling inline elements are break opportunities — so the browser could wrap between any two
// characters. Measured on /game/<N>/TEST at 390x844: `xiǎojiě` rendered as `xiǎoji` / `ě`.
//
// 🔴 THE TEST HAS TO ASSERT BOTH HALVES. A fix that stops the breaking by dropping the
// per-character spans would pass a nowrap-only assertion and silently delete tone colouring —
// the feature this component exists for. So the colour assertions below are not decoration; they
// are what makes the nowrap assertion safe to satisfy.
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import PinyinText from './PinyinText';

const html = (text) => renderToStaticMarkup(<PinyinText text={text} />);

describe('the token cannot break mid-syllable', () => {
  test('🔴 the bug shape: the whole token is wrapped in a nowrap element', () => {
    // xiǎojiě is the measured case from the issue.
    expect(html('xiǎojiě')).toMatch(/^<span[^>]*style="[^"]*white-space:nowrap/);
  });

  test('the nowrap element is the OUTERMOST one, not an inner span', () => {
    // A nowrap on an inner element leaves the outer siblings breakable — the same bug with an
    // extra element in it.
    //
    // 🔴 MY FIRST VERSION OF THIS WAS VACUOUS and mutation testing caught it:
    //     expect(out.indexOf('white-space:nowrap')).toBeLessThan(out.indexOf('</span>'))
    // On the reverted component `indexOf` returns -1, and -1 is less than anything, so the
    // assertion PASSED on the bug it was written to catch. Assert the FIRST tag carries it.
    const out = html('shāngdiàn');
    const firstTag = out.slice(0, out.indexOf('>') + 1);
    expect(firstTag).toMatch(/white-space:nowrap/);
  });

  test.each(['xiǎojiě', 'shāngdiàn', 'míngtiān', 'gōngzuò', 'zěnme'])(
    '%s — every token the issue measured', (word) => {
      expect(html(word)).toMatch(/white-space:nowrap/);
    });
});

describe('CONTROL: the tone colouring the component exists for still works', () => {
  // Without these, "delete the per-character spans" passes every assertion above.
  test('a first-tone vowel is coloured and bold', () => {
    const out = html('shāng');
    expect(out).toMatch(/color:#FF4500/);   // tone 1
    expect(out).toMatch(/font-weight:bold/);
  });

  test('all four tones map to four distinct colours', () => {
    const colours = ['ā', 'á', 'ǎ', 'à'].map((c) => html(c).match(/color:(#[0-9A-Fa-f]{6})/)[1]);
    expect(new Set(colours).size).toBe(4);
  });

  test('a neutral-tone character is NOT coloured — the discriminator', () => {
    // If every character were coloured, the assertions above would pass against a component that
    // had stopped distinguishing tones at all.
    expect(html('ma')).not.toMatch(/color:#/);
  });

  test('the characters themselves survive, in order', () => {
    expect(html('xiǎojiě').replace(/<[^>]+>/g, '')).toBe('xiǎojiě');
  });
});
