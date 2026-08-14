// Bounded practice sessions (lexitrail#108, RD-2) — the finish line.
//
// The list this replaces had no end: `useWordsetLoader` removes a word from
// `toShow` as it is memorized, so the queue drains toward zero and "done"
// means "you exhausted the set". For a 149-word wordset there is no moment of
// completion, no natural stopping point, and nothing that reads as an
// accomplishment — which is what RD-2 was filed about.
//
// 🔴 THE WHOLE DESIGN TURNS ON ONE THING: THE SESSION IS BOUND ONCE.
//
// The obvious implementation — `toShow.slice(0, BUDGET)` on every render — is
// silently the bug it is meant to fix. `toShow` SHRINKS as words are
// memorized, so a fresh slice pulls the next unseen word in behind it: 10
// cards in, 10 cards left, forever. The session would be visually bounded and
// functionally endless, which is worse than today's honest list because the
// progress indicator would actively lie.
//
// So `bindSession` captures identities ONCE, and everything downstream filters
// against that captured set rather than re-slicing. A word that arrives later
// cannot enter the session; a word removed from `toShow` (memorized, or
// excluded mid-session) leaves the remaining queue but stays in the denominator,
// because it was part of what you set out to do.
import { DEFAULT_GOAL } from './streak';

// The budget IS the daily streak goal, deliberately — not a second number that
// happens to be 10 today. Finishing one session should be exactly what meets
// the daily goal the streak badge and the Today home already show; two
// independent constants would drift and the loop would stop closing (finish a
// session, still 8/10 today).
export const SESSION_BUDGET = DEFAULT_GOAL;

// Modes that are SESSIONS. Deliberately a whitelist rather than "everything
// except X": a mode added later must opt in, because silently bounding a mode
// that is meant to be exhaustive is the failure that cannot be seen from here.
//
// SHOW_EXCLUDED is a browse view, not practice — capping it at 10 would hide
// excluded words with no way to reach them. TEST already caps itself at 20
// (`useWordsetLoader`), and two competing caps on one list is how you get a
// "20-question test" that stops at 10.
export const SESSION_MODES = ['PRACTICE', 'DUE_TODAY'];

export const isSessionMode = (mode) => SESSION_MODES.includes(mode);

// The identity of a word, for session membership.
//
// `word_id` is the stable one. `word_index` is a per-load counter assigned in
// `useWordsetLoader` (`word_index: wordIndex++`), so it is positional and a
// reload can hand the same index to a different word — using it here would let
// a refetch silently swap which words are in your session.
export const wordKey = (word) => (word && word.word_id != null ? word.word_id : null);

// Capture the session: the first `budget` words, by identity, ONCE.
//
// Returns a Set so membership is O(1) on every subsequent render — this is
// consulted per word per render, so a linear scan here would be paid on the
// hot path of the card view.
export const bindSession = (words, budget = SESSION_BUDGET) => {
  const keys = (words || [])
    .map(wordKey)
    .filter((k) => k !== null)
    .slice(0, Math.max(0, budget));
  return new Set(keys);
};

// The words still to do IN this session: the live queue, filtered to what was
// captured. Order is the live queue's, so the loader keeps owning sequencing.
export const sessionRemaining = (words, sessionKeys) =>
  (words || []).filter((w) => sessionKeys && sessionKeys.has(wordKey(w)));

// Position within the session, for the progress indicator.
//
// `total` is the size of the CAPTURED set, never the budget: a set with 4 due
// words yields a 4-card session, and showing "1 of 10" there would promise six
// cards that do not exist. It is also never `toShow.length`, which shrinks —
// a denominator that moves is how a progress bar runs backwards.
export const sessionProgress = (sessionKeys, remainingCount) => {
  const total = sessionKeys ? sessionKeys.size : 0;
  const remaining = Math.max(0, Math.min(remainingCount || 0, total));
  const done = total - remaining;
  return { done, total, percent: total > 0 ? (done / total) * 100 : 0 };
};

// Which terminal state this is — the AC's "explicit done, distinct from ran
// out of cards".
//
// COMPLETE   you finished the session you set out to do.
// CLEARED    you finished everything available, and it was less than a full
//            session. Not a lesser outcome — for a due-today queue it is the
//            BEST one ("nothing left due") — but it is a different sentence,
//            and collapsing the two is what makes an endless list feel endless.
// EMPTY      there was nothing to practice at all; never a celebration.
export const SessionOutcome = {
  COMPLETE: 'COMPLETE',
  CLEARED: 'CLEARED',
  EMPTY: 'EMPTY',
};

export const sessionOutcome = (sessionKeys, budget = SESSION_BUDGET) => {
  const total = sessionKeys ? sessionKeys.size : 0;
  if (total === 0) return SessionOutcome.EMPTY;
  return total >= budget ? SessionOutcome.COMPLETE : SessionOutcome.CLEARED;
};

// ─── binding lifecycle ──────────────────────────────────────────────────────
//
// @ensemble-hc2 on #134: checking `isSessionMode` at BIND time and never at
// READ time leaves a live hole. `Game` is one component instance across a
// param-only route change (React Router v6 does not remount `/game/:wordsetId/
// :mode?` without a `key`), and `toggleWordsetFilter` navigates PRACTICE ⇄
// SHOW_EXCLUDED in place without touching the ref. So a bound practice session
// survived into the excluded-words browse view and filtered it down to nothing
// — rendering the completion screen instead of the list, which is the exact
// outcome the `SESSION_MODES` whitelist comment promises cannot happen.
//
// The rule now lives here rather than in the component: no component in this
// repo has a test, so a fix expressed in `Game.js` could only be argued, not
// pinned. Expressed as a pure transition it is testable, and the component is
// left holding one assignment.
export const EMPTY_BINDING = { key: null, keys: null };

// A binding belongs to ONE (wordset, mode) pair. The wordset half is not
// speculative padding: it is the same class of gap, costs nothing here, and a
// binding that outlived a wordset change would silently filter one set's queue
// by another set's word ids.
export const sessionBindingKey = (wordsetId, mode) => `${wordsetId}|${mode}`;

export const nextSessionBinding = (
  previous,
  { wordsetId, mode, loaded, words, budget = SESSION_BUDGET }
) => {
  const prev = previous || EMPTY_BINDING;

  // Not a session mode: unbound, ALWAYS — this is the read-time gate, and it
  // must clear rather than merely decline to bind, or the stale set survives.
  if (!isSessionMode(mode)) return EMPTY_BINDING;

  const key = sessionBindingKey(wordsetId, mode);

  // Already bound to this exact pair: return the SAME object. Identity matters
  // — this runs every render, and a fresh Set each time would re-bind the
  // session against the shrinking queue, which is the endless-list bug wearing
  // a different hat.
  if (prev.key === key) return prev;

  // Nothing loaded yet: stay unbound. Returning `prev` here would let a
  // previous pair's set apply to this one for as long as the fetch takes.
  if (!loaded || !(words && words.length > 0)) return EMPTY_BINDING;

  return { key, keys: bindSession(words, budget) };
};
