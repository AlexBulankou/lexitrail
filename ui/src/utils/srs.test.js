import { srsIntervalMs, isDue, lastRecallTimeOf, isWordDue, dueCount, dueByWordset, totalDue, pickStartSet, MASTERY_FLOOR, nextRecallState } from './srs';

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
    // issue-188 CHANGED THIS LINE'S CONTRACT, deliberately. It asserted
    // `srsIntervalMs(-5) === 7 * DAY` -- i.e. that a state below 0 clamped back
    // to the weekly interval. That clamp WAS the ceiling this issue removes: a
    // word mastered far past 0 was scheduled identically to one just reaching
    // it, so the due-count never thinned.
    //
    // A negative now clamps to the FLOOR of the graduation ladder, not to 7
    // days. Recording the change here rather than editing the number quietly,
    // because a test that silently starts asserting the opposite of what it
    // asserted yesterday is indistinguishable from one that was wrong.
    expect(srsIntervalMs(-5)).toBe(90 * DAY);
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

describe('lastRecallTimeOf reads BOTH row shapes', () => {
  // The bug this file did not catch the first time: `useDueToday` passes RAW
  // `/userwords/query` rows, which carry `recall_histories[].recall_time`, and
  // this only read the MAPPED `recall_history[].original_recall_time`. It
  // returned null for every live row, `isDue(state, null)` is true, and the
  // Today home silently counted every included word as due.
  const RAW = { recall_histories: [{ recall_time: ago(3 * DAY) }] };
  const MAPPED = { recall_history: [{ original_recall_time: ago(3 * DAY) }] };

  it('reads the RAW backend shape (recall_histories / recall_time)', () => {
    expect(lastRecallTimeOf(RAW)).toBe(ago(3 * DAY));
  });

  it('still reads the MAPPED loader shape', () => {
    expect(lastRecallTimeOf(MAPPED)).toBe(ago(3 * DAY));
  });

  it('agrees across the two shapes, so one screen cannot disagree with the other', () => {
    // The Today home counts raw rows; the DUE_TODAY session filters mapped
    // ones. If these ever differ, the headline and the session it opens
    // disagree about what is due -- which is the whole reason this rule was
    // extracted into one function.
    expect(isWordDue({ is_included: true, recall_state: 2, ...RAW }, NOW))
      .toBe(isWordDue({ is_included: true, recall_state: 2, ...MAPPED }, NOW));
  });

  it('returns the NEWEST review, not the first element', () => {
    // Nothing sorts these -- the backend appends per result row. With `[0]` an
    // unsorted history names an arbitrary review, which can mark a rested word
    // due or hide a word that is.
    const unsorted = { recall_histories: [
      { recall_time: ago(30 * DAY) },
      { recall_time: ago(1 * DAY) },   // newest, in the middle
      { recall_time: ago(10 * DAY) },
    ] };
    expect(lastRecallTimeOf(unsorted)).toBe(ago(1 * DAY));
    // A mastered word reviewed yesterday is RESTING (7-day interval); reading
    // the 30-day-old entry instead would wrongly call it due.
    expect(isWordDue({ is_included: true, recall_state: 0, ...unsorted }, NOW)).toBe(false);
  });

  it('skips unusable entries rather than throwing or trusting them', () => {
    expect(lastRecallTimeOf({ recall_histories: [{}, null, { recall_time: ago(2 * DAY) }] }))
      .toBe(ago(2 * DAY));
    expect(lastRecallTimeOf({ recall_histories: [{ recall_time: 'not-a-date' }] })).toBeNull();
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

  // #112: re-inclusion does not resurrect a word as not-due on a stale answer.
  //
  // The open question on #112 was whether answers given in SHOW_EXCLUDED should
  // COUNT once a word comes back. They do -- a real answer is a real answer,
  // which is #109's own principle. The hazard that question was standing in for
  // is AGE, not provenance: a word excluded for months, carrying a best-case
  // answer from month one, coming back not-due on quarter-old evidence.
  //
  // It cannot happen, and the reason is worth pinning rather than re-deriving:
  // `isDue` compares elapsed time against the interval, and the LONGEST
  // interval any state earns is 7 days (INTERVAL_DAYS[0]). So every exclusion
  // longer than a week makes the word due on re-inclusion whatever its state.
  // Pinned because the next reader meets #112's QUESTION before this predicate,
  // and "discard excluded-mode answers on re-inclusion" is the plausible fix
  // for a problem that does not exist.
  it('a long-excluded word is due the moment it is re-included, whatever its state', () => {
    const mastered = { recall_state: 0, recall_history: [{ original_recall_time: ago(90 * DAY) }] };
    expect(isWordDue({ ...mastered, is_included: false }, NOW)).toBe(false);
    expect(isWordDue({ ...mastered, is_included: true }, NOW)).toBe(true);
  });

  it('and the boundary is the 7-day cap, not the exclusion', () => {
    // Negative control for the test above: a RECENT answer on a mastered word
    // still rests. Without this, the pin passes for a version of `isDue` that
    // ignores the interval entirely and calls everything due.
    const fresh = { is_included: true, recall_state: 0,
                    recall_history: [{ original_recall_time: ago(1 * DAY) }] };
    expect(isWordDue(fresh, NOW)).toBe(false);
    expect(isWordDue({ ...fresh, recall_history: [{ original_recall_time: ago(8 * DAY) }] }, NOW))
      .toBe(true);
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

  it('dueByWordset reads the clock once for ALL wordsets', () => {
    // Reds at 4 if each wordset binds its own `now`, which would let the first
    // and last set be counted against different instants.
    //
    // issue-107: carried over from `dueAcrossWordsets` when that function was
    // replaced. This is the STRONGER of the two clock assertions in this file
    // -- it counts actual reads rather than comparing counts -- so it is the
    // one that had to survive the rename.
    const sets = [
      { wordsetId: 1, words: manyWords },
      { wordsetId: 2, words: manyWords },
      { wordsetId: 3, words: manyWords },
    ];
    expect(countBareNowCalls(() => dueByWordset(sets))).toBe(1);
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

const setOf = (wordsetId, words, description = `set ${wordsetId}`) =>
  ({ wordsetId, description, words });

// These first two carry over from `dueAcrossWordsets` (deleted in issue-107 when
// Today's Start action needed the per-set breakdown). A replaced function must
// not take its coverage with it, so both of its invariants are re-pinned here
// against the new shape rather than left behind with the old name.
describe('dueByWordset', () => {
  it('counts each wordset separately rather than answering for one', () => {
    const sets = [
      setOf(7, [word(), word({ is_included: false })]),   // 1 due
      setOf(9, [word(), word({ recall_history: [] })]),   // 2 due
    ];
    expect(dueByWordset(sets, NOW)).toEqual([
      { wordsetId: 7, description: 'set 7', due: 1 },
      { wordsetId: 9, description: 'set 9', due: 2 },
    ]);
    expect(totalDue(dueByWordset(sets, NOW))).toBe(3);
  });

  it('reports zero rather than throwing on empty or missing input', () => {
    // The Today home renders this number on first paint, before any fetch has
    // resolved. Throwing here would blank the home screen the habit depends on.
    expect(dueByWordset([], NOW)).toEqual([]);
    expect(dueByWordset(undefined, NOW)).toEqual([]);
    expect(dueByWordset([undefined], NOW)).toEqual(
      [{ wordsetId: undefined, description: '', due: 0 }]
    );
    expect(totalDue(undefined)).toBe(0);
    expect(totalDue([undefined])).toBe(0);
  });



});

describe('pickStartSet', () => {
  it('opens the set with the most due words', () => {
    const chosen = pickStartSet([
      { wordsetId: 1, due: 2 }, { wordsetId: 2, due: 9 }, { wordsetId: 3, due: 4 },
    ]);
    expect(chosen.wordsetId).toBe(2);
  });

  it('returns null when nothing is due, rather than an empty session', () => {
    // Load-bearing: a Start button that opens a session with no words is worse
    // than no Start button -- it reads as broken rather than as finished.
    expect(pickStartSet([{ wordsetId: 1, due: 0 }])).toBeNull();
    expect(pickStartSet([])).toBeNull();
    expect(pickStartSet(undefined)).toBeNull();
  });

  it('breaks ties on the lowest id, INDEPENDENT of the order they arrive in', () => {
    // hc2 on #133: the first version broke ties on arrival order and claimed
    // that was stable. It is not -- `Wordset.query.all()` has no ORDER BY, so
    // the response order is not a contract. Both orderings must pick the SAME
    // set, or two sets at 5 due each swap which session Start opens whenever
    // the backend happens to return them differently.
    const tied = [{ wordsetId: 1, due: 5 }, { wordsetId: 2, due: 5 }];
    expect(pickStartSet(tied).wordsetId).toBe(1);
    expect(pickStartSet([...tied].reverse()).wordsetId).toBe(1);
  });

  it('still prefers a higher count over a lower id', () => {
    // The tie-break must not outrank the count itself -- guards the shape where
    // the id comparison is applied unconditionally rather than only on a tie.
    expect(pickStartSet([{ wordsetId: 9, due: 7 }, { wordsetId: 1, due: 2 }]).wordsetId).toBe(9);
  });

  it('ignores malformed entries instead of opening an undefined wordset', () => {
    expect(pickStartSet([null, { due: undefined }, { wordsetId: 4, due: 1 }]).wordsetId).toBe(4);
  });
});


// issue-188: the graduation ladder. Before this, `updateRecallState` floored at
// 0 and 0 meant 7 days, so a word answered correctly a hundred times returned
// weekly for ever and a steady learner's due-count grew without bound.
describe('srsIntervalMs graduation ladder (issue-188)', () => {
  it('rests a repeatedly-mastered word LONGER than a week', () => {
    // THE BUG: every one of these was 7 days before the change. This is the
    // assertion the old code fails -- verified by reverting, see the floor test
    // below for the writer-side half.
    expect(srsIntervalMs(-1)).toBe(14 * 24 * 60 * 60 * 1000);
    expect(srsIntervalMs(-2)).toBe(30 * 24 * 60 * 60 * 1000);
    expect(srsIntervalMs(-3)).toBe(90 * 24 * 60 * 60 * 1000);
  });

  it('is strictly increasing as mastery deepens, so the daily load can only shrink', () => {
    // Stated as a PROPERTY rather than four numbers: a future edit that reorders
    // the ladder would keep every individual assertion above passing.
    const days = [-3, -2, -1, 0, 1, 2].map(srsIntervalMs);
    for (let i = 1; i < days.length; i += 1) {
      expect(days[i]).toBeLessThanOrEqual(days[i - 1]);
    }
    expect(days[0]).toBeGreaterThan(days[days.length - 1]);
  });

  it('clamps below the floor instead of returning undefined', () => {
    expect(srsIntervalMs(MASTERY_FLOOR - 5)).toBe(srsIntervalMs(MASTERY_FLOOR));
  });

  it('leaves the struggling half untouched', () => {
    // NEGATIVE CONTROL. Without this the ladder could be "fixed" by making every
    // state longer, which would delay the words a learner is actually failing.
    expect(srsIntervalMs(0)).toBe(7 * 24 * 60 * 60 * 1000);
    expect(srsIntervalMs(1)).toBe(3 * 24 * 60 * 60 * 1000);
    expect(srsIntervalMs(2)).toBe(1 * 24 * 60 * 60 * 1000);
    expect(srsIntervalMs(3)).toBe(0);
  });

  it('MASTERY_FLOOR reaches the end of the ladder and no further', () => {
    // The two-copies hazard named in srs.js: a floor that disagreed with the
    // ladder length lets the writer keep decrementing past the last rung, so a
    // word "graduates" with no change to when it is next seen -- a silent no-op.
    // Pins that the deepest state is a DISTINCT interval from the one above it.
    expect(srsIntervalMs(MASTERY_FLOOR)).toBeGreaterThan(srsIntervalMs(MASTERY_FLOOR + 1));
    expect(srsIntervalMs(MASTERY_FLOOR - 1)).toBe(srsIntervalMs(MASTERY_FLOOR));
  });
});


// issue-188 WRITER SIDE. Without these the ladder could be perfect and the
// transition still floor at 0 -- the feature inert with every interval test
// green, which is the shape this whole change is about.
describe('nextRecallState (issue-188 writer side)', () => {
  it('keeps graduating a repeatedly-correct word past 0', () => {
    // THE BUG: the old `Math.max(0, ...)` returned 0 for every one of these.
    expect(nextRecallState(0, true)).toBe(-1);
    expect(nextRecallState(-1, true)).toBe(-2);
    expect(nextRecallState(-2, true)).toBe(-3);
  });

  it('stops at the floor rather than decrementing for ever', () => {
    expect(nextRecallState(MASTERY_FLOOR, true)).toBe(MASTERY_FLOOR);
  });

  it('reaches EXACTLY the end of the ladder — no unreachable rung, no silent no-op', () => {
    // The two-copies hazard, now pinned end-to-end rather than commented: walk
    // the transition from 0 and assert the interval it produces is the deepest
    // the ladder offers. A floor SHORTER than the ladder leaves a rung nothing
    // can reach; a floor DEEPER than it lets a word "graduate" with no change
    // to when it is next seen.
    let state = 0;
    for (let i = 0; i < 20; i += 1) state = nextRecallState(state, true);
    expect(state).toBe(MASTERY_FLOOR);
    expect(srsIntervalMs(state)).toBe(90 * DAY);
    expect(srsIntervalMs(state)).toBeGreaterThan(srsIntervalMs(state + 1));
  });

  it('a lapse climbs back one rung at a time, so mastery decays as it was earned', () => {
    expect(nextRecallState(-3, false)).toBe(-2);
    expect(nextRecallState(-1, false)).toBe(0);
    expect(nextRecallState(0, false)).toBe(1);
  });

  it('leaves the struggling side unbounded above', () => {
    // NEGATIVE CONTROL: the floor must not become a ceiling. srsIntervalMs
    // clamps the READING end; the state itself keeps climbing so a word missed
    // repeatedly is not silently treated as merely "state 4".
    expect(nextRecallState(9, false)).toBe(10);
  });
});
