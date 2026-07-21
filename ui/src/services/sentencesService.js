// FEAT-9 (ITP #21): example sentences. Surfaces the existing curated sentence
// bank (public/sentences/sentences.json) so learners see each word used in
// context. Zero new backend — a static asset, lazy-loaded + cached client-side.
//
// Record shape (compacted at build time): { w, zh, py, en }
//   w = the vocab word (chinese) the sentence exemplifies
//   zh = example sentence (chinese) · py = pinyin · en = english

const SENTENCES_URL = '/sentences/sentences.json';

// Build a { word(chinese) -> [record...] } index. Pure — unit-tested.
export function buildIndex(sentences) {
  const index = {};
  for (const s of sentences || []) {
    const w = s && s.w;
    if (!w) continue;
    (index[w] = index[w] || []).push(s);
  }
  return index;
}

// Up to `limit` examples for `chinese` from a prebuilt index. Pure — unit-tested.
export function selectExamples(index, chinese, limit = 2) {
  const key = (chinese || '').trim();
  if (!key || !index) return [];
  return (index[key] || []).slice(0, limit);
}

// Lazy singleton: fetch + index once, reuse the in-flight promise so concurrent
// cards don't each fetch. A failed fetch resolves to an empty index (feature
// simply hides) and is retried on the next call.
let _indexPromise = null;

function loadIndex() {
  if (_indexPromise) return _indexPromise;
  _indexPromise = fetch(SENTENCES_URL)
    .then((r) => (r.ok ? r.json() : { sentences: [] }))
    .then((data) => buildIndex(data.sentences))
    .catch(() => {
      _indexPromise = null; // allow retry
      return {};
    });
  return _indexPromise;
}

// Async convenience used by the UI: example sentences for a word.
export async function getExamples(chinese, limit = 2) {
  const index = await loadIndex();
  return selectExamples(index, chinese, limit);
}

// Test-only: reset the memoized index between cases.
export function _resetCache() {
  _indexPromise = null;
}
