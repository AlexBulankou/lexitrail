import {
  SESSION_SIZES, DEFAULT_SESSION_SIZE, resolveSessionBudget, sessionSizeToken,
  bindSession, sessionOutcome, SessionOutcome, sessionBindingKey, nextSessionBinding, EMPTY_BINDING,
} from './session';

const words = (n) => Array.from({ length: n }, (_, i) => ({ word_id: i + 1 }));

describe('session size picker (revamp-2026-09)', () => {
  test('offers exactly 10, 20, 100 and whole set', () => {
    expect(SESSION_SIZES).toEqual([10, 20, 100, 'all']);
  });

  test('resolves URL tokens; garbage falls back to the default, never to unbounded', () => {
    expect(resolveSessionBudget('10')).toBe(10);
    expect(resolveSessionBudget('20')).toBe(20);
    expect(resolveSessionBudget('100')).toBe(100);
    expect(resolveSessionBudget('all')).toBe(Infinity);
    expect(resolveSessionBudget('banana')).toBe(DEFAULT_SESSION_SIZE);
    expect(resolveSessionBudget('15')).toBe(DEFAULT_SESSION_SIZE);
    expect(resolveSessionBudget(null)).toBe(DEFAULT_SESSION_SIZE);
  });

  test('token round-trips', () => {
    for (const s of SESSION_SIZES) expect(sessionSizeToken(resolveSessionBudget(String(s)))).toBe(String(s));
  });

  test('whole set binds every loaded word, once', () => {
    const keys = bindSession(words(149), Infinity);
    expect(keys.size).toBe(149);
  });

  test('a finite budget still caps', () => {
    expect(bindSession(words(149), 100).size).toBe(100);
    expect(bindSession(words(7), 20).size).toBe(7);
  });

  test('whole set with words is COMPLETE, not CLEARED', () => {
    expect(sessionOutcome(bindSession(words(3), Infinity), Infinity)).toBe(SessionOutcome.COMPLETE);
    expect(sessionOutcome(bindSession(words(0), Infinity), Infinity)).toBe(SessionOutcome.EMPTY);
    expect(sessionOutcome(bindSession(words(7), 20), 20)).toBe(SessionOutcome.CLEARED);
  });

  test('changing the budget re-binds; same budget keeps identity', () => {
    const base = { wordsetId: '1', mode: 'PRACTICE', loaded: true, words: words(150) };
    const a = nextSessionBinding(EMPTY_BINDING, { ...base, budget: 10 });
    const same = nextSessionBinding(a, { ...base, budget: 10, words: words(140) });
    expect(same).toBe(a);
    const b = nextSessionBinding(a, { ...base, budget: 100 });
    expect(b).not.toBe(a);
    expect(b.keys.size).toBe(100);
    expect(sessionBindingKey('1', 'PRACTICE', Infinity)).toBe('1|PRACTICE|all');
  });
});
