// lexitrail#192 — the ~450 curated example sentences that ship in prod and were never rendered.
//
// `ui/public/sentences/sentences.json` is deployed and served today; nothing in the UI read it.
// #191 removed the landing page's "example sentences and usage notes" claim precisely because it
// was false, and this is what makes it true again.
//
// SHAPE (verified against the real file, not assumed):
//   { "sentences": [ { "w": "您", "zh": "您是我们的老师吗？",
//                      "py": "Nín shì wǒmen de lǎoshī ma?", "en": "Are you our teacher?" }, ... ] }
// 56 KB, ~450 entries, several per word, covering ~224 HSK2/HSK3 words.
//
// PURE + AN INJECTABLE FETCHER, so every claim below is unit-testable without touching globals.

/** `{word: [{zh, py, en}, ...]}`, preserving corpus order within a word.
 *
 * Order is preserved deliberately: `sentencesFor` takes the FIRST n, so a re-ordering render
 * would change which examples a learner sees without any test noticing.
 */
export const indexByWord = (payload) => {
  const out = {};
  for (const s of (payload && payload.sentences) || []) {
    if (!s || !s.w || !s.zh) continue;          // a row without a word or hanzi is not usable
    (out[s.w] = out[s.w] || []).push({ zh: s.zh, py: s.py || '', en: s.en || '' });
  }
  return out;
};

/** Up to `limit` examples for a word. ALWAYS an array — never null.
 *
 * 🔴 Returning [] rather than null/undefined for an unknown word is the contract the caller's
 * "render nothing, not an empty box" acceptance rests on: `arr.length > 0` is one check, whereas
 * a nullable return needs two and the second one gets forgotten.
 */
export const sentencesFor = (index, word, limit = 2) =>
  ((index && index[word]) || []).slice(0, limit);

// ── the lazy, fetch-once loader ───────────────────────────────────────────────────────────────
//
// 🔴 MEMOISED ON THE PROMISE, NOT ON THE RESULT. Caching the resolved value still lets N cards
// mounting in the same tick each start their own request before any of them resolves -- which is
// SUG-2's exact bug one layer over (37 hint requests in one short session). Storing the in-flight
// promise means the second caller awaits the first one's request.
let _pending = null;

export const SENTENCES_URL = '/sentences/sentences.json';

export const loadSentences = (fetcher) => {
  if (!_pending) {
    const f = fetcher || (typeof fetch !== 'undefined' ? fetch : null);
    if (!f) return Promise.resolve({});
    _pending = f(SENTENCES_URL)
      .then((r) => r.json())
      .then(indexByWord)
      // A missing or malformed corpus renders NOTHING, it does not break the card. The panel is
      // an enhancement; a card that fails to show because its examples 404'd would be a
      // regression caused by an addition.
      .catch(() => ({}));
  }
  return _pending;
};

/** Tests only — the module-level cache is deliberate and would otherwise leak across cases. */
export const _resetSentencesCache = () => { _pending = null; };
