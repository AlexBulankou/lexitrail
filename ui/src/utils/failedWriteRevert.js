// R3-BUG-3 (lexitrail#45) — revert an optimistic word write whose PUT failed.
//
// The three write sites in `useWordsetLoader` are optimistic: they mutate the
// visible list, fire `updateUserWordRecall`, and — before this — did nothing on
// rejection but `console.error`. So a failed write left the UI showing a state
// the server never accepted, and `removeWordAtIndex` had already dropped the
// word from the list the learner would have used to retry. Silent divergence.
//
// 🔑 WHY THIS RESTORES BY IDENTITY RATHER THAN INVERTING THE REORDER.
// The optimistic path runs `updateWordListAfterAction`, which removes the word
// AND re-picks/reorders around `maxWordsToShow`. Inverting that is not
// `setState(previous)`, and an inverse that is subtly wrong produces a third
// state — neither the pre-write list nor the post-write one — which nobody
// downstream can distinguish from success. So this does not invert anything:
// it finds the word by `word_id` and restores the two server-owned fields.
//
// ⚠️ The index is NOT the identity. The reorder moves words, so the position a
// write was issued at routinely no longer holds that word by the time the PUT
// rejects. Keying on index would restore the WRONG word's fields, which is
// worse than the bug — it manufactures a second divergence while appearing to
// fix the first.

/**
 * Restore the server-owned fields of one word after its write failed.
 *
 * Pure: returns a new array, mutates nothing.
 *
 * @param {Array<object>} words     the CURRENT list (not a stale snapshot)
 * @param {object} priorWord        the word as it was BEFORE the optimistic write
 * @returns {Array<object>}         a new list with that word's state restored
 */
export function revertWordWrite(words, priorWord) {
  if (!Array.isArray(words) || !priorWord || priorWord.word_id === undefined) {
    // Nothing safe to do. Returning the input unchanged is deliberate: a revert
    // helper that throws would turn a failed write into a crashed render.
    return Array.isArray(words) ? words : [];
  }

  const i = words.findIndex((w) => w && w.word_id === priorWord.word_id);

  if (i === -1) {
    // The optimistic path removed it. Re-append rather than drop it.
    //
    // ⚠️ Stated trade-off: the ORIGINAL POSITION is not recoverable once
    // `updateWordListAfterAction` has reordered, so the word comes back at the
    // end rather than where it was. That is a deliberate choice of a visible,
    // correct-state imperfection over an invisible, lost one — the learner can
    // see and redo the action, which is the whole point of reverting.
    return [...words, { ...priorWord }];
  }

  const next = [...words];
  next[i] = {
    ...next[i],
    recall_state: priorWord.recall_state,
    is_included: priorWord.is_included,
  };
  return next;
}

/**
 * Was this word dropped from the visible list by the optimistic update?
 *
 * Callers need this to decide whether a counter (`totalToShow`) also has to be
 * put back — restoring the word without restoring the count leaves the two
 * disagreeing, which is its own quiet wrongness.
 */
export function wasWordRemoved(words, priorWord) {
  if (!Array.isArray(words) || !priorWord || priorWord.word_id === undefined) return false;
  return !words.some((w) => w && w.word_id === priorWord.word_id);
}
