import { correctOption, shouldReveal, REVEAL_MS } from './quizReveal';

const opt = (pinyin, correct = false) => ({ pinyin, correct });
const FOUR = [opt('hǎo'), opt('shì', true), opt('rén'), opt('dà')];

describe('correctOption (issue-344)', () => {
  test('returns the option flagged correct', () => {
    expect(correctOption(FOUR).pinyin).toBe('shì');
  });

  test('returns NULL when none is flagged — a real answer, not a throw', () => {
    // BUG SHAPE: returning the first option here would highlight a WRONG answer
    // as correct, which is worse than the bug this feature fixes.
    expect(correctOption([opt('a'), opt('b')])).toBeNull();
  });

  test('survives missing / malformed option data', () => {
    expect(correctOption(undefined)).toBeNull();
    expect(correctOption(null)).toBeNull();
    expect(correctOption([])).toBeNull();
    expect(correctOption([null, undefined, opt('x', true)]).pinyin).toBe('x');
  });

  test('FIRST match wins when two are flagged — matches the click handler', () => {
    // A generator bug (#280/#281) must not make the highlighted option disagree
    // with the one the click actually scored.
    const two = [opt('first', true), opt('second', true)];
    expect(correctOption(two).pinyin).toBe('first');
  });
});

describe('shouldReveal (issue-344)', () => {
  test('a WRONG pick reveals', () => {
    expect(shouldReveal(false, FOUR)).toBe(true);
  });

  test('a CORRECT pick does NOT reveal — the success path keeps its timing', () => {
    // BUG SHAPE. The reveal shares provideFeedback with the success path, so a
    // predicate that fired on both would add REVEAL_MS to every right answer —
    // the common case, and the one #108/#137 worked to keep fast.
    expect(shouldReveal(true, FOUR)).toBe(false);
  });

  test('a wrong pick with NO correct option degrades to today: no reveal', () => {
    expect(shouldReveal(false, [opt('a'), opt('b')])).toBe(false);
    expect(shouldReveal(false, undefined)).toBe(false);
  });

  test('REVEAL_MS is bounded — this is paid PER WRONG ANSWER', () => {
    expect(REVEAL_MS).toBeGreaterThan(0);
    expect(REVEAL_MS).toBeLessThanOrEqual(2000);
  });
});
