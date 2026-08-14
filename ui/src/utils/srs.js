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
// Takes already-fetched entries rather than fetching, so the aggregation stays
// pure and testable and the caller keeps control of request fan-out.
//
// The SAME `now` spans every wordset, not merely every word within one. A
// clock bound per wordset would let the first and last set be counted against
// different instants, so the total would not equal the session Start opens.
//
// 🔴 This REPLACES `dueAcrossWordsets`, which returned a bare total. That
// function was written that way on hc2's review of #131 — it had returned
// `{ total, perWordset }` on the GUESS that a Today view would want a
// "which set" affordance, and an unused return field reads as a contract
// someone must preserve. The right condition for re-adding it was named there:
// "when a caller needs it, at which point the shape can be chosen against a
// real use rather than a guess." That caller is now real — `Today`'s single
// Start action has to open ONE wordset, because the practice route is
// `/game/:wordsetId/:mode`. So the shape is chosen against that use: the
// per-set breakdown, and the total derived from it rather than counted twice.
//
// Both invariants the old function was pinned on are carried over to this one
// by test (one clock across all sets; empty/missing input reports zero rather
// than throwing) — a replaced function must not take its coverage with it.
export const dueByWordset = (entries, now = new Date()) =>
  (entries || []).map((entry) => ({
    wordsetId: entry && entry.wordsetId,
    description: (entry && entry.description) || '',
    due: dueCount(entry && entry.words, now),
  }));

// The headline number, derived from the breakdown rather than counted again.
//
// Deliberately a sum over the SAME array the Start button chooses from: if this
// counted independently, the home could show "12 due" and open a session with
// a different set of words, which is the one inconsistency a habit screen
// cannot survive.
export const totalDue = (sets) =>
  (sets || []).reduce((sum, s) => sum + ((s && s.due) || 0), 0);

// Which wordset the single Start action opens: the one with the most due words.
//
// Returns null when nothing is due, so the caller renders "all caught up"
// rather than a Start button that opens an empty session.
//
// Ties keep the EARLIER set (strict `>`), so the order `getWordsets()` returns
// is the tiebreak rather than an arbitrary one. That matters for the habit:
// two sets at 5 due each must open the same session today and tomorrow, or
// Start becomes unpredictable.
export const pickStartSet = (sets) => {
  let best = null;
  for (const s of sets || []) {
    if (!s || !(s.due > 0)) continue;
    if (!best || s.due > best.due) best = s;
  }
  return best;
};
