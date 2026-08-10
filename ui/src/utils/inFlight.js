// lexitrail#52 bug 6 — in-flight request de-duplication for the wordset loader.
//
// WHY THIS IS A MODULE AND NOT A BOOLEAN REF. `useWordsetLoader` carried a
// `isFetchingRef` guard that read `if (isFetchingRef.current) return;` and
// reset the flag in `finally` — but NOTHING IN THE TREE EVER SET IT TO TRUE
// (3 references: one init to `false`, one read, one reset). The early return
// could never be taken, so the de-duplication it documents never once
// happened and every repeated invocation issued a fresh pair of network
// requests.
//
// The obvious repair — set the flag to `true` — introduces a HANG, which is
// why the guard is keyed instead. `loadWordsForWordset` is a `useCallback`
// over `[wordsetId, userId, mode]`, and Game.js re-runs it from an effect
// keyed on the same values. So changing `mode` mid-flight issues a
// DIFFERENT request while an old one is still running: a single boolean
// would early-return that new request, leave `loading` at its previous
// value, and strand the UI — the exact symptom (a stuck loading state) the
// fix is meant to address.
//
// Keying on the request identity keeps both properties: an identical
// concurrent request is suppressed, and a genuinely different one is never
// blocked. The failure direction is deliberate — the worst case is a
// duplicate fetch (which is today's unconditional behaviour), never a stall.

/** Fresh in-flight registry. One per hook instance (held in a ref). */
export const makeInFlight = () => new Set();

/**
 * Identity of a load request. Must contain every value the request's result
 * depends on — these are exactly `useWordsetLoader`'s callback deps. `|` is
 * the separator because none of the three values can contain it.
 */
export const requestKey = (userId, wordsetId, mode) =>
  `${userId}|${wordsetId}|${mode}`;

/**
 * Claim `key`. Returns false when an identical request is already running
 * (caller should return without touching loading state), true when the
 * caller now owns the request and MUST pair this with `endRequest` in a
 * `finally` — an unpaired claim locks that key out until remount.
 */
export const beginRequest = (inFlight, key) => {
  if (inFlight.has(key)) return false;
  inFlight.add(key);
  return true;
};

/** Release `key`. Safe to call for a key that is not held. */
export const endRequest = (inFlight, key) => {
  inFlight.delete(key);
};
