import { gridDimensions, selectLayout } from './cardLayout';

// The real constants from `Game.updateLayout`, so these assertions are about
// the LIVE geometry and not a convenient fiction. cardHeight is the PRACTICE
// value (TEST uses 345, which is strictly worse and so cannot un-break this).
const CARD_W = 160;
const CARD_H = 280;
const GRID_GAP = 10;     // .cards-container { gap: 10px }
const PAGE_MARGIN = 12;  // game .container: 10px padding + 2px border, each side
const EXTRA_H = 200;     // Game.js: extraHorizontalSpaceNeeded, applied to HEIGHT

// The WIDTH path mirrors the fixed `Game.updateLayout` call: N columns fit when
// N*CARD_W + (N-1)*GRID_GAP <= w - 2*PAGE_MARGIN, expressed to `gridDimensions`
// as a per-column footprint of CARD_W+GRID_GAP against an allowance of
// 2*PAGE_MARGIN-GRID_GAP. (The old flat allowance of 100 gave floor((390-100)/160)
// = 1 column on a phone where 2 fit — see the practice-mobile-columns suite.)
const dims = (w, h) => gridDimensions(
  w, h, CARD_W + GRID_GAP, CARD_H, 2 * PAGE_MARGIN - GRID_GAP, EXTRA_H);

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

  // AC3 — asserted, not assumed: the floor touches the shared path, so the
  // working viewports have to be pinned or a regression here is silent.
  // (Portrait moved from the 1 column pinned here under the old 100px
  // allowance to its correct 2 — see the practice-mobile-columns suite.)
  test('portrait 390x844 and desktop 1440x900 are pinned', () => {
    expect(dims(390, 844)).toEqual({ maxColumns: 2, maxRows: 2 });
    expect(dims(1440, 900)).toEqual({ maxColumns: 8, maxRows: 2 });
  });

  test('the 20-column / 7-row ceilings still bind on an absurd viewport', () => {
    // BUG SHAPE for the other direction: a `Math.max` applied without keeping
    // the `Math.min` would let a huge window generate thousands of options.
    expect(dims(100000, 100000)).toEqual({ maxColumns: 20, maxRows: 7 });
  });
});

// uibug 2026-09-16 (practice-mobile-columns): on live mobile 390x844 /game/1
// PRACTICE, `.cards-container` was layout1c2r at {x:115, w:160} — 115px dead
// margin each side, 'cards 1–2 of 10' (5 pages) — because the width allowance
// was a flat 100 while the real chrome is 12px each side plus a 10px
// inter-column gap. These pin the corrected width path.
describe('gridDimensions width path (practice-mobile-columns)', () => {
  test('phone-class widths get 2 columns — 2*160+10+24 = 354 fits them all', () => {
    for (const w of [360, 390, 414, 428]) {
      expect(dims(w, 844).maxColumns).toBe(2);
    }
  });

  test('portrait 390x844 selects layout2c2r: 4 cards per page of 10, not 2', () => {
    const { maxColumns, maxRows } = dims(390, 844);
    const layout = selectLayout(maxColumns, maxRows, 10);
    expect(layout.className).toBe('layout2c2r');
    expect(layout.capacity).toBe(4);
  });

  test('desktop 1440x900 still offers the full 8x2 grid', () => {
    const { maxColumns, maxRows } = dims(1440, 900);
    expect({ maxColumns, maxRows }).toEqual({ maxColumns: 8, maxRows: 2 });
    // With enough words the selection is the same layout8c2r as before the fix
    // (capacity is word-count-capped, so 16+ words are needed to exercise it).
    expect(selectLayout(maxColumns, maxRows, 20).className).toBe('layout8c2r');
  });

  // Why the fix is footprint+gap and not another flat constant: 8 columns
  // really need 8*160+7*10+24 = 1374px, so a 1366px laptop must get 7. A flat
  // allowance would need a > 86 here but a <= 70 for 2 columns at 390 — no
  // single flat value satisfies both.
  test('1366px laptop gets 7 columns, not an overflowing 8', () => {
    expect(dims(1366, 768).maxColumns).toBe(7);
  });

  test('columns never overflow the usable width across common widths', () => {
    for (const w of [320, 360, 390, 414, 768, 820, 1024, 1280, 1366, 1440, 1920]) {
      const { maxColumns } = dims(w, 900);
      const needed = maxColumns * CARD_W + (maxColumns - 1) * GRID_GAP;
      expect(needed).toBeLessThanOrEqual(Math.max(w - 2 * PAGE_MARGIN, CARD_W));
    }
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
