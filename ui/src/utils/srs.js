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
