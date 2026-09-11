/**
 * issue-447 — the two `recall` call sites must stay SEPARABLE.
 *
 * GA4 counts a bulk mark of N cards as ONE event, and `cards_count` is not a
 * registered custom metric, so the single-card and bulk paths are
 * indistinguishable in the data unless their `event_label` differs. Only the
 * CORRECT side is ever bulked, so a shared label makes every accuracy number
 * read low — and read lower the more the bulk feature is used.
 *
 * This is a SOURCE assertion, deliberately: mounting <Game> to observe gtag
 * would test the rendering path, and the thing at risk here is a one-word
 * edit to a string literal. The failure this guards is somebody "tidying"
 * 'correct_bulk' back to 'correct' — which reunifies the two paths silently,
 * with nothing at runtime to notice.
 *
 * It keys on the parsed `recall` event blocks rather than on a free-floating
 * substring, so a mention of the label in a comment elsewhere in the file
 * cannot satisfy it.
 */
const fs = require('fs');
const path = require('path');

const SRC = fs.readFileSync(path.join(__dirname, 'Game.js'), 'utf8');

/** Every `window.gtag('event', 'recall', { ... })` block's event_label. */
function recallLabels(src) {
  const blocks = [...src.matchAll(
    /window\.gtag\(\s*'event',\s*'recall',\s*\{([\s\S]*?)\}\s*\)/g
  )];
  return blocks.map((m) => {
    const label = m[1].match(/'event_label':\s*([^,\n]+)/);
    return label ? label[1].trim() : null;
  });
}

describe('issue-447 recall event labels', () => {
  test('CONTROL — the parser finds both call sites', () => {
    // If this drops to 1, the regex stopped matching and every assertion
    // below would pass vacuously on an empty/short list.
    expect(recallLabels(SRC)).toHaveLength(2);
  });

  test('the CORRECT path of each call site emits a different label', () => {
    // Compares what each site sends when the answer is correct, which is the
    // only case the bulk path can produce. Resolving the ternary's TRUE branch
    // is what makes this a real guard: comparing the raw expressions would
    // pass on the bug, because `isCorrect ? 'correct' : 'incorrect'` is a
    // different STRING from `'correct'` while denoting the same label.
    const correctCase = (expr) => {
      const ternary = expr.match(/\?\s*('[^']*')\s*:/);
      return ternary ? ternary[1] : expr;
    };
    const [single, bulk] = recallLabels(SRC).map(correctCase);
    expect(single).toEqual("'correct'"); // the resolver found the true branch
    expect(bulk).not.toEqual(single);
  });

  test('the bulk site is labelled correct_bulk, the single site is not', () => {
    const labels = recallLabels(SRC);
    // Single-card site is the ternary; bulk site is the literal.
    expect(labels.filter((l) => l === "'correct_bulk'")).toHaveLength(1);
    expect(labels.some((l) => l && l.includes('isCorrect'))).toBe(true);
  });

  test('no recall site emits a bare \'correct\' literal', () => {
    // The bare literal is what the bulk site had before issue-447. The
    // single-card site reaches 'correct' through the ternary, which is
    // correct and is not this string.
    const labels = recallLabels(SRC);
    expect(labels).not.toContain("'correct'");
  });
});
