import { markOnce, FIRST_CARD_MARK, resetMarksForTest } from './perfMark';

describe('markOnce (issue-266)', () => {
  let calls;
  beforeEach(() => {
    resetMarksForTest();
    calls = [];
    // Two instrument facts, both learned the hard way rather than assumed:
    //   1. assigning `global.performance` does NOT override what the module
    //      sees — bare `performance` resolves to `window.performance` in jsdom;
    //   2. this jsdom's `window.performance` has NO `mark` at all, so
    //      `jest.spyOn(window.performance, 'mark')` throws "not a function".
    // (2) is also why the module's `performance.mark &&` guard is load-bearing
    // rather than defensive decoration — this very suite is an environment
    // without it.
    window.performance.mark = (n) => calls.push(n);
  });
  afterEach(() => { delete window.performance.mark; });

  it('marks the first time and reports that it did', () => {
    expect(markOnce('a')).toBe(true);
    expect(calls).toEqual(['a']);
  });

  // THE load-bearing case: performance.mark APPENDS, so an unguarded call in a
  // re-rendering component emits N entries. getEntriesByName()[0] would still
  // read the first, so the defect would be invisible in the metric itself.
  it('does not mark again, and says so, on repeat', () => {
    markOnce('a');
    expect(markOnce('a')).toBe(false);
    expect(calls).toEqual(['a']);
  });

  it('tracks names independently', () => {
    markOnce('a');
    expect(markOnce('b')).toBe(true);
    expect(calls).toEqual(['a', 'b']);
  });

  // A missing metric must never break the app it measures. Both arms, because
  // "absent" and "throws" are different failures and only one is obvious.
  it('survives an environment with no performance.mark', () => {
    delete window.performance.mark;   // jsdom's own default state
    expect(() => markOnce('c')).not.toThrow();
    expect(markOnce('c')).toBe(false); // still guarded — the name was consumed
  });

  it('survives performance.mark throwing', () => {
    window.performance.mark = () => { throw new Error('nope'); };
    expect(() => markOnce('d')).not.toThrow();
  });

  // The mark name is a CONTRACT with the e2e harness that reads it. Pinning it
  // so a rename cannot land silently and leave the harness reading nothing.
  it('exports the exact name the harness reads', () => {
    expect(FIRST_CARD_MARK).toBe('lt:first-card');
  });
});
