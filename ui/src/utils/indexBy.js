// issue-266: extracted from useWordsetLoader so the semantic below is TESTABLE.
//
// It was written inline as part of replacing an O(n*m) `.find()`-inside-`.map()`
// join, and the whole claim of that change is that it alters nothing observable.
// A claim like that needs a pin, and an inline `new Map(...)` had none — the hook
// itself is not covered by any test that reaches this path, so the suite was green
// before and after and said nothing either way.

/**
 * Index rows by a key, keeping the FIRST row for a duplicate key.
 *
 * First-wins is the point, not an implementation detail. The natural one-liner
 * `new Map(rows.map(r => [r[key], r]))` keeps the LAST row, whereas the
 * `Array.prototype.find` this replaces returned the FIRST — so on a duplicate
 * key the tidy version is a silent behaviour change wearing the costume of a
 * pure optimisation.
 */
export const indexByFirst = (rows, key) => {
  const out = new Map();
  for (const row of rows || []) {
    const k = row?.[key];
    if (!out.has(k)) out.set(k, row);
  }
  return out;
};
