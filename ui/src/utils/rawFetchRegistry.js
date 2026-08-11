// lexitrail#95 — in-flight de-duplication for the RAW fetch.
//
// WHY A SECOND REGISTRY. The existing guard and the raw cache are keyed
// differently, and the gap between them is the bug:
//
//     in-flight guard   (userId, wordsetId, mode)     utils/inFlight.js
//     raw payload cache (userId, wordsetId)           utils/wordsetCache.js
//
// So PRACTICE and TEST on the same wordset are two DIFFERENT in-flight keys —
// both pass `beginRequest` — and before either resolves both find the raw
// entry absent, so both issue the raw fetch pair. `inFlight.js` cannot close
// this by widening its key: dropping `mode` there would early-return a
// genuinely different request and strand the loading state, which is the hang
// that module exists to prevent. The two guards want different keys because
// they guard different things, so the raw fetch needs its own.
//
// WHY A MAP OF PROMISES, not a Set. A Set answers "is someone fetching?" —
// enough to skip, not enough to WAIT. The second caller needs the first
// caller's result, so the registry has to hand back something awaitable. That
// is the promise-in-the-cache shape, and it is why this was deferred out of
// #94 rather than folded in as a one-liner.
//
// SCOPE MUST MATCH THE CACHE IT GUARDS. The raw cache is window-scoped
// (shared across hook instances), so this registry is too. A per-instance
// registry would be a narrower guard than the thing it protects — it would
// de-duplicate a mode switch within one component and still double-fetch
// across two mounted instances that share the cache slot.

/** Fresh raw-fetch registry: key -> in-flight promise. */
export const makeRawRegistry = () => new Map();

/**
 * Run `fetcher` for `key`, or join the run already in flight for it.
 *
 * Returns a promise for the fetched value in both cases, so the caller cannot
 * tell whether it started the work or joined it — which is the point.
 *
 * THE KEY IS ALWAYS RELEASED, including when `fetcher` rejects. That is the
 * load-bearing property, not an implementation detail: a key left claimed
 * after a failed load would make every later caller await a promise that has
 * already rejected and can never be retried — the #90 hang shape, reintroduced
 * one layer down. The `.finally` is attached BEFORE the promise is stored, so
 * the stored promise is the released one and there is no window in which a
 * second caller can pick up an unreleased handle.
 *
 * `Promise.resolve().then(fetcher)` rather than calling `fetcher()` directly:
 * it normalises a `fetcher` that throws SYNCHRONOUSLY into a rejected promise,
 * so the key is released on that path too. A raw `fetcher()` that throws
 * before returning would escape past the `.finally` and leave the key claimed
 * forever.
 */
export const claimRawFetch = (registry, key, fetcher) => {
  const existing = registry.get(key);
  if (existing) return existing;
  const p = Promise.resolve()
    .then(fetcher)
    .finally(() => { registry.delete(key); });
  registry.set(key, p);
  return p;
};
