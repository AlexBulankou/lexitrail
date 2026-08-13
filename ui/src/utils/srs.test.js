import { srsIntervalMs, isDue, lastRecallTimeOf, isWordDue, dueCount } from './srs';

const DAY = 24 * 60 * 60 * 1000;
const NOW = new Date('2026-08-13T12:00:00Z');
const ago = (ms) => new Date(NOW.getTime() - ms).toISOString();

// recall_state semantics, from srs.js: a CORRECT answer moves the state toward
// 0 (mastered), so a LOWER state earns a LONGER rest. Pinning that direction
// explicitly because it is the counter-intuitive half -- an off-by-one or a
// reversed comparator would still "work" and would silently re-review mastered
// words while resting the struggling ones.
describe('srsIntervalMs', () => {
  it('rests mastered words longest and struggling words not at all', () => {
    expect(srsIntervalMs(0)).toBe(7 * DAY);
    expect(srsIntervalMs(1)).toBe(3 * DAY);
    expect(srsIntervalMs(2)).toBe(1 * DAY);
    expect(srsIntervalMs(3)).toBe(0);
  });

  it('clamps out-of-range states instead of returning undefined', () => {
    expect(srsIntervalMs(99)).toBe(0);
    expect(srsIntervalMs(-5)).toBe(7 * DAY);
  });
});

describe('isDue', () => {
  it('treats a never-practiced word as due', () => {
    expect(isDue(0, null, NOW)).toBe(true);
  });

  it('treats an unparseable timestamp as due rather than never-due', () => {
    // Fail toward SHOWING the word: a word wrongly shown is a small annoyance,
    // one wrongly hidden never resurfaces and silently leaves the rotation.
    expect(isDue(0, 'not-a-date', NOW)).toBe(true);
  });

  it('is due exactly AT the interval boundary, not one tick after', () => {
    expect(isDue(2, ago(1 * DAY), NOW)).toBe(true);
    expect(isDue(2, ago(1 * DAY - 1000), NOW)).toBe(false);
  });

  it('rests a mastered word for a week', () => {
    expect(isDue(0, ago(6 * DAY), NOW)).toBe(false);
    expect(isDue(0, ago(7 * DAY), NOW)).toBe(true);
  });
});

const word = (over = {}) => ({
  is_included: true, recall_state: 2,
  recall_history: [{ original_recall_time: ago(30 * DAY) }],
  ...over,
});

describe('lastRecallTimeOf', () => {
  it('returns null for an empty or missing history rather than throwing', () => {
    expect(lastRecallTimeOf({ recall_history: [] })).toBeNull();
    expect(lastRecallTimeOf({})).toBeNull();
    expect(lastRecallTimeOf(null)).toBeNull();
  });

  it('reads the most recent entry', () => {
    expect(lastRecallTimeOf(word())).toBe(ago(30 * DAY));
  });
});

describe('isWordDue', () => {
  it('is due when the interval has elapsed', () => {
    expect(isWordDue(word(), NOW)).toBe(true);
  });

  it('EXCLUDED words are never due, however overdue', () => {
    // The learner opted out. A due count including them would start a session
    // containing words they removed.
    expect(isWordDue(word({ is_included: false }), NOW)).toBe(false);
  });

  it('a never-practiced included word is due', () => {
    expect(isWordDue(word({ recall_history: [] }), NOW)).toBe(true);
  });
});

describe('dueCount', () => {
  it('counts only included, due words', () => {
    const words = [
      word(),                                              // due
      word({ recall_history: [] }),                        // never practiced -> due
      word({ is_included: false }),                        // excluded -> not
      word({ recall_state: 0, recall_history: [{ original_recall_time: ago(1 * DAY) }] }), // resting
    ];
    expect(dueCount(words, NOW)).toBe(2);
  });

  it('handles an empty or missing list', () => {
    expect(dueCount([], NOW)).toBe(0);
    expect(dueCount(undefined, NOW)).toBe(0);
  });
});
