// Spaced-repetition scheduling for the "Due today" queue (ITP FEAT-2).
//
// recall_state semantics (see useWordsetLoader.updateRecallState): a correct
// answer decreases the state toward 0 (mastered); an incorrect answer
// increases it (struggling). So a LOWER state means better mastery and earns
// a longer rest before the word is worth reviewing again.

const DAY_MS = 24 * 60 * 60 * 1000;

// Review interval (in days) indexed by recall_state, clamped to [0, 4].
// Mastered words (state 0) rest a week; struggling words (state >= 3) are due
// again immediately.
const INTERVAL_DAYS = [7, 3, 1, 0, 0];

export const srsIntervalMs = (recallState) => {
  const idx = Math.min(Math.max(recallState | 0, 0), INTERVAL_DAYS.length - 1);
  return INTERVAL_DAYS[idx] * DAY_MS;
};

// A word is "due" when it has never been practiced, or when at least its
// recall-state interval has elapsed since the most recent review.
export const isDue = (recallState, lastRecallTime, now = new Date()) => {
  if (!lastRecallTime) return true;
  const last = new Date(lastRecallTime).getTime();
  if (Number.isNaN(last)) return true;
  return now.getTime() - last >= srsIntervalMs(recallState);
};

// The "last review" timestamp for a userword, as the API returns it.
//
// issue-107: this extraction was duplicated inline in useWordsetLoader's
// DUE_TODAY branch. The Today home needs the same answer ACROSS wordsets, and
// two copies of "which field means last-reviewed" is how the home screen and
// the practice loop end up disagreeing about what is due -- a disagreement
// that would show as a count that does not match the session it starts.
export const lastRecallTimeOf = (word) => {
  const history = (word && word.recall_history) || [];
  return history.length > 0 ? history[0].original_recall_time : null;
};

// Is this userword due for review right now?
//
// Excluded words are never due: `is_included === false` means the learner has
// removed it from their set, and a due count that included them would send
// people into a session containing words they opted out of.
export const isWordDue = (word, now = new Date()) => {
  if (!word || !word.is_included) return false;
  return isDue(word.recall_state, lastRecallTimeOf(word), now);
};

// How many of these userwords are due — the Today home's headline number.
//
// `now` is bound ONCE here and threaded into every `isWordDue`, rather than
// letting each element read its own clock. That is deliberate and is pinned by
// test: with a per-element `new Date()` a word sitting exactly on its interval
// boundary can be counted differently from its neighbours within a single
// count, so the headline number would not correspond to any one instant.
export const dueCount = (words, now = new Date()) =>
  (words || []).filter((w) => isWordDue(w, now)).length;

// The Today home is cross-wordset by definition, so it needs one number over
// every wordset rather than the per-wordset count `useWordsetLoader` produces.
//
// Client-side on purpose (issue-107 recommendation (a)): `getWordsets()`
// already hides the test/HSK7 sets so N is small, and a backend endpoint would
// make this issue undeployable for reasons unrelated to its merits — lexitrail
// has no Cloud Build trigger, so backend deploys are the blocked half (#77)
// while the UI ships today.
//
// Takes already-fetched lists rather than fetching, so the aggregation stays
// pure and testable and the caller keeps control of request fan-out.
//
// The SAME `now` spans every wordset, not merely every word within one. A
// clock bound per wordset would let the first and last set be counted against
// different instants, so the total would not equal the session Start opens.
export const dueAcrossWordsets = (entries, now = new Date()) => {
  const perWordset = (entries || []).map((entry) => ({
    wordsetId: entry && entry.wordsetId,
    due: dueCount(entry && entry.words, now),
  }));
  return {
    total: perWordset.reduce((sum, e) => sum + e.due, 0),
    perWordset,
  };
};
