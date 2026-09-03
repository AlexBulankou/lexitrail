import { gridDimensions, selectLayout } from './cardLayout';

// The real constants from `Game.updateLayout`, so these assertions are about
// the LIVE geometry and not a convenient fiction. cardHeight is the PRACTICE
// value (TEST uses 345, which is strictly worse and so cannot un-break this).
const CARD_W = 160;
const CARD_H = 280;
const EXTRA_W = 100; // Game.js: extraVerticalSpaceNeeded, applied to WIDTH
const EXTRA_H = 200; // Game.js: extraHorizontalSpaceNeeded, applied to HEIGHT

const dims = (w, h) => gridDimensions(w, h, CARD_W, CARD_H, EXTRA_W, EXTRA_H);

describe('gridDimensions (issue-338)', () => {
  // BUG SHAPE. This is the whole defect: the unfloored expression is
  // floor((390 - 200) / 280) = 0, which made the option loop unreachable.
  test('phone LANDSCAPE 844x390 yields at least one row — the raw formula gives 0', () => {
    expect(Math.floor((390 - EXTRA_H) / CARD_H)).toBe(0); // what it used to be
    expect(dims(844, 390).maxRows).toBeGreaterThanOrEqual(1); // what it must be
  });

  test('a viewport too small on BOTH axes still yields a 1x1 grid, never 0', () => {
    // A zero on either axis empties the option list, and an empty list is what
    // let the initial `useState` value stand in for a failed computation.
    expect(dims(10, 10)).toEqual({ maxColumns: 1, maxRows: 1 });
    expect(dims(0, 0)).toEqual({ maxColumns: 1, maxRows: 1 });
  });

  // AC3 — asserted, not assumed: the floor touches the shared path, so the two
  // working viewports have to be pinned or a regression here is silent.
  test('portrait 390x844 and desktop 1440x900 are UNCHANGED by the floor', () => {
    expect(dims(390, 844)).toEqual({ maxColumns: 1, maxRows: 2 });
    expect(dims(1440, 900)).toEqual({ maxColumns: 8, maxRows: 2 });
  });

  test('the 20-column / 7-row ceilings still bind on an absurd viewport', () => {
    // BUG SHAPE for the other direction: a `Math.max` applied without keeping
    // the `Math.min` would let a huge window generate thousands of options.
    expect(dims(100000, 100000)).toEqual({ maxColumns: 20, maxRows: 7 });
  });
});

describe('selectLayout (issue-338)', () => {
  test('landscape 4x1 with enough words picks 4c1r — four cards, not one', () => {
    const { maxColumns, maxRows } = dims(844, 390);
    expect(selectLayout(maxColumns, maxRows, 20).className).toBe('layout4c1r');
  });

  test('never returns null when the grid is at least 1x1 and there is a word', () => {
    // The property that makes the initial-state fallback unreachable. A null
    // here is exactly what left `layoutClass` at `layout1c1r`.
    for (const [w, h] of [[844, 390], [390, 844], [1440, 900], [10, 10]]) {
      const { maxColumns, maxRows } = dims(w, h);
      expect(selectLayout(maxColumns, maxRows, 1)).not.toBeNull();
    }
  });

  test('returns null for ZERO words — the transient pre-load case stays distinct', () => {
    // Portrait and desktop hit this for one render before words arrive, and
    // recover. It must not be conflated with the geometric failure: handing
    // back a 1x1 grid for an empty set would hide a real "no words" state.
    expect(selectLayout(8, 2, 0)).toBeNull();
  });

  test('never exceeds the word count, and takes the LARGEST that fits', () => {
    expect(selectLayout(8, 2, 16).className).toBe('layout8c2r'); // capacity 16
    expect(selectLayout(8, 2, 15).capacity).toBeLessThanOrEqual(15);
    expect(selectLayout(1, 2, 5).className).toBe('layout1c2r');  // bounded by grid
  });
});
