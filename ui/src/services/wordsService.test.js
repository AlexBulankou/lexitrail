// issue-297: `getWordsets` shares one in-flight request across concurrent callers.
//
// Two components call it and neither knows about the other — `Wordsets.js` (the
// picker) and `useDueToday` (the Today home's fan-out) — so one journey issues the
// same GET more than once. Measured on live prod: three per arrival, two of them on
// `/` before any navigation.
//
// 🔴 THE NEGATIVE CONTROLS ARE THE POINT. "Dedupe" is satisfied by a cache that
// never refetches, which would serve a stale list forever and would quietly weaken
// lexitrail#52 bug 6 (the picker refreshes in the background on revisit). So: shared
// WHILE OPEN, and a fully independent request once it settles — including after a
// failure, or one flaky call poisons every later one.
import { getWordsets } from './wordsService';
import { getData } from './apiService';

jest.mock('./apiService', () => ({ getData: jest.fn() }));
jest.mock('../utils/perfMark', () => ({ markOnce: jest.fn(), WORDSETS_REQUESTED_MARK: 'm' }));

const ROWS = [{ wordset_id: 1, description: 'HSK1' }, { wordset_id: 2, description: 'HSK2' }];

/** A promise plus its resolve/reject, so a test can hold a request OPEN. */
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
};

beforeEach(() => { getData.mockReset(); });

describe('getWordsets in-flight dedup', () => {
  test('two CONCURRENT callers share ONE request', async () => {
    const d = deferred();
    getData.mockReturnValueOnce(d.promise);

    const a = getWordsets();
    const b = getWordsets();          // second caller while the first is still open
    d.resolve({ data: [...ROWS] });
    const [ra, rb] = await Promise.all([a, b]);

    expect(getData).toHaveBeenCalledTimes(1);
    expect(ra.data).toEqual(ROWS);
    expect(rb.data).toEqual(ROWS);
  });

  test('each caller gets its OWN array — mutating one must not reach the other', () => {
    // Not a style preference: sharing one array across two component trees turns a
    // future `.sort()` or `.splice()` in either into a silent corruption of the
    // other, in a place nobody would look for it.
    const d = deferred();
    getData.mockReturnValueOnce(d.promise);
    const a = getWordsets();
    const b = getWordsets();
    d.resolve({ data: [...ROWS] });
    return Promise.all([a, b]).then(([ra, rb]) => {
      expect(ra.data).not.toBe(rb.data);
      ra.data.push({ wordset_id: 99, description: 'injected' });
      expect(rb.data).toHaveLength(2);
    });
  });

  // ── negative controls: this must NOT become a cache ───────────────────────
  test('a SEQUENTIAL caller after the first settles makes a NEW request', async () => {
    getData.mockResolvedValueOnce({ data: [...ROWS] })
           .mockResolvedValueOnce({ data: [...ROWS] });
    await getWordsets();
    await getWordsets();
    expect(getData).toHaveBeenCalledTimes(2);   // in-flight only, never a TTL
  });

  test('a FAILED request does not poison later calls', async () => {
    getData.mockRejectedValueOnce(new Error('network'))
           .mockResolvedValueOnce({ data: [...ROWS] });
    await expect(getWordsets()).rejects.toThrow('network');
    const ok = await getWordsets();             // must retry, not replay the failure
    expect(getData).toHaveBeenCalledTimes(2);
    expect(ok.data).toEqual(ROWS);
  });

  test('BOTH concurrent callers see the failure, and neither is left hanging', async () => {
    const d = deferred();
    getData.mockReturnValueOnce(d.promise);
    const a = getWordsets();
    const b = getWordsets();
    d.reject(new Error('boom'));
    await expect(a).rejects.toThrow('boom');
    await expect(b).rejects.toThrow('boom');
    expect(getData).toHaveBeenCalledTimes(1);
  });

  test('the hidden-wordset filter still applies, once, to the shared response', async () => {
    getData.mockResolvedValueOnce({
      data: [...ROWS, { wordset_id: 9, description: 'test' }, { wordset_id: 10, description: 'HSK7\r' }],
    });
    const r = await getWordsets();
    expect(r.data.map(w => w.description)).toEqual(['HSK1', 'HSK2']);
  });
});
