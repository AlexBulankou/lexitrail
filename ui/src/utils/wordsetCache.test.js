import { rawKey, viewKey, userwordsKey, invalidateWordset } from './wordsetCache';

// Mirrors GameMode without importing it — components/Game pulls in React and
// the router, and these are pure-key assertions.
const PRACTICE = 'PRACTICE';
const TEST = 'TEST';
const DUE_TODAY = 'DUE_TODAY';
const SHOW_EXCLUDED = 'SHOW_EXCLUDED';

describe('wordset cache keys (lexitrail#93, #91)', () => {
  // BUG SHAPE (#93 AC2) — the live collision. The old key was built from
  // `includedFlag`, which is 1 for BOTH of these, so they shared a slot and
  // TEST rendered PRACTICE's 150-word list with its filter and 20-cap skipped.
  test('PRACTICE and TEST do not share a view slot', () => {
    expect(viewKey('u1', '1', PRACTICE)).not.toBe(viewKey('u1', '1', TEST));
  });

  test('every mode gets its own view slot', () => {
    const keys = new Set([PRACTICE, TEST, DUE_TODAY, SHOW_EXCLUDED]
      .map((m) => viewKey('u1', '1', m)));
    expect(keys.size).toBe(4);
  });

  // #91: the raw payload is mode-independent, because neither fetch takes mode.
  test('the raw key is the same across modes and distinct per wordset/user', () => {
    expect(rawKey('u1', '1')).toBe(rawKey('u1', '1'));
    expect(rawKey('u1', '1')).not.toBe(rawKey('u1', '2'));
    expect(rawKey('u1', '1')).not.toBe(rawKey('u2', '1'));
  });

  test('a raw key never collides with a view key', () => {
    expect(rawKey('u1', '1')).not.toBe(viewKey('u1', '1', PRACTICE));
  });

  describe('invalidateWordset', () => {
    const populate = () => ({
      [rawKey('u1', '1')]: ['raw1'],
      [viewKey('u1', '1', PRACTICE)]: ['p'],
      [viewKey('u1', '1', TEST)]: ['t'],
      [viewKey('u1', '1', DUE_TODAY)]: ['d'],
      [viewKey('u1', '1', SHOW_EXCLUDED)]: ['s'],
      [rawKey('u1', '2')]: ['raw2'],
      [viewKey('u1', '2', PRACTICE)]: ['other'],
    });

    // #93 AC3 — the old version deleted three literal keys, so any mode
    // without a hand-written entry was never invalidated. That is exactly how
    // TEST went missing.
    test('clears the raw entry and EVERY derived view for the wordset', () => {
      const cache = populate();
      invalidateWordset(cache, 'u1', '1');
      expect(Object.keys(cache).sort())
        .toEqual([rawKey('u1', '2'), viewKey('u1', '2', PRACTICE)].sort());
    });

    test('leaves other wordsets and other users untouched', () => {
      const cache = populate();
      invalidateWordset(cache, 'u1', '1');
      expect(cache[rawKey('u1', '2')]).toEqual(['raw2']);
      expect(cache[viewKey('u1', '2', PRACTICE)]).toEqual(['other']);
    });

    // BUG SHAPE — prefix matching without a trailing delimiter would make
    // wordset 1 also invalidate 10, 11, 100...
    test('wordset 1 does not invalidate wordset 10', () => {
      const cache = {
        [viewKey('u1', '1', PRACTICE)]: ['one'],
        [viewKey('u1', '10', PRACTICE)]: ['ten'],
        [rawKey('u1', '10')]: ['ten-raw'],
      };
      invalidateWordset(cache, 'u1', '1');
      expect(cache[viewKey('u1', '10', PRACTICE)]).toEqual(['ten']);
      expect(cache[rawKey('u1', '10')]).toEqual(['ten-raw']);
      expect(cache[viewKey('u1', '1', PRACTICE)]).toBeUndefined();
    });

    test('returns the keys it removed, and is a no-op on an empty cache', () => {
      const cache = populate();
      const removed = invalidateWordset(cache, 'u1', '1');
      expect(removed.sort()).toEqual([
        rawKey('u1', '1'),
        viewKey('u1', '1', DUE_TODAY),
        viewKey('u1', '1', PRACTICE),
        viewKey('u1', '1', SHOW_EXCLUDED),
        viewKey('u1', '1', TEST),
      ].sort());
      expect(invalidateWordset({}, 'u1', '1')).toEqual([]);
    });
  });

  // issue-335 — the published `/userwords/query` rows Today writes and the
  // practice loader reads.
  describe('userwordsKey (issue-335)', () => {
    test('is a DIFFERENT slot from rawKey — they hold different shapes', () => {
      // BUG SHAPE. Sharing `rawKey` would let Today's raw userword rows be read
      // back by `loadWordsForWordset` as an already-MAPPED word list, which
      // renders nothing. Distinctness is the property, not the spelling.
      expect(userwordsKey('u1', '1')).not.toEqual(rawKey('u1', '1'));
      expect(userwordsKey('u1', '1')).not.toEqual(viewKey('u1', '1', PRACTICE));
    });

    test('separates users and wordsets', () => {
      expect(userwordsKey('u1', '1')).not.toEqual(userwordsKey('u2', '1'));
      expect(userwordsKey('u1', '1')).not.toEqual(userwordsKey('u1', '2'));
    });

    test('invalidateWordset SWEEPS it — a recall write must not leave it behind', () => {
      // BUG SHAPE (the one that matters): this slot is the UPSTREAM of `raw`.
      // Left behind, the next loader rebuilds `raw` from pre-write rows and
      // silently undoes the invalidation — the write appears to land and the
      // next session shows the old recall state.
      const cache = {
        [userwordsKey('u1', '1')]: ['stale-rows'],
        [rawKey('u1', '1')]: ['mapped'],
      };
      const removed = invalidateWordset(cache, 'u1', '1');
      expect(cache[userwordsKey('u1', '1')]).toBeUndefined();
      expect(removed).toContain(userwordsKey('u1', '1'));
    });

    test('sweeping wordset 1 leaves wordset 10 and other users intact', () => {
      const cache = {
        [userwordsKey('u1', '1')]: ['one'],
        [userwordsKey('u1', '10')]: ['ten'],
        [userwordsKey('u2', '1')]: ['other-user'],
      };
      invalidateWordset(cache, 'u1', '1');
      expect(cache[userwordsKey('u1', '10')]).toEqual(['ten']);
      expect(cache[userwordsKey('u2', '1')]).toEqual(['other-user']);
      expect(cache[userwordsKey('u1', '1')]).toBeUndefined();
    });
  });
});