import { buildHistoryTiles } from './historyTiles';

describe('buildHistoryTiles (lexitrail#52 bug 2)', () => {
  test('no history → no tiles, zero counts', () => {
    expect(buildHistoryTiles([])).toEqual({ tiles: [], correct: 0, total: 0 });
    expect(buildHistoryTiles(undefined)).toEqual({ tiles: [], correct: 0, total: 0 });
    expect(buildHistoryTiles(null)).toEqual({ tiles: [], correct: 0, total: 0 });
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
    expect(tiles[tiles.length - 1]).toEqual({ correct: true, time: '2 hours ago' });
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
