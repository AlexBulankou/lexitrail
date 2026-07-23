// lexitrail#52 bug 2: compute the red/green past-answer history tiles for a word
// card. Alex asked to revert the plain-text "Seen N×, M correct" summary back to
// the at-a-glance tiles view: one tile per past answer, green = correct, red =
// wrong. This is the pure logic behind that render (kept out of the component so
// it can be unit-tested): it returns the correct count, the total, and the tiles
// to draw (newest answers only, ordered oldest→newest so the latest is last).
export const buildHistoryTiles = (recallHistory, max = 6) => {
  const history = Array.isArray(recallHistory) ? recallHistory : [];
  const correct = history.filter((r) => r && r.recall).length;
  // recall_history[0] is the most recent entry; take the newest `max` and
  // reverse so the tiles read oldest→newest left-to-right (latest on the right).
  const tiles = history.slice(0, max).reverse().map((r) => ({
    correct: Boolean(r && r.recall),
    time: r && r.recall_time ? r.recall_time : null,
  }));
  return { tiles, correct, total: history.length };
};
