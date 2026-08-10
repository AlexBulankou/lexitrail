import { makeInFlight, requestKey, beginRequest, endRequest } from './inFlight';

describe('inFlight de-duplication (lexitrail#52 bug 6)', () => {
  test('an identical concurrent request is suppressed', () => {
    const f = makeInFlight();
    const k = requestKey('u1', 'w1', 'PRACTICE');
    expect(beginRequest(f, k)).toBe(true);
    expect(beginRequest(f, k)).toBe(false);
  });

  // BUG SHAPE — this is the regression the naive repair would have shipped.
  // `isFetchingRef` was a single boolean, so setting it to `true` would have
  // early-returned a mode change issued while a load was still running,
  // leaving `loading` stuck at its previous value. A different request must
  // NEVER be blocked, whichever field differs.
  test('a DIFFERENT request is never blocked by one in flight', () => {
    const f = makeInFlight();
    expect(beginRequest(f, requestKey('u1', 'w1', 'PRACTICE'))).toBe(true);

    // mode changed mid-flight — the Game.js effect re-runs and must proceed
    expect(beginRequest(f, requestKey('u1', 'w1', 'DUE_TODAY'))).toBe(true);
    // ...and so must a different wordset or a different user
    expect(beginRequest(f, requestKey('u1', 'w2', 'PRACTICE'))).toBe(true);
    expect(beginRequest(f, requestKey('u2', 'w1', 'PRACTICE'))).toBe(true);
  });

  // Pins against the other way this hangs: a key that is claimed and never
  // released locks that request out for the life of the component.
  test('a released key can be claimed again', () => {
    const f = makeInFlight();
    const k = requestKey('u1', 'w1', 'PRACTICE');
    expect(beginRequest(f, k)).toBe(true);
    endRequest(f, k);
    expect(beginRequest(f, k)).toBe(true);
  });

  test('releasing one key leaves other in-flight keys held', () => {
    const f = makeInFlight();
    const a = requestKey('u1', 'w1', 'PRACTICE');
    const b = requestKey('u1', 'w1', 'DUE_TODAY');
    beginRequest(f, a);
    beginRequest(f, b);
    endRequest(f, a);
    expect(beginRequest(f, a)).toBe(true); // released
    expect(beginRequest(f, b)).toBe(false); // still running
  });

  test('endRequest on an unheld key is a no-op, not a throw', () => {
    const f = makeInFlight();
    expect(() => endRequest(f, requestKey('u1', 'w1', 'PRACTICE'))).not.toThrow();
  });

  test('requestKey distinguishes every field it is keyed on', () => {
    const keys = new Set([
      requestKey('u1', 'w1', 'PRACTICE'),
      requestKey('u2', 'w1', 'PRACTICE'),
      requestKey('u1', 'w2', 'PRACTICE'),
      requestKey('u1', 'w1', 'DUE_TODAY'),
    ]);
    expect(keys.size).toBe(4);
  });

  // Each hook instance owns its registry; one component's in-flight load must
  // not suppress another's.
  test('makeInFlight returns an independent registry each call', () => {
    const a = makeInFlight();
    const b = makeInFlight();
    const k = requestKey('u1', 'w1', 'PRACTICE');
    beginRequest(a, k);
    expect(beginRequest(b, k)).toBe(true);
  });
});
