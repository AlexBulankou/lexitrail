// Cache keys for the wordset loader — lexitrail#93 (correctness) and #91
// (efficiency). Both come from one root, which is why they are fixed together.
//
// THE OLD KEY WAS DERIVED FROM `includedFlag`, NOT FROM `mode`:
//
//     includedFlag = mode == SHOW_EXCLUDED ? 0 : 1
//     cacheKey     = `${userId}-${wordsetId}-${includedFlag}${DUE_TODAY ? '-due' : ''}`
//
//   PRACTICE       -> ...-1
//   TEST           -> ...-1     <- SAME SLOT, different derivation
//   DUE_TODAY      -> ...-1-due
//   SHOW_EXCLUDED  -> ...-0
//
// DUE_TODAY had been given its own slot explicitly; TEST had not. The cached
// value is the POST-filter, POST-slice list, and TEST's derivation differs
// materially — it strips `[quiz_word]` options and special characters and caps
// at 20. Measured on prod: clicking Practice then Test in one session left the
// shared slot holding 150 entries, so Test rendered the practice list with its
// own filter and cap silently skipped (#93).
//
// TWO CACHES, because the two things have different lifetimes:
//
//   raw   per (userId, wordsetId)         — what the network returned. Mode
//                                           does not appear because neither
//                                           fetch takes it (#91): a mode switch
//                                           was refetching identical bytes.
//   view  per (userId, wordsetId, mode)   — the derived, filtered, sorted list.
//
// Keys are JSON-ish delimited with `|` and always carry a TRAILING delimiter
// when used as a prefix — `view|u|1|` must not match `view|u|10|PRACTICE`.

const RAW = 'raw';
const VIEW = 'view';

/** Key for the raw fetch result — deliberately mode-independent (#91). */
export const rawKey = (userId, wordsetId) => `${RAW}|${userId}|${wordsetId}`;

/** Key for one mode's derived list. Keyed on MODE, never on includedFlag (#93). */
export const viewKey = (userId, wordsetId, mode) =>
  `${VIEW}|${userId}|${wordsetId}|${mode}`;

/**
 * Drop every entry belonging to one (user, wordset): the raw payload and ALL
 * derived views.
 *
 * Enumerating slots by hand is what let TEST go missing in the first place —
 * the old `invalidateCache` deleted three literal keys, so any mode without a
 * hand-written entry was silently never invalidated. This sweeps by prefix
 * instead, so a mode added later is covered without touching this function.
 *
 * Mutates `cache` in place (it is a window-scoped object shared across hook
 * instances) and returns the keys it removed, so callers and tests can assert
 * on what happened rather than inferring it.
 */
export const invalidateWordset = (cache, userId, wordsetId) => {
  const raw = rawKey(userId, wordsetId);
  // Trailing delimiter is load-bearing: without it, wordset 1 would also
  // invalidate wordset 10, 11, 100...
  const viewPrefix = `${VIEW}|${userId}|${wordsetId}|`;
  const removed = Object.keys(cache).filter(
    (k) => k === raw || k.startsWith(viewPrefix));
  removed.forEach((k) => { delete cache[k]; });
  return removed;
};
