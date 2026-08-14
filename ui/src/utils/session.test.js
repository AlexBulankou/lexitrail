import {
  sessionVisibleIndices,
  SESSION_BUDGET, SESSION_MODES, isSessionMode, wordKey,
  bindSession, sessionRemaining, sessionProgress, sessionOutcome, SessionOutcome,
  nextSessionBinding, sessionBindingKey, EMPTY_BINDING, windowHasSessionWord,
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

describe('nextSessionBinding — the read-time gate hc2 caught missing on #134', () => {
  const practice = { wordsetId: 1, mode: 'PRACTICE', loaded: true, words: many(25), budget: 10 };

  it('binds on a session mode with a loaded queue', () => {
    const b = nextSessionBinding(EMPTY_BINDING, practice);
    expect(b.key).toBe('1|PRACTICE');
    expect(b.keys.size).toBe(10);
  });

  it('🔴 CLEARS when the mode changes to a browse view in place', () => {
    // THE REGRESSION. `Game` is one instance across a param-only route change
    // (React Router v6 does not remount `/game/:wordsetId/:mode?` without a
    // `key`), and `toggleWordsetFilter` navigates PRACTICE -> SHOW_EXCLUDED
    // without touching the ref. Gating only at bind time left the practice
    // session's ids filtering the excluded-words list -- near-empty for a
    // typical case, so the browse view rendered the COMPLETION screen.
    const bound = nextSessionBinding(EMPTY_BINDING, practice);
    const after = nextSessionBinding(bound, { ...practice, mode: 'SHOW_EXCLUDED' });

    expect(after.keys).toBeNull();
    expect(after).toEqual(EMPTY_BINDING);
  });

  it('does not bind TEST either, which caps itself at 20', () => {
    expect(nextSessionBinding(EMPTY_BINDING, { ...practice, mode: 'TEST' }).keys).toBeNull();
  });

  it('rebinds a FRESH session on the way back from the browse view', () => {
    const bound = nextSessionBinding(EMPTY_BINDING, practice);
    const browsing = nextSessionBinding(bound, { ...practice, mode: 'SHOW_EXCLUDED' });
    const back = nextSessionBinding(browsing, practice);

    expect(back.key).toBe('1|PRACTICE');
    expect(back.keys.size).toBe(10);
    expect(back).not.toBe(bound); // a new session, not the old set resurrected
  });

  it('returns the SAME OBJECT while the pair is unchanged', () => {
    // Identity, not just equality: this runs on every render, and a fresh Set
    // each time would re-bind against the SHRINKING queue -- the endless-list
    // bug wearing a different hat.
    const bound = nextSessionBinding(EMPTY_BINDING, practice);
    const rerender = nextSessionBinding(bound, { ...practice, words: many(20, 6) });

    expect(rerender).toBe(bound);
  });

  it('rebinds when the WORDSET changes under the same instance', () => {
    const bound = nextSessionBinding(EMPTY_BINDING, practice);
    const other = nextSessionBinding(bound, { ...practice, wordsetId: 2, words: many(25, 100) });

    expect(other.key).toBe('2|PRACTICE');
    expect(other.keys.has(100)).toBe(true);
    expect(other.keys.has(1)).toBe(false);
  });

  it('stays unbound until the queue is loaded, without carrying a stale pair', () => {
    const bound = nextSessionBinding(EMPTY_BINDING, practice);
    // Navigating to another wordset whose fetch is still in flight: the old
    // pair's set must NOT apply for the duration of the fetch.
    const loading = nextSessionBinding(bound, { ...practice, wordsetId: 2, loaded: false, words: [] });

    expect(loading).toEqual(EMPTY_BINDING);
  });

  it('tolerates a missing previous binding', () => {
    expect(nextSessionBinding(undefined, practice).keys.size).toBe(10);
    expect(nextSessionBinding(null, { ...practice, mode: 'SHOW_EXCLUDED' })).toEqual(EMPTY_BINDING);
  });
});


describe('windowHasSessionWord — issue-137, the cards the front-check dropped', () => {
  const keys = bindSession(many(10), 10);   // word_ids 1..10 captured

  it('🔴 stays TRUE when a session word is visible but not FIRST', () => {
    // THE BUG, as a test. The old rule asked only about `displayWords[0]`, so
    // an uncaptured word arriving in slot 0 ended the session while a captured
    // word sat in slot 1 — losing exactly `maxCardsToShow` cards, silently.
    // Measured before the fix: 2 cards visible -> "8 of 10", 1 card -> "9 of 10".
    const visible = [w(99), w(9)];          // uncaptured first, captured second
    expect(windowHasSessionWord(visible, keys)).toBe(true);
  });

  it('goes false only when NOTHING visible belongs to the session', () => {
    expect(windowHasSessionWord([w(99), w(98)], keys)).toBe(false);
  });

  it('is true for a session word in the first slot, as before', () => {
    expect(windowHasSessionWord([w(3), w(99)], keys)).toBe(true);
  });

  it('never ends a NON-session mode on this rule', () => {
    // sessionKeys is null for browse/test; the window rule must not fire there
    // or the excluded-words view would terminate on its own first card.
    expect(windowHasSessionWord([w(99)], null)).toBe(true);
  });

  it('tolerates an empty or missing window', () => {
    expect(windowHasSessionWord([], keys)).toBe(false);
    expect(windowHasSessionWord(undefined, keys)).toBe(false);
  });
});


// --- issue-137: the 1-card layout, and the two costs this retires -----------

describe('sessionVisibleIndices', () => {
  const keys = bindSession(many(10), 10);   // word_ids 1..10 captured

  it('🔴 fills a ONE-card window from the session, not from the front', () => {
    // THE BUG this closes. `windowHasSessionWord` fixed 2+ card layouts and
    // could not fix this one: with a single slot the window rule IS the front
    // rule, so a captured word behind an uncaptured one stayed unreachable
    // (measured: 1 card -> 9 of 10, unchanged by that fix). Choosing the
    // visible set by membership makes the window size irrelevant.
    const queue = [w(99), w(4)];            // uncaptured first, captured second
    expect(sessionVisibleIndices(queue, keys, 1)).toEqual([1]);
  });

  it('returns INDICES into the original list, not the words', () => {
    // Load-bearing: the recall handlers do `toShow[index]`, so a filtered list
    // would desynchronise every handler from the word it marks.
    const queue = [w(99), w(98), w(7)];
    expect(sessionVisibleIndices(queue, keys, 2)).toEqual([2]);
  });

  it('never offers an uncaptured card while captured ones remain', () => {
    // The leak `windowHasSessionWord`'s own comment records as its honest
    // cost: an uncaptured card sharing the window was tappable, i.e. a card
    // outside the session being practisable. It cannot be selected now.
    const queue = [w(1), w(99), w(2), w(98)];
    expect(sessionVisibleIndices(queue, keys, 4)).toEqual([0, 2]);
  });

  it('returns fewer than the window when the session is nearly done', () => {
    // Two captured left, three slots: two indices, not three padded with
    // uncaptured words. This is what makes "cannot run past the budget"
    // structural rather than a guard.
    const queue = [w(99), w(5), w(98), w(6), w(97)];
    expect(sessionVisibleIndices(queue, keys, 3)).toEqual([1, 3]);
  });

  it('returns EMPTY when no captured word remains, at any window size', () => {
    expect(sessionVisibleIndices([w(99), w(98)], keys, 5)).toEqual([]);
  });

  it('is the plain prefix for a NON-session mode', () => {
    // SHOW_EXCLUDED browse and TEST's own cap must keep seeing the queue as
    // the loader orders it.
    const queue = [w(99), w(98), w(97)];
    expect(sessionVisibleIndices(queue, null, 2)).toEqual([0, 1]);
  });

  it('tolerates an empty/missing list and a zero or missing window', () => {
    expect(sessionVisibleIndices([], keys, 3)).toEqual([]);
    expect(sessionVisibleIndices(undefined, keys, 3)).toEqual([]);
    expect(sessionVisibleIndices(many(3), keys, 0)).toEqual([]);
    expect(sessionVisibleIndices(many(3), keys, undefined)).toEqual([]);
  });
});
