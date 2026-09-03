// lexitrail#52 bug 2: compute the red/green past-answer history tiles for a word
// card. Alex asked to revert the plain-text "Seen N×, M correct" summary back to
// the at-a-glance tiles view: one tile per past answer, green = correct, red =
// wrong. This is the pure logic behind that render (kept out of the component so
// it can be unit-tested): it returns the correct count, the total, and the tiles
// to draw (newest answers only, ordered oldest→newest so the latest is last).
export const buildHistoryTiles = (recallHistory, max = 6) => {
  const history = Array.isArray(recallHistory) ? recallHistory : [];
  const correct = history.filter((r) => r && r.recall).length;
  // #109 (RD-6): how many of those greens came from the bulk "to all" tap.
  //
  // 🔴 Counted POSITIVELY -- rows we KNOW were bulk -- and never as
  // `correct - earned`. The subtraction would sweep every row of UNKNOWN
  // provenance into "bulk", and ~94k rows predate the column, so a learner
  // would be told their whole history was a bulk tap on the strength of a
  // column that did not exist yet. Unknown is a third state and it must stay
  // silent, not get attributed to whichever side is convenient.
  const bulk = history.filter(
    (r) => r && r.recall && r.provenance === 'bulk').length;
  // recall_history[0] is the most recent entry; take the newest `max` and
  // reverse so the tiles read oldest→newest left-to-right (latest on the right).
  const tiles = history.slice(0, max).reverse().map((r) => ({
    correct: Boolean(r && r.recall),
    time: r && r.recall_time ? r.recall_time : null,
    // #109 (RD-6): 'single' | 'bulk' | null, straight from the row. THREE
    // states, deliberately not a boolean: null means the row predates the
    // column and its provenance is genuinely UNKNOWN, which must not render as
    // earned. Collapsing null into either known value rebuilds the bug one
    // layer up.
    provenance: r && r.provenance ? r.provenance : null,
  }));
  return { tiles, correct, bulk, total: history.length };
};
