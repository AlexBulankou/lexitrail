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

// issue-188: states BELOW 0 are the graduation ladder, and they are why a
// diligent learner's daily load can finally shrink.
//
// Before this, `updateRecallState` floored at 0 and 0 meant "7 days", so a word
// answered correctly for the hundredth time came back on the same weekly
// cadence as one answered correctly once. The due-count for a steady learner
// therefore grew without bound: every word ever studied returned weekly for
// ever, which is the opposite of what spaced repetition is for and a direct
// cause of overwhelm-and-quit.
//
// The ladder extends DOWNWARD rather than adding a second field because
// `recall_state` is already a signed `INT NOT NULL` (terraform/schema-tables.sql)
// with no CHECK constraint, and the API passes it through unvalidated
// (`routes/userwords.py::update_recall_state` reads `data.get('recall_state')`).
// So negatives persist and round-trip today — no migration, no schema change,
// and one number still fully describes a word's scheduling.
//
// Lapses need no special case: an incorrect answer is `state + 1`, so a word at
// -3 (90 days) that is missed climbs back to -2, then -1, and a further miss
// puts it at 0 and then into the struggling range. Mastery decays at exactly
// the rate it was earned.
// hc2@ on PR #285: index 0 is NEVER READ -- `srsIntervalMs` enters this branch
// only for state < 0, so the index is always >= 1. It is here as the ladder's
// ORIGIN, and it is DERIVED rather than written as a second `7`, because a
// literal would be a duplicate of INTERVAL_DAYS[0] that nothing forces to agree:
// change the weekly interval there and this array would keep claiming the ladder
// starts at 7, silently.
//
// Deriving it also keeps MASTERY_FLOOR correct by construction. Deleting the
// "dead" element instead -- the natural cleanup -- would shorten the array, move
// the floor from -3 to -2, and drop the 14-day rung entirely. That is caught
// (two tests red, verified), but it is better not to invite the edit.
const GRADUATED_DAYS = [INTERVAL_DAYS[0], 14, 30, 90];

// The furthest a word can graduate. Exported because `updateRecallState` must
// clamp to the SAME floor -- a floor in the writer that disagreed with the
// ladder here would produce states this function silently clamps, i.e. a word
// that keeps "graduating" with no change to when it is next seen.
export const MASTERY_FLOOR = -(GRADUATED_DAYS.length - 1);

// The state TRANSITION lives here, beside the ladder it has to agree with.
//
// It was `useWordsetLoader`'s module-private `updateRecallState`, which meant
// the floor and the ladder sat in different files. My first version of
// issue-188 imported MASTERY_FLOOR across that boundary and left a comment
// asking the next editor to keep them in step -- which is a rule that fires only
// if someone reads it. Co-locating them makes the disagreement unrepresentable
// instead of merely discouraged: there is no second floor to drift.
//
// It also makes the writer TESTABLE. As a private const it had no test at all,
// so the ladder could be correct and the transition still floored at 0 -- the
// feature inert with every srs test green.
export const nextRecallState = (currentRecallState, isCorrect) => {
  const state = currentRecallState | 0;
  // Correct answers move DOWN toward mastery and stop at the last rung; wrong
  // answers move up with no ceiling (srsIntervalMs clamps the reading end).
  return isCorrect ? Math.max(MASTERY_FLOOR, state - 1) : state + 1;
};

export const srsIntervalMs = (recallState) => {
  const state = recallState | 0;
  if (state < 0) {
    const idx = Math.min(-state, GRADUATED_DAYS.length - 1);
    return GRADUATED_DAYS[idx] * DAY_MS;
  }
  const idx = Math.min(state, INTERVAL_DAYS.length - 1);
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
  // TWO SHAPES REACH THIS, and the first version only handled one.
  //
  //   MAPPED  (`useWordsetLoader`'s DUE_TODAY filter, where this was extracted
  //           from): `recall_history[].original_recall_time`, a Date.
  //   RAW     (`useDueToday`, the Today home): `/userwords/query` returns
  //           `recall_histories[].recall_time` -- plural key, different field,
  //           an ISO string. Confirmed against the serializer in
  //           `backend/app/routes/userwords.py`, which builds exactly that.
  //
  // Reading only the mapped shape made this return null for EVERY raw row, and
  // `isDue(state, null)` is TRUE by design (a never-practiced word is due). So
  // the Today home counted every included word as due — the headline silently
  // became "words in your sets", inflated for anyone with any history, and it
  // fails toward MORE work rather than an error anybody would report.
  //
  // My unit tests could not catch this: they mock the row shape, and I mocked
  // the shape I assumed rather than the one the backend sends.
  const history =
    (word && (word.recall_history || word.recall_histories)) || [];

  // The MOST RECENT review, not `history[0]`.
  //
  // Nothing sorts these. The mapped path builds them in the backend's append
  // order and the raw payload appends per result row, so `[0]` is "whichever
  // the query returned first". Taking the max is shape-agnostic and correct
  // whatever the order; with an unsorted history, `[0]` could name an older
  // review and mark a rested word due (or the reverse).
  let newest = null;
  let newestMs = -Infinity;
  for (const entry of history) {
    const value = entry && (entry.original_recall_time || entry.recall_time);
    if (!value) continue;
    const ms = new Date(value).getTime();
    if (Number.isNaN(ms)) continue;
    if (ms > newestMs) { newestMs = ms; newest = value; }
  }
  return newest;
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
// Ties break on the LOWEST wordsetId, not on arrival order.
//
// @ensemble-hc2 caught the first version of this resting on an assumption it
// could not support: it broke ties by keeping whichever set arrived first, and
// the comment claimed that made Start stable day to day because the order
// `getWordsets()` returns is stable. Nothing guarantees that order — the
// backend route is `Wordset.query.all()` with no ORDER BY
// (`backend/app/routes/wordsets.py`), so the ordering is whatever the engine
// returns and may vary between calls.
//
// That is the exact failure the tie-break exists to prevent: with two sets at
// 5 due each, a reordered response would silently swap which one Start opens.
// Sorting on a value the ROW carries rather than on its position makes the
// property hold whatever order the backend chooses, so this no longer depends
// on an unwritten backend contract.
//
// Sets missing an id sort last: `undefined < n` is false, so a malformed row
// can never displace a well-formed one.
export const pickStartSet = (sets) => {
  let best = null;
  for (const s of sets || []) {
    if (!s || !(s.due > 0)) continue;
    if (!best) { best = s; continue; }
    if (s.due > best.due) { best = s; continue; }
    if (s.due === best.due && s.wordsetId < best.wordsetId) best = s;
  }
  return best;
};
