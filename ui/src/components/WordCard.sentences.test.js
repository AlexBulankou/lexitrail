// lexitrail#192 — the example-sentence panel's WIRING inside WordCard.
//
// The corpus logic itself is unit-tested in ../utils/sentences.test.js against the real file.
// This pins only what that cannot see: that WordCard uses the shared loader (one request, not one
// per card), and that the panel is gated so an uncovered word renders no empty box.
//
// ⚠️ Structural, like #193's: WordCard pulls in contexts and services and this repo has no
// @testing-library, so nothing here proves the panel RENDERS. Comments are stripped first, with
// controls, because #192's own comments name every symbol these assertions look for.
import fs from 'fs';
import path from 'path';
import { stripComments } from '../utils/stripComments';

const code = () => stripComments(
  fs.readFileSync(path.resolve(__dirname, 'WordCard.js'), 'utf8'));
const css = () => fs.readFileSync(
  path.resolve(__dirname, '..', 'styles', 'WordCard.css'), 'utf8');

test('CONTROL: the stripped file is still the component', () => {
  const c = code();
  expect(c).toContain('const [hintImage, setHintImage] = useState(null)');
  expect(c.length).toBeGreaterThan(2000);
});

test('it uses the SHARED memoised loader, not its own fetch', () => {
  // 🔴 The whole point of the module-level cache is that N cards share ONE request. A card that
  // called fetch directly would be correct on screen and wrong in the network tab — SUG-2's
  // measured bug (37 hint requests in a short session) reproduced on a static asset.
  const c = code();
  expect(c).toMatch(/import \{[^}]*loadSentences[^}]*\} from '\.\.\/utils\/sentences'/);
  expect((c.match(/loadSentences\(/g) || [])).toHaveLength(1);
  expect(c).not.toMatch(/fetch\(['"`]\/sentences/);
});

test('the corpus is loaded ONCE per card, on mount — not per word', () => {
  // An effect keyed on `word` would issue a lookup per card change. The memoised promise makes
  // that cheap rather than free, and "cheap" is how 37 requests happened.
  const c = code();
  const eff = c.slice(c.indexOf('loadSentences('));
  expect(eff.slice(0, 200)).toMatch(/\}, \[\]\)/);   // empty dependency array
});

test('🔴 an uncovered word renders NO empty panel', () => {
  // #192's acceptance. ~224 of 5,614 words are covered, so the empty case is the COMMON one — a
  // panel that renders regardless would put an empty box on 96% of cards.
  expect(code()).toMatch(/sentencesFor\(sentenceIndex, word\.word\)\.length > 0 &&/);
});

test('each sentence renders hanzi, pinyin AND English', () => {
  const c = code();
  const panel = c.slice(c.indexOf('word-sentences'), c.indexOf('word-sentences') + 900);
  expect(panel).toMatch(/word-sentence-zh/);
  expect(panel).toMatch(/<PinyinText text=\{s\.py\}/);   // tone colouring, not a bare string
  expect(panel).toMatch(/word-sentence-en/);
});

test('the panel has styles', () => {
  const s = css();
  for (const cls of ['.word-sentences', '.word-sentence-zh', '.word-sentence-py', '.word-sentence-en']) {
    expect(s).toContain(`${cls} `);
  }
});
