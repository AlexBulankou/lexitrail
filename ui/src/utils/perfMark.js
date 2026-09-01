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

// issue-266: the two cuts that split `app` -- DOMContentLoaded -> first-card,
// measured at 1180.8 ms median on prod, 73% of the whole arrival. That number
// came from PerformanceNavigationTiming with no app change at all, which was
// the right order: an in-app mark can only measure a phase somebody already
// suspects, so the browser's own timeline named the phase first and these name
// its parts.
//
// WHY THESE TWO CUTS AND NOT OTHERS
// ---------------------------------
// The probe trace showed the first `/wordsets` request starting 573 ms after
// DOMContentLoaded. That gap is neither network nor render -- it is us not
// asking yet -- and the guest journey's one blocking prerequisite before any
// data fetch is a settled session. So the cuts are placed to make that gap
// attributable rather than to instrument everything:
//
//     DCL -> auth-settled        are we waiting on the session?
//     auth-settled -> requested  are we waiting on ourselves after that?
//     requested -> first-card    are we waiting on the API?
//
// All three are answered by two marks. A third mark on the response would be
// cheap, but `redundant_fetches.py` already owns the request/response picture
// and duplicating it here would give two surfaces that can disagree.
//
// Both are `markOnce`, like FIRST_CARD_MARK: emitted at most once per page
// load, so a re-render or a retry cannot append a second entry that a
// `[0]`-reading harness would silently ignore.

/** Session usable for data fetches -- guest or Google, whichever settles. */
export const AUTH_SETTLED_MARK = 'lt:auth-settled';

/** The first `/wordsets` request leaves the app. */
export const WORDSETS_REQUESTED_MARK = 'lt:wordsets-requested';

/** Test-only: the once-guard is module state and would leak across cases. */
export const resetMarksForTest = () => marked.clear();
