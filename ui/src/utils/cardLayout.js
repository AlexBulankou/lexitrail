// issue-338 — how many cards the practice grid can show, extracted from
// `Game.updateLayout` so it is TESTABLE.
//
// Same reason `indexBy`, `srs` and `session` were extracted: this repo has no
// React testing library (see `useDueToday.js`'s docstring), so logic that stays
// inside a component is logic nothing can pin. The bug this fixes was invisible
// precisely because it lived in a component and failed silently.
//
// THE BUG. `maxRows` was `floor((height - 200) / 280)`. On a phone in LANDSCAPE
// (844x390) that is `floor(0.678)` = **0**, which makes the option-generating
// loop body unreachable, so the option list came back EMPTY and
// `setLayoutClass` was never called. The grid then kept `useState('layout1c1r')`
// — its initial value — and rendered ONE card.
//
// 🔴 Why it went unnoticed for six weeks: `layout1c1r` is a legitimate layout.
// "Chose one card" and "computed nothing and kept the default" produce the
// IDENTICAL observable, so no consumer could tell them apart and nothing threw.
// A default that is also a valid value cannot report its own absence.
//
// The floor of 1 is the fix: a viewport always gets at least a 1x1 grid, so the
// option list is never empty and the initial state can never stand in for a
// failed computation. Measured on prod at 844x390 this yields `4c1r` — four
// cards where there was one.

/** Hard ceilings, unchanged from the original expression. */
const MAX_COLUMNS = 20;
const MAX_ROWS = 7;

/**
 * Grid dimensions that fit `width` x `height`, never smaller than 1x1.
 *
 * ⚠️ `extraWidth` / `extraHeight` are the caller's chrome allowances. They are
 * named for the AXIS THEY ARE SUBTRACTED FROM, which is deliberately NOT what
 * `Game.js` calls them — there the constants are `extraVerticalSpaceNeeded`
 * (100, applied to WIDTH) and `extraHorizontalSpaceNeeded` (200, applied to
 * HEIGHT), i.e. each is named for the opposite axis, with a standing `TODO`
 * saying the numbers are not understood. Renaming them at the call site would
 * change behaviour, so this signature takes them by axis and leaves that knot
 * for its own change (noted on #338).
 */
export const gridDimensions = (width, height, cardWidth, cardHeight,
                               extraWidth, extraHeight) => ({
  maxColumns: Math.max(1, Math.min(Math.floor((width - extraWidth) / cardWidth), MAX_COLUMNS)),
  maxRows: Math.max(1, Math.min(Math.floor((height - extraHeight) / cardHeight), MAX_ROWS)),
});

/**
 * The largest grid that fits BOTH the viewport and the number of cards to show.
 *
 * Returns `null` when `wordCount` is 0 — that case is real and transient (it is
 * what portrait and desktop hit for one render before words load), and it must
 * stay distinguishable from the geometric failure above rather than being
 * papered over with a 1x1 grid for a set that has nothing to render.
 */
export const selectLayout = (maxColumns, maxRows, wordCount) => {
  const options = [];
  for (let columns = 1; columns <= maxColumns; columns += 1) {
    for (let rows = 1; rows <= maxRows; rows += 1) {
      options.push({ className: `layout${columns}c${rows}r`, columns, rows,
                     capacity: columns * rows });
    }
  }
  options.sort((a, b) => a.capacity - b.capacity);
  return options.filter((o) => o.capacity <= wordCount).pop() || null;
};
