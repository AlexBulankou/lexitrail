'use strict';
/**
 * API fixtures for SURROGATE RUNS ONLY.
 *
 * Against the live site the real API answers and this module must stay off --
 * measuring a mocked page and reporting it as prod would defeat the whole point.
 * It exists because a surrogate run (references/local-surrogate.md) is usually
 * needed exactly when the network is blocked, which blocks api.lexitrail.com too,
 * and a game screen with no words renders an error state: you would be measuring
 * the error page, not the card grid.
 *
 * Shapes are taken from the product, not invented:
 * EVERY list endpoint is wrapped in a `{data: [...]}` envelope. That is not a
 * guess -- wordsService.js does `response.data.filter(...)` and
 * useWordsetLoader.js does `response.data` / `.then(r => r.data)`, so a bare
 * array makes the app throw "Cannot read properties of undefined (reading
 * 'filter')" and render its error state. Which is exactly what the first
 * version of this file did, and it cost a whole sweep: eleven routes reported
 * `ok` with 23 elements, because an error page IS a page. If you change a shape
 * here, re-check the consumer, not just the HTTP status.
 *
 *   GET /wordsets                -> {data: [{wordset_id, description}]}   (wordsService.js:58)
 *   GET /wordsets/:id/words      -> {data: [{word_id, word, wordset_id, def1, def2}]}
 *                                   (useWordsetLoader.js:201 `response.data`)
 *   GET /userwords/query         -> {data: [{word_id, is_included, recall_state, recall_histories}]}
 *                                   (useWordsetLoader.js:199 `.then(r => r.data)`)
 *   GET /userwords/due-counts    -> {data: {<wordset_id>: n}}
 *   GET /hint/generate_hint      -> 404 (no hint; the UI handles this path)
 *   POST *                       -> 200 {} (writes must never leave the box)
 *
 * Word content is REAL HSK1 vocabulary from terraform/csv/HSK1.csv. Placeholder
 * hanzi would change the rendered box width, and card layout is the thing under
 * measurement -- a fake string is a fake measurement.
 */

const API_RE = /api\.lexitrail\.com/;

// Real HSK1 rows: [word_id, word, def1 (pinyin), def2 (english)]
const HSK1 = [
  [1, '我', 'wǒ', 'I, me'],
  [2, '我们', 'wǒmen', 'we, us (pl.)'],
  [3, '你', 'nǐ', 'you'],
  [4, '他', 'tā', 'he, him'],
  [5, '她', 'tā', 'she, her'],
  [6, '这 (这儿)', 'zhè ( zhèr)', 'this (here)'],
  [7, '那 (那儿)', 'nà (nàr)', 'that (there)'],
  [8, '哪 (哪儿)', 'nǎ (nǎr)', 'which (where)'],
  [9, '谁', 'shéi', 'who, whom'],
  [10, '什么', 'shénme', 'what'],
  [11, '多少', 'duōshao', 'how many, how much'],
  [12, '几', 'jǐ', 'how many, a few'],
  [13, '怎么', 'zěnme', 'how'],
  [14, '怎么样', 'zěnmeyàng', 'how about'],
  [15, '没关系', 'méi guānxi', "it doesn't matter"],
  [16, '认识', 'rènshi', 'to know, to recognize'],
  [17, '朋友', 'péngyou', 'friend'],
  [18, '老师', 'lǎoshī', 'teacher'],
  [19, '学生', 'xuésheng', 'student'],
  [20, '同学', 'tóngxué', 'classmate'],
];

const WORDSETS = [
  { wordset_id: 1, description: 'HSK1' },
  { wordset_id: 2, description: 'HSK2' },
  { wordset_id: 3, description: 'HSK3' },
  { wordset_id: 4, description: 'HSK4' },
  { wordset_id: 5, description: 'HSK5' },
  { wordset_id: 6, description: 'HSK6' },
  { wordset_id: 8, description: 'HSK1+2+3' },
];

/**
 * `quiz_options` is REQUIRED on every word, in every mode -- not just TEST.
 * useWordsetLoader.js builds the option list inside the unconditional `.map`
 * over every loaded word (`word.quiz_options[0][0]` ...), so a word without it
 * throws "Cannot read properties of undefined (reading '0')" and takes the
 * whole PRACTICE screen down with it. Three distractor triples of
 * [word, pinyin, def2]; the correct answer is appended by the loader itself.
 */
const quizOptionsFor = (i) => {
  const others = [0, 1, 2].map((k) => HSK1[(i + k + 1) % HSK1.length]);
  return others.map(([, word, def1, def2]) => [word, def1, def2]);
};

const words = (wordsetId) =>
  HSK1.map(([word_id, word, def1, def2], i) => ({
    word_id, word, wordset_id: Number(wordsetId), def1, def2, hint_text: null,
    quiz_options: quizOptionsFor(i),
  }));

/**
 * Give a few words a recall history so the red/green `.mastery-indicator` tiles
 * actually render. A fixture where every word is pristine hides every defect in
 * the history row -- including the flex-end clipping this repo already knows about.
 */
const userwords = () => ({
  data: HSK1.map(([word_id], i) => ({
    word_id,
    is_included: true,
    recall_state: i % 5,
    recall_histories: Array.from({ length: i % 9 }, (_, k) => ({
      recall: k % 3 !== 0,
      recall_time: new Date(Date.now() - (k + 1) * 86400000).toISOString(),
      provenance: 'single',
    })),
  })),
});

const json = (route, body, status = 200) =>
  route.fulfill({
    status,
    contentType: 'application/json',
    headers: { 'access-control-allow-origin': '*' },
    body: JSON.stringify(body),
  });

/**
 * Install on the CONTEXT before the first navigation, same as the analytics abort.
 * Returns a counter so a run can prove the mock was actually exercised -- a mock
 * that silently never matched would leave you measuring the error state again.
 */
async function installApiMock(context) {
  const state = { served: 0, byEndpoint: {} };

  await context.route(API_RE, async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const p = url.pathname;
    state.served++;
    state.byEndpoint[p] = (state.byEndpoint[p] || 0) + 1;

    if (req.method() !== 'GET') return json(route, {});          // writes stay local

    let m;
    if (p === '/wordsets') return json(route, { data: WORDSETS });
    if ((m = p.match(/^\/wordsets\/(\d+)\/words$/))) return json(route, { data: words(m[1]) });
    if (p === '/userwords/query') return json(route, userwords());
    if (p === '/userwords/due-counts') return json(route, { data: { 1: HSK1.length } });
    if (p.startsWith('/users/')) return json(route, { email: 'demo@lexitrail.demo' });
    if (p.startsWith('/hint/')) return json(route, { message: 'no hint' }, 404);

    return json(route, {}, 404);
  });

  return state;
}

module.exports = { installApiMock, API_RE, WORDSETS, HSK1 };
