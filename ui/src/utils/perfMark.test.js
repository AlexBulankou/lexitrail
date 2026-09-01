import {
  markOnce, FIRST_CARD_MARK, AUTH_SETTLED_MARK, WORDSETS_REQUESTED_MARK,
  resetMarksForTest,
} from './perfMark';

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

// ── issue-266: the two cuts that split `app` ─────────────────────────────────
// These names are read by e2e/time_to_first_card.py --phases. A rename here is
// a contract change, and the harness reports CANNOT-TELL rather than guessing,
// so a silent rename shows up as a phase that stopped being measurable.

describe('the app-phase marks (issue-266)', () => {
  beforeEach(resetMarksForTest);

  it('exports the exact names the harness reads', () => {
    expect(AUTH_SETTLED_MARK).toBe('lt:auth-settled');
    expect(WORDSETS_REQUESTED_MARK).toBe('lt:wordsets-requested');
  });

  // The three names are SUBTRACTED from one another to produce the phases. If
  // any two collided, one phase would read as exactly zero and the other would
  // absorb it -- a plausible split that silently attributes one phase's cost to
  // its neighbour. Cheaper to pin than to notice in a number.
  it('are three distinct names', () => {
    const names = [FIRST_CARD_MARK, AUTH_SETTLED_MARK, WORDSETS_REQUESTED_MARK];
    expect(new Set(names).size).toBe(3);
  });

  // Once-ever is per NAME, not global -- the phases need all three from one
  // page load, so a guard that stopped after the first mark of any name would
  // leave two phases permanently unmeasurable.
  it('each mark once, independently of the others', () => {
    const calls = [];
    window.performance.mark = (n) => calls.push(n);
    try {
      expect(markOnce(AUTH_SETTLED_MARK)).toBe(true);
      expect(markOnce(WORDSETS_REQUESTED_MARK)).toBe(true);
      expect(markOnce(FIRST_CARD_MARK)).toBe(true);
      expect(markOnce(AUTH_SETTLED_MARK)).toBe(false);
      expect(calls).toEqual([AUTH_SETTLED_MARK, WORDSETS_REQUESTED_MARK, FIRST_CARD_MARK]);
    } finally {
      delete window.performance.mark;
    }
  });
});
