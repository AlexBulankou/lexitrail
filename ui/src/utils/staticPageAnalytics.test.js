/**
 * issue-393 — the GA4 tag is on ALL THREE static families, from one constant.
 *
 * The defect: ~5,600 standalone word/HSK/gloss pages carried no tag, so GSC
 * showed 2.87K impressions at position ~10 while GA4 showed 2 Organic Search
 * sessions and zero /hsk* pagePaths. Not a low number — a BLIND one, and the
 * whole lighthouse funnel (#184/#365/#367) was arriving on pages the property
 * never saw.
 *
 * Why this file exists rather than trusting the three renderers: the snippet is
 * shared, but each family injects it at its own call site, so a future edit can
 * drop it from ONE family and leave the other two green. That is the failure
 * this pins — per-family, not "the constant exists".
 */

import { renderPage, GA4_SNIPPET, GA4_ID } from './hskPages';
import { renderWordPage } from './wordPages';
import { renderGlossPage, collectGlossGroup } from './glossPages';

const WORDS = [
  { word: '我', pinyin: 'wǒ', def1: 'I; me', wordset: 'HSK1', level: 1 },
];

/** The two things a GA4 install must both have; either alone is inert. */
function assertTagged(html, label) {
  expect(html).toContain(`googletagmanager.com/gtag/js?id=${GA4_ID}`);
  expect(html).toContain(`gtag('config', '${GA4_ID}')`);
  // ...and inside <head>, before </head> — a loader after it still runs, but
  // late enough to miss a fast bounce, which is the arrival this measures.
  const head = html.slice(0, html.indexOf('</head>'));
  expect(head).toContain('googletagmanager.com/gtag/js');
  expect(label).toBeTruthy();
}

describe('issue-393: every static family carries the GA4 loader', () => {
  it('the shared constant carries BOTH halves', () => {
    expect(GA4_SNIPPET).toContain('googletagmanager.com/gtag/js');
    expect(GA4_SNIPPET).toContain(`gtag('config', '${GA4_ID}')`);
  });

  it('HSK level pages', () => {
    assertTagged(renderPage(1, WORDS), 'hsk');
  });

  it('word pages', () => {
    assertTagged(renderWordPage(WORDS[0], { level: 1 }), 'word');
  });

  it('gloss landers', () => {
    // Built through collectGlossGroup rather than hand-shaped: renderGlossPage
    // destructures { primary, alternates }, so a hand-built fixture tests my
    // guess at the contract instead of the contract.
    // Row shape lifted from glossPages.test.js — `def1` is the PINYIN and
    // `def2` the gloss, which is not what the field names suggest. I guessed
    // twice and collectGlossGroup returned null both times; the sibling test
    // is the contract.
    const rows = [
      { word_id: '2771', word: '澄清', wordset_id: '6', def1: 'chéngqīng', def2: 'clarify' },
    ];
    const group = collectGlossGroup(rows, 'clarify');
    const query = { slug: 'clarify-in-chinese', gloss: 'clarify' };
    assertTagged(renderGlossPage(query, group, {}), 'gloss');
  });

  it('the SAME measurement id as the SPA shell — so a word-page visitor crossing into the app stays ONE session', () => {
    // This is what makes issue-393's AC3 (word page -> / -> wordset_click)
    // measurable at all. Two different ids would make it two disjoint visits
    // and the conversion claim unevaluable, which is the state this fixes.
    expect(GA4_ID).toBe('G-910V8PX54C');
  });
});
