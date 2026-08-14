import {
  SESSION_BUDGET, SESSION_MODES, isSessionMode, wordKey,
  bindSession, sessionRemaining, sessionProgress, sessionOutcome, SessionOutcome,
} from './session';
import { DEFAULT_GOAL } from './streak';

const w = (id, over = {}) => ({ word_id: id, word_index: id, ...over });
const many = (n, from = 1) => Array.from({ length: n }, (_, i) => w(from + i));

describe('SESSION_BUDGET', () => {
  it('IS the daily streak goal, not a coincidentally equal number', () => {
    // Load-bearing: finishing one session has to be exactly what meets the
    // daily goal the streak badge and the Today home already display. Two
    // independent constants would drift, and the loop would stop closing --
    // "session complete" over "8/10 words today" reads as a bug to a learner.
    expect(SESSION_BUDGET).toBe(DEFAULT_GOAL);
  });
});

describe('isSessionMode', () => {
  it('bounds practice and due-today, and nothing else', () => {
    expect(SESSION_MODES).toEqual(['PRACTICE', 'DUE_TODAY']);
    expect(isSessionMode('PRACTICE')).toBe(true);
    expect(isSessionMode('DUE_TODAY')).toBe(true);
  });

  it('leaves the browse and test modes alone', () => {
    // SHOW_EXCLUDED is a browse view: capping it would hide excluded words
    // with no route to them. TEST caps itself at 20 in useWordsetLoader, and
    // two competing caps produce a "20-question test" that stops at 10.
    expect(isSessionMode('SHOW_EXCLUDED')).toBe(false);
    expect(isSessionMode('TEST')).toBe(false);
    expect(isSessionMode(undefined)).toBe(false);
  });
});

describe('wordKey', () => {
  it('keys on word_id, NOT the positional word_index', () => {
    // `word_index` is a per-load counter (`wordIndex++`), so a refetch can
    // hand the same index to a different word. Keying on it would silently
    // swap which words are in your session across a reload.
    expect(wordKey(w(7, { word_index: 0 }))).toBe(7);
    expect(wordKey({ word_index: 3 })).toBeNull();
    expect(wordKey(null)).toBeNull();
  });

  it('treats id 0 as a real id, not as absent', () => {
    // A `!word_id` guard would drop it -- and the first row of a fixture is
    // exactly where a 0 id shows up.
    expect(wordKey(w(0))).toBe(0);
  });
});

describe('bindSession', () => {
  it('captures at most the budget, in queue order', () => {
    const s = bindSession(many(25), 10);
    expect(s.size).toBe(10);
    expect(s.has(1)).toBe(true);
    expect(s.has(10)).toBe(true);
    expect(s.has(11)).toBe(false);
  });

  it('captures everything when the queue is smaller than the budget', () => {
    expect(bindSession(many(4), 10).size).toBe(4);
  });

  it('survives an empty, missing or malformed queue', () => {
    expect(bindSession([], 10).size).toBe(0);
    expect(bindSession(undefined, 10).size).toBe(0);
    expect(bindSession([null, {}, w(3)], 10)).toEqual(new Set([3]));
  });
});

describe('the session is BOUND ONCE — the property this whole module exists for', () => {
  it('does not refill as the live queue drains', () => {
    // THE bug being prevented, stated as a test rather than a comment.
    //
    // `toShow.slice(0, BUDGET)` on every render is the obvious implementation
    // and is endless: the queue shrinks as words are memorized, so a fresh
    // slice pulls the next unseen word in behind it -- 10 cards in, 10 cards
    // left, forever. Here the captured set is fixed, so draining the queue
    // drains the session.
    const queue = many(25);
    const session = bindSession(queue, 10);

    // Memorize the first five: they leave `toShow`, and words 11-15 are now
    // within the first 10 positions of the live queue.
    const afterFive = queue.slice(5);
    const remaining = sessionRemaining(afterFive, session);

    expect(remaining.map(wordKey)).toEqual([6, 7, 8, 9, 10]);
    expect(remaining.some((x) => wordKey(x) > 10)).toBe(false);
    expect(sessionProgress(session, remaining.length)).toEqual({ done: 5, total: 10, percent: 50 });
  });

  it('reaches empty when the captured words are done, with the set NOT exhausted', () => {
    const queue = many(25);
    const session = bindSession(queue, 10);
    const afterTen = queue.slice(10); // 15 words still available in the wordset

    expect(sessionRemaining(afterTen, session)).toEqual([]);
    expect(afterTen.length).toBe(15); // the finish line is the SESSION's, not the set's
    expect(sessionProgress(session, 0)).toEqual({ done: 10, total: 10, percent: 100 });
  });

  it('counts a word that leaves the queue WITHOUT being practiced as done', () => {
    // Excluding a word mid-session removes it from `toShow`. It stays in the
    // denominator -- it was part of what you set out to do -- so progress
    // advances rather than the session becoming unfinishable.
    const queue = many(10);
    const session = bindSession(queue, 10);
    const afterExcludingOne = queue.filter((x) => wordKey(x) !== 4);

    expect(sessionProgress(session, sessionRemaining(afterExcludingOne, session).length))
      .toEqual({ done: 1, total: 10, percent: 10 });
  });
});

describe('sessionProgress', () => {
  it('denominates on the CAPTURED size, never on the budget', () => {
    // A 4-word due queue is a 4-card session. "1 of 10" there promises six
    // cards that do not exist, and the bar can never reach 100%.
    const small = bindSession(many(4), 10);
    expect(sessionProgress(small, 3)).toEqual({ done: 1, total: 4, percent: 25 });
  });

  it('cannot run backwards or past the end on a nonsense remaining count', () => {
    const s = bindSession(many(10), 10);
    expect(sessionProgress(s, 99)).toEqual({ done: 0, total: 10, percent: 0 });
    expect(sessionProgress(s, -3).done).toBe(10);
  });

  it('reports zero rather than dividing by zero on an empty session', () => {
    expect(sessionProgress(new Set(), 0)).toEqual({ done: 0, total: 0, percent: 0 });
    expect(sessionProgress(null, 0)).toEqual({ done: 0, total: 0, percent: 0 });
  });
});

describe('sessionOutcome — the AC-mandated distinction', () => {
  it('separates "finished the session" from "ran out of cards"', () => {
    expect(sessionOutcome(bindSession(many(25), 10), 10)).toBe(SessionOutcome.COMPLETE);
    expect(sessionOutcome(bindSession(many(4), 10), 10)).toBe(SessionOutcome.CLEARED);
  });

  it('never celebrates a session that had nothing in it', () => {
    expect(sessionOutcome(bindSession([], 10), 10)).toBe(SessionOutcome.EMPTY);
    expect(sessionOutcome(null, 10)).toBe(SessionOutcome.EMPTY);
  });

  it('is decided by what was CAPTURED, so it cannot change as the queue drains', () => {
    // The outcome is a property of the session you started, not of the moment
    // you finish it -- otherwise a full session would report CLEARED at the
    // end, when the live queue is empty.
    const s = bindSession(many(25), 10);
    expect(sessionOutcome(s, 10)).toBe(SessionOutcome.COMPLETE);
    expect(sessionOutcome(s, 10)).toBe(SessionOutcome.COMPLETE);
  });
});
