import { buildHistoryTiles } from './historyTiles';

describe('buildHistoryTiles (lexitrail#52 bug 2)', () => {
  test('no history → no tiles, zero counts', () => {
    expect(buildHistoryTiles([])).toEqual({ tiles: [], correct: 0, bulk: 0, total: 0 });
    expect(buildHistoryTiles(undefined)).toEqual({ tiles: [], correct: 0, bulk: 0, total: 0 });
    expect(buildHistoryTiles(null)).toEqual({ tiles: [], correct: 0, bulk: 0, total: 0 });
  });

  test('maps recall boolean to correct/wrong and counts correct answers', () => {
    const history = [
      { recall: true, recall_time: '2 hours ago' },
      { recall: false, recall_time: '1 day ago' },
      { recall: true, recall_time: '3 days ago' },
    ];
    const { tiles, correct, total } = buildHistoryTiles(history);
    expect(total).toBe(3);
    expect(correct).toBe(2);
    // recall_history[0] is newest; reversed so newest (recall:true, "2 hours
    // ago") is LAST in the tile row (rendered rightmost).
    expect(tiles.map((t) => t.correct)).toEqual([true, false, true]);
    // #109 added `provenance` to the tile shape. Kept as an EXACT toEqual (not
    // toMatchObject) so a future field cannot slip in unasserted -- the pin is
    // the point, so it is updated rather than loosened.
    expect(tiles[tiles.length - 1]).toEqual({ correct: true, time: '2 hours ago', provenance: null });
  });

  test('caps to the newest `max` tiles but counts all answers', () => {
    // 8 answers, newest-first; recall true on even indices (0,2,4,6) => 4 correct
    const history = Array.from({ length: 8 }, (_, i) => ({
      recall: i % 2 === 0,
      recall_time: `${i} ago`,
    }));
    const { tiles, correct, total } = buildHistoryTiles(history, 6);
    expect(total).toBe(8);
    expect(correct).toBe(4); // count is over the full history, not just shown tiles
    expect(tiles).toHaveLength(6); // only the newest 6 are drawn
    // newest entry (index 0, "0 ago") is the last tile after reverse
    expect(tiles[tiles.length - 1].time).toBe('0 ago');
  });
});

// --- #109 (RD-6 slice A): bulk vs earned vs unknown -------------------------
describe('provenance (#109)', () => {
  const row = (recall, provenance) => ({ recall, recall_time: 't', provenance });

  it('carries the row provenance onto the tile, unchanged', () => {
    const { tiles } = buildHistoryTiles([
      row(true, 'bulk'), row(true, 'single'), row(true, undefined),
    ]);
    // tiles read oldest -> newest, i.e. reversed from the input
    expect(tiles.map((t) => t.provenance)).toEqual([null, 'single', 'bulk']);
  });

  it('counts bulk POSITIVELY and never as correct-minus-earned', () => {
    // 🔴 The bug shape this pins. ~94k rows predate the column, so every one of
    // them is provenance-null. A `correct - earned` count would report all
    // three of these as bulk and tell the learner their whole history was one
    // tap, on the strength of a column that did not exist when they answered.
    const unknownHistory = [row(true), row(true), row(true)];
    const { correct, bulk } = buildHistoryTiles(unknownHistory);
    expect(correct).toBe(3);
    expect(bulk).toBe(0);
  });

  it('counts only rows that are BOTH correct and known-bulk', () => {
    const { correct, bulk, total } = buildHistoryTiles([
      row(true, 'bulk'), row(true, 'bulk'), row(true, 'single'),
      row(false, 'bulk'),   // a wrong answer is not a green tile to explain
      row(true, undefined), // unknown: silent, not attributed either way
    ]);
    expect(total).toBe(5);
    expect(correct).toBe(4);
    expect(bulk).toBe(2);
  });

  it('is unchanged for history written before the column existed', () => {
    // The regression that matters on deploy day: every existing learner's row
    // has no `provenance` key at all, and their card must look exactly as it
    // did yesterday.
    const legacy = [{ recall: true, recall_time: 't' },
                    { recall: false, recall_time: 't' }];
    const { tiles, correct, bulk, total } = buildHistoryTiles(legacy);
    expect({ correct, bulk, total }).toEqual({ correct: 1, bulk: 0, total: 2 });
    expect(tiles.every((t) => t.provenance === null)).toBe(true);
  });
});
