// uibug 2026-09-16 — length→size-class mapping for TEST-mode option buttons.
//
// jsdom cannot measure the rendered box (no layout), so the GEOMETRY half of
// this fix is proven by the harness sweep (zero `.test-buttons button` rows
// with scrollWidth > clientWidth after). What jsdom CAN pin is the mapping the
// geometry depends on: which option lengths get which font-size step. The
// strings asserted here are the LIVE clipped rows from the 2026-09-15 sweep of
// lexitrail.com, so a threshold edit that would re-clip one of them fails by
// name.
import { quizOptionSizeClass } from './quizOptionSize';

describe('quizOptionSizeClass — length steps', () => {
  test('short options (≤4 chars) keep the default size: no class', () => {
    expect(quizOptionSizeClass('sì')).toBe('');
    expect(quizOptionSizeClass('shéi')).toBe('');
    expect(quizOptionSizeClass('nǎr')).toBe('');
  });

  test('5-6 chars step to md — live rows: wǒmen (73px @1.5rem), shénme (76px)', () => {
    expect(quizOptionSizeClass('wǒmen')).toBe('test-option-md');
    expect(quizOptionSizeClass('zěnme')).toBe('test-option-md');
    expect(quizOptionSizeClass('shénme')).toBe('test-option-md');
    expect(quizOptionSizeClass('búkèqì')).toBe('test-option-md');
    expect(quizOptionSizeClass('míngzi')).toBe('test-option-md');
  });

  test('7-8 chars step to sm — live rows: duōshǎo (80px), xuéshēng (85px), fēnzhōng (83px)', () => {
    expect(quizOptionSizeClass('duōshǎo')).toBe('test-option-sm');
    expect(quizOptionSizeClass('xiànzài')).toBe('test-option-sm');
    expect(quizOptionSizeClass('péngyǒu')).toBe('test-option-sm');
    expect(quizOptionSizeClass('xuéshēng')).toBe('test-option-sm');
    expect(quizOptionSizeClass('fēnzhōng')).toBe('test-option-sm');
    expect(quizOptionSizeClass('míngtiān')).toBe('test-option-sm');
  });

  test('9-10 chars step to xs — the worst live rows: dǎdiànhuà (90px), zěnmeyàng (95px)', () => {
    expect(quizOptionSizeClass('dǎdiànhuà')).toBe('test-option-xs');
    expect(quizOptionSizeClass('zěnmeyàng')).toBe('test-option-xs');
    expect(quizOptionSizeClass('xīngqītiān')).toBe('test-option-xs');
  });

  test('11+ chars step to xxs', () => {
    expect(quizOptionSizeClass('zhōngguāncūn')).toBe('test-option-xxs');
  });

  test('length counts CODE POINTS: a precomposed tone-marked vowel is ONE char', () => {
    // 'wǒmen' is 5 visible characters; a byte- or UTF-16-naive count that saw
    // more would push it a step too small.
    expect(Array.from('wǒmen').length).toBe(5);
    expect(quizOptionSizeClass('wǒmen')).toBe('test-option-md');
  });

  test('whitespace is trimmed before counting', () => {
    expect(quizOptionSizeClass('  shéi  ')).toBe('');
  });

  test('degenerate inputs are safe: empty/null/undefined → no class', () => {
    expect(quizOptionSizeClass('')).toBe('');
    expect(quizOptionSizeClass(null)).toBe('');
    expect(quizOptionSizeClass(undefined)).toBe('');
  });
});
