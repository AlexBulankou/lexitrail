// lexitrail#192 — the ~450 example sentences that shipped in prod and were never rendered.
import fs from 'fs';
import path from 'path';
import {
  indexByWord, sentencesFor, loadSentences, _resetSentencesCache, SENTENCES_URL,
} from './sentences';

const CORPUS = path.resolve(__dirname, '..', '..', 'public', 'sentences', 'sentences.json');
const real = () => JSON.parse(fs.readFileSync(CORPUS, 'utf8'));

beforeEach(() => _resetSentencesCache());

describe('indexing the real corpus, not a fixture', () => {
  const idx = indexByWord(real());

  test('the words #192 names by hand are present with usable examples', () => {
    for (const w of ['您', '它', '大家']) {
      expect(sentencesFor(idx, w).length).toBeGreaterThan(0);
      const [first] = sentencesFor(idx, w);
      expect(first.zh).toContain(w);
      expect(first.py).not.toBe('');
      expect(first.en).not.toBe('');
    }
  });

  test('the corpus is the size the issue claims — a sanity check on the file itself', () => {
    // If sentences.json is ever truncated or re-keyed, this moves. A silently short corpus
    // renders as "most words have no examples", which reads like a design choice.
    expect(real().sentences.length).toBeGreaterThan(400);
    expect(Object.keys(idx).length).toBeGreaterThan(150);
  });

  test('an unknown word yields an EMPTY ARRAY, never null', () => {
    // The caller's "render nothing, not an empty box" rests on one `.length` check. A nullable
    // return needs two, and the second is the one that gets forgotten.
    expect(sentencesFor(idx, '🚫notaword')).toEqual([]);
    expect(sentencesFor(idx, undefined)).toEqual([]);
    expect(sentencesFor(null, '您')).toEqual([]);
  });

  test('the limit is respected and corpus order is preserved', () => {
    const all = sentencesFor(idx, '您', 99);
    expect(sentencesFor(idx, '您', 1)).toEqual(all.slice(0, 1));
    expect(sentencesFor(idx, '您', 2)).toEqual(all.slice(0, 2));
  });

  test('rows without a word or hanzi are dropped', () => {
    const i = indexByWord({ sentences: [
      { w: '', zh: 'x' }, { w: 'a' }, { w: 'b', zh: 'B', py: 'p', en: 'e' }] });
    expect(Object.keys(i)).toEqual(['b']);
  });
});

describe('the loader fetches ONCE', () => {
  const payload = { sentences: [{ w: '您', zh: 'z', py: 'p', en: 'e' }] };
  const fakeFetch = (calls) => (url) => {
    calls.push(url);
    return Promise.resolve({ json: () => Promise.resolve(payload) });
  };

  test('🔴 concurrent callers share ONE request — memoised on the PROMISE', async () => {
    // BUG SHAPE: memoising the RESULT lets N cards mounting in the same tick each start their own
    // request before any resolves. That is SUG-2's measured bug (37 hint requests in one short
    // session) one layer over, and it only appears under concurrency — a sequential test passes
    // against the broken version.
    const calls = [];
    const [a, b, c] = await Promise.all([
      loadSentences(fakeFetch(calls)),
      loadSentences(fakeFetch(calls)),
      loadSentences(fakeFetch(calls)),
    ]);
    expect(calls).toHaveLength(1);
    expect(calls[0]).toBe(SENTENCES_URL);
    expect(a).toBe(b);
    expect(b).toBe(c);
  });

  test('CONTROL: after a reset it fetches again — the cache is real, not a dead code path', () => {
    // Without this, "fetched once" is equally satisfied by a loader that never fetches at all.
    const calls = [];
    return loadSentences(fakeFetch(calls))
      .then(() => { _resetSentencesCache(); return loadSentences(fakeFetch(calls)); })
      .then(() => expect(calls).toHaveLength(2));
  });

  test('a failed or malformed fetch renders NOTHING rather than breaking the card', async () => {
    const boom = () => Promise.reject(new Error('404'));
    await expect(loadSentences(boom)).resolves.toEqual({});
    _resetSentencesCache();
    const garbage = () => Promise.resolve({ json: () => Promise.resolve('not an object') });
    await expect(loadSentences(garbage)).resolves.toEqual({});
  });
});
