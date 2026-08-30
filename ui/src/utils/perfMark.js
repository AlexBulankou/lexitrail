// issue-266: a programmatic anchor for "the first card is on screen".
//
// The issue's bar is Alex's phrasing — "extremely fast to get to practice" —
// and it asks that the close be a NUMBER. There was no way to produce one:
// `grep performance.(mark|measure|now)` across ui/src returned zero hits, so
// time-to-first-card had no anchor an e2e harness could read.
//
// WHY A MARK RATHER THAN A DOM SELECTOR
// -------------------------------------
// A harness can already wait for `.container` or a card class to appear, and
// that is the tempting zero-app-change option. It is also the one that decays
// silently: the moment the card markup is restyled or renamed, the selector
// starts timing a DIFFERENT thing and keeps reporting a plausible number. A
// named mark breaks loudly instead — the harness finds no entry and says so.
//
// WHY ONCE-ONLY
// -------------
// `performance.mark` appends. A component that re-renders would emit N entries
// and `getEntriesByName(...)[0]` would still read the first, so the bug would
// be invisible in the metric and visible only as a growing buffer. Guarding
// here keeps the entry list meaning what its name says.

const marked = new Set();

/** Mark `name` at most once per page load. Returns true if it actually marked. */
export const markOnce = (name) => {
  if (marked.has(name)) return false;
  marked.add(name);
  try {
    // Absent in older browsers and in some test environments. A missing metric
    // must never break the app it measures.
    if (typeof performance !== 'undefined' && performance.mark) {
      performance.mark(name);
    }
  } catch (e) {
    /* measurement is best-effort by construction */
  }
  return true;
};

/** The anchor an e2e harness reads. Changing this string is a contract change. */
export const FIRST_CARD_MARK = 'lt:first-card';

/** Test-only: the once-guard is module state and would leak across cases. */
export const resetMarksForTest = () => marked.clear();
