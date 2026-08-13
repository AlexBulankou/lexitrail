import { srsIntervalMs, isDue, lastRecallTimeOf, isWordDue, dueCount, dueAcrossWordsets } from './srs';

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

// --- the clock snapshot -------------------------------------------------
//
// hc2 found on #130 that `dueCount` binds `now` ONCE and threads it, that the
// choice is deliberate, and that NOTHING PINNED IT: every test above passes an
// explicit NOW, so a regression to a per-element `new Date()` leaves all of
// them green. These tests are that missing pin, and they are written to fail
// on exactly that change.
//
// They count ZERO-ARGUMENT `new Date()` constructions. One-argument
// constructions are the parse of a stored timestamp (`new Date(lastRecallTime)`
// inside `isDue`) and happen once per word by design, so counting those too
// would make the assertion track the input length instead of the clock.
const countBareNowCalls = (fn) => {
  const RealDate = Date;
  const FIXED = NOW.getTime();
  let bare = 0;
  class CountingDate extends RealDate {
    constructor(...args) {
      if (args.length === 0) {
        bare += 1;
        super(FIXED);
      } else {
        super(...args);
      }
    }
    static now() { return FIXED; }
  }
  global.Date = CountingDate;
  try {
    fn();
  } finally {
    global.Date = RealDate;
  }
  return bare;
};

describe('the clock is read once per count, not once per word', () => {
  const manyWords = [word(), word(), word(), word(), word()];

  it('dueCount reads the clock exactly once regardless of list length', () => {
    // Reds at 6 (its own default + one per word) if the threading is dropped.
    expect(countBareNowCalls(() => dueCount(manyWords))).toBe(1);
  });

  it('dueAcrossWordsets reads the clock once for ALL wordsets', () => {
    // Reds at 4 if each wordset binds its own `now`, which would let the first
    // and last set be counted against different instants.
    const entries = [
      { wordsetId: 1, words: manyWords },
      { wordsetId: 2, words: manyWords },
      { wordsetId: 3, words: manyWords },
    ];
    expect(countBareNowCalls(() => dueAcrossWordsets(entries))).toBe(1);
  });

  it('counts a boundary word consistently while the clock ADVANCES mid-count', () => {
    // The behavioural half of the same property: the counting test above shows
    // the clock is read once, this shows why that matters. Every word here sits
    // EXACTLY on its 1-day boundary, so a clock that advances between elements
    // flips them from not-due to due partway through the list and the count
    // lands somewhere between 0 and 5 depending on iteration order.
    const RealDate = Date;
    const boundary = () => word({
      recall_state: 2,
      recall_history: [{ original_recall_time: new RealDate(NOW.getTime() - DAY).toISOString() }],
    });
    const onTheLine = [boundary(), boundary(), boundary(), boundary(), boundary()];
    // Each bare read is 1 ms later than the last, STARTING 2 ms before the
    // boundary. The offset is load-bearing and was chosen by running the
    // mutation, not by eye: `dueCount` evaluates its own default `now` first,
    // so that unused read consumes tick 0. Starting at NOW-1 (the obvious
    // choice) therefore hands the five words NOW..NOW+4 — all past the
    // boundary, all due, count 5 — which is a NON-split value this assertion
    // accepts, and the test passed under the very mutation it exists to catch.
    // Starting at NOW-2 puts the boundary in the MIDDLE of the list: the words
    // read NOW-1..NOW+3, so a per-element clock yields 4 and reds.
    let tick = 0;
    const advancing = () => NOW.getTime() - 2 + (tick++);
    class AdvancingDate extends RealDate {
      constructor(...args) {
        if (args.length === 0) {
          super(advancing());
        } else {
          super(...args);
        }
      }
      static now() { return advancing(); }
    }
    global.Date = AdvancingDate;
    try {
      // One clock read => all five share it => all-or-nothing, never a split.
      expect([0, 5]).toContain(dueCount(onTheLine));
    } finally {
      global.Date = RealDate;
    }
  });
});

describe('dueAcrossWordsets', () => {
  it('totals across wordsets and reports the per-wordset breakdown', () => {
    const entries = [
      { wordsetId: 7, words: [word(), word({ is_included: false })] },   // 1 due
      { wordsetId: 9, words: [word(), word({ recall_history: [] })] },   // 2 due
    ];
    expect(dueAcrossWordsets(entries, NOW)).toEqual({
      total: 3,
      perWordset: [
        { wordsetId: 7, due: 1 },
        { wordsetId: 9, due: 2 },
      ],
    });
  });

  it('reports zero rather than throwing on empty or missing input', () => {
    // The Today home renders this number on first paint, before any fetch has
    // resolved. Throwing here would blank the home screen the habit depends on.
    expect(dueAcrossWordsets([], NOW)).toEqual({ total: 0, perWordset: [] });
    expect(dueAcrossWordsets(undefined, NOW)).toEqual({ total: 0, perWordset: [] });
    expect(dueAcrossWordsets([{ wordsetId: 1 }], NOW)).toEqual({
      total: 0,
      perWordset: [{ wordsetId: 1, due: 0 }],
    });
  });
});
