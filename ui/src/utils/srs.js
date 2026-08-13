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
export const dueCount = (words, now = new Date()) =>
  (words || []).filter((w) => isWordDue(w, now)).length;
