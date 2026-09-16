/**
 * uibug 2026-09-16 — tone-colored pinyin vowels on the TEST-mode option buttons.
 *
 * Measured on live prod (both viewports): every span.t1–.t4 inside
 * `.test-buttons button` rendered its root tone color (#c8361f / #9c5410 /
 * #2a7130 / #6b3fa0) on the button's var(--accent) #b23b2e background —
 * contrast 1.02–1.25:1 against the 3:1 floor. The tone-marked vowel is exactly
 * the character that differentiates the four choices, so 'sān' read as 's n'.
 *
 * The fix redefines --t1..--t4 to `currentColor` inside `.test-buttons button`.
 * That is the ONLY override that can work: PinyinText.js applies the tone color
 * as an INLINE `color: var(--tN)`, so a class-level `color` rule loses to it at
 * any specificity — but both the inline style and Global.css's .t1–.t4 rules
 * resolve through the tokens, and tokens cascade by scope.
 *
 * Same limits as tapTargets.test.js: this pins what the CSS DECLARES, not the
 * rendered pixel color (jsdom does not resolve var()). Render-level proof is
 * the E2E contrast harness.
 */
const fs = require('fs');
const path = require('path');

const STYLES = __dirname;
const read = (f) => fs.readFileSync(path.join(STYLES, f), 'utf8');

const TONE_TOKENS = ['--t1', '--t2', '--t3', '--t4'];

describe('TEST-mode options: tone tokens resolve to the button ink', () => {
  const wordCard = read('WordCard.css');

  // The base rule, not :hover / .quiz-option-correct — those inherit the
  // custom properties from it.
  const base = wordCard.match(/\.test-buttons button\s*\{([^}]*)\}/s);

  test('the base .test-buttons button rule exists and keeps accent-on-surface ink', () => {
    expect(base).not.toBeNull();
    expect(base[1]).toMatch(/background-color:\s*var\(--accent\)/);
    expect(base[1]).toMatch(/color:\s*var\(--surface\)/);
  });

  test.each(TONE_TOKENS)(
    '%s is redefined to currentColor inside .test-buttons button',
    (token) => {
      expect(base[1]).toMatch(new RegExp(`${token}:\\s*currentColor`));
    }
  );

  test('the override is currentColor, not a literal — so the reveal state stays readable', () => {
    // issue-344: .quiz-option-correct swaps to --ok ink on --ok-soft. A literal
    // (e.g. var(--surface) = white) would put white vowels on pale green there,
    // the exact trap that rule's own comment documents. currentColor tracks the
    // button's ink through every state.
    for (const token of TONE_TOKENS) {
      expect(base[1]).not.toMatch(
        new RegExp(`${token}:\\s*(#|rgb|var\\(--surface\\))`)
      );
    }
  });

  test('CONTROL: Global.css still owns the root tone palette this scopes over', () => {
    // Without the root tokens and the .t1–.t4 class rules, the override above
    // would be vacuous and this file could pass against an empty stylesheet.
    const global = read('Global.css');
    for (const token of TONE_TOKENS) {
      expect(global).toMatch(new RegExp(`${token}:\\s*#[0-9a-fA-F]{3,8}`));
    }
    expect(global).toMatch(/\.t1\s*\{\s*color:\s*var\(--t1\)/);
  });
});
