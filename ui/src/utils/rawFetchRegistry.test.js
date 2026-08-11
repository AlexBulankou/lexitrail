import { makeRawRegistry, claimRawFetch } from './rawFetchRegistry';
import { rawKey } from './wordsetCache';

// A deferred promise, so a test can hold a "fetch" open and start a second
// caller while the first is genuinely still in flight. Using a real pending
// promise rather than a timer keeps these deterministic.
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
};

describe('raw-fetch in-flight registry (lexitrail#95)', () => {
  // AC1 + AC2 — THE BUG SHAPE. PRACTICE and TEST are different `inFlight`
  // keys, so both pass that guard and both reach the raw fetch with the cache
  // still empty. Keyed on rawKey (mode-independent), the second must JOIN the
  // first rather than start its own.
  test('two concurrent different-mode loads issue ONE raw fetch, not two', async () => {
    const reg = makeRawRegistry();
    const key = rawKey('u1', 'w1');
    const d = deferred();
    let calls = 0;
    const fetcher = () => { calls += 1; return d.promise; };

    // PRACTICE arrives, then TEST while the first is still pending.
    const practice = claimRawFetch(reg, key, fetcher);
    // The CLAIM is synchronous even though the fetcher runs on a microtask —
    // that ordering is what closes the race. Asserting `calls === 1` here
    // instead would be pinning the wrong property: it fails on a correct
    // implementation (the fetcher has not been invoked yet) and would pass on
    // a broken one that claimed the key late.
    expect(reg.size).toBe(1);
    const test_ = claimRawFetch(reg, key, fetcher);
    expect(reg.size).toBe(1);

    await Promise.resolve();          // let the deferred fetcher run
    expect(calls).toBe(1);
    d.resolve(['payload']);
    // Both callers get the SAME result — the second joined, it did not skip.
    await expect(practice).resolves.toEqual(['payload']);
    await expect(test_).resolves.toEqual(['payload']);
    expect(calls).toBe(1);
  });

  // AC3 (first half) — a genuinely different wordset must never be blocked.
  // This is the property inFlight.js exists to protect, one layer down: a
  // registry that over-shares would strand the second wordset's load.
  test('a different wordset is never blocked by one in flight', async () => {
    const reg = makeRawRegistry();
    const d1 = deferred();
    let w1calls = 0, w2calls = 0;

    const p1 = claimRawFetch(reg, rawKey('u1', 'w1'), () => { w1calls += 1; return d1.promise; });
    const p2 = claimRawFetch(reg, rawKey('u1', 'w2'), async () => { w2calls += 1; return ['w2']; });

    await expect(p2).resolves.toEqual(['w2']);   // resolves while w1 hangs
    expect([w1calls, w2calls]).toEqual([1, 1]);
    d1.resolve(['w1']);
    await expect(p1).resolves.toEqual(['w1']);
  });

  // AC3 (second half) — THE #90 HANG SHAPE, one layer down. A key left
  // claimed after a rejected load would make every later caller await a
  // promise that has already rejected and can never be retried.
  test('a REJECTED load releases the key, and a retry runs a fresh fetch', async () => {
    const reg = makeRawRegistry();
    const key = rawKey('u1', 'w1');
    let calls = 0;

    const first = claimRawFetch(reg, key, async () => {
      calls += 1;
      throw new Error('network down');
    });
    await expect(first).rejects.toThrow('network down');

    // The registry must be empty — not "eventually", by the time the promise
    // the caller awaited has settled.
    expect(reg.size).toBe(0);

    const second = claimRawFetch(reg, key, async () => { calls += 1; return ['ok']; });
    await expect(second).resolves.toEqual(['ok']);
    expect(calls).toBe(2);
  });

  // A fetcher that throws SYNCHRONOUSLY (before returning a promise) must not
  // escape past the release. A bare `fetcher()` call would let this one throw
  // out of claimRawFetch entirely, leaving the key claimed forever.
  test('a SYNCHRONOUSLY throwing fetcher still releases the key', async () => {
    const reg = makeRawRegistry();
    const key = rawKey('u1', 'w1');

    const p = claimRawFetch(reg, key, () => { throw new Error('sync boom'); });
    await expect(p).rejects.toThrow('sync boom');
    expect(reg.size).toBe(0);
  });

  test('the key is released after a SUCCESSFUL load too', async () => {
    const reg = makeRawRegistry();
    const key = rawKey('u1', 'w1');
    await claimRawFetch(reg, key, async () => ['ok']);
    expect(reg.size).toBe(0);
  });

  // A caller arriving AFTER the first settled starts a fresh fetch rather
  // than joining a stale promise — the registry de-duplicates concurrency, it
  // is not a second cache. (The raw cache above it is what prevents the
  // refetch in practice.)
  test('a caller arriving after settlement is not handed the old promise', async () => {
    const reg = makeRawRegistry();
    const key = rawKey('u1', 'w1');
    let calls = 0;
    const fetcher = async () => { calls += 1; return ['v', calls]; };

    await claimRawFetch(reg, key, fetcher);
    await claimRawFetch(reg, key, fetcher);
    expect(calls).toBe(2);
  });
});
