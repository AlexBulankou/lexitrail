import { indexByFirst } from './indexBy';

// The reference implementation this REPLACED. Every equivalence test below is
// stated against it rather than against my expectation of it, so the tests
// verify a migration rather than restate a design.
const findRef = (rows, key, k) => rows.find((r) => r[key] === k);

describe('indexByFirst (issue-266)', () => {
  const rows = [
    { word_id: 3, tag: 'c' },
    { word_id: 1, tag: 'a' },
    { word_id: 2, tag: 'b' },
  ];

  it('agrees with .find() for every present key, regardless of order', () => {
    const idx = indexByFirst(rows, 'word_id');
    for (const k of [1, 2, 3]) {
      expect(idx.get(k)).toBe(findRef(rows, 'word_id', k));
    }
  });

  it('returns undefined for an absent key, as .find() did', () => {
    const idx = indexByFirst(rows, 'word_id');
    expect(idx.get(99)).toBeUndefined();
    expect(findRef(rows, 'word_id', 99)).toBeUndefined();
  });

  // THE load-bearing case. `new Map(rows.map(...))` keeps the LAST row and would
  // pass every other test in this file.
  it('keeps the FIRST row on a duplicate key — where the naive Map differs', () => {
    const dupes = [
      { word_id: 1, tag: 'FIRST' },
      { word_id: 1, tag: 'LAST' },
    ];
    expect(indexByFirst(dupes, 'word_id').get(1).tag).toBe('FIRST');
    expect(findRef(dupes, 'word_id', 1).tag).toBe('FIRST');

    // negative control: prove the naive form really does disagree, so this test
    // is pinning a live difference and not an imagined one.
    const naive = new Map(dupes.map((r) => [r.word_id, r]));
    expect(naive.get(1).tag).toBe('LAST');
  });

  it('is identity-preserving — returns the row object, not a copy', () => {
    const idx = indexByFirst(rows, 'word_id');
    expect(idx.get(1)).toBe(rows[1]);
  });

  it('tolerates empty and nullish input', () => {
    expect(indexByFirst([], 'word_id').size).toBe(0);
    expect(indexByFirst(undefined, 'word_id').size).toBe(0);
    expect(indexByFirst(null, 'word_id').size).toBe(0);
  });

  it('handles a row missing the key without throwing', () => {
    const idx = indexByFirst([{ tag: 'x' }, { word_id: 1, tag: 'y' }], 'word_id');
    expect(idx.get(1).tag).toBe('y');
    expect(idx.get(undefined).tag).toBe('x');
  });
});
