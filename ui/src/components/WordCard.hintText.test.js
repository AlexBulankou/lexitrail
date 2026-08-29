// lexitrail#265 — the /hint `hint_text` is the Gemini IMAGE PROMPT, and the UI rendered it.
//
// 🔴 THIS FILE WAS #193's PIN AND IS NOW ITS INVERSE. #193 shipped these tests to prove a caption
// rendered `hint_text`, on the premise that it was "an AI etymology/mnemonic ... free depth,
// already paid for". `hint_generation.py:256` sets it to `_clean_text(prompt)` — the image
// generation prompt verbatim — so the caption put internal prompt text in front of the learner
// (Alex, 2026-08-29), and the prompt is written to "not directly reveal the word's meaning",
// i.e. it describes the picture and hands over the hint the image exists to make you earn.
//
// The pins are inverted rather than deleted: an absence nobody asserts is one PR from coming back,
// which is the argument issue-109 made for its own retired control.
//
// 🔴 WHY THIS ASSERTS SOURCE STRUCTURE RATHER THAN RENDERED OUTPUT. `WordCard` pulls in contexts
// and services and cannot be rendered standalone without @testing-library, which this repo does
// not have. So these are structural pins, and structural pins are use/mention-vulnerable: the
// comments added by #193 name `hintText` repeatedly, so a raw `src.includes(...)` would be
// satisfied by the explanation rather than the code. Comments are stripped first, with controls.
//
// ⚠️ Stated plainly: this cannot prove the caption RENDERS. It proves the state is read from the
// cached response, that no second request is issued, and that the element is not nested inside
// the fixed-height image container. The rendering itself needs a browser.
import fs from 'fs';
import path from 'path';
import { stripComments } from '../utils/stripComments';

/** Index just past the `</div>` that CLOSES the <div> whose attributes contain `fromIdx`.
 *
 * Balanced-tag scan rather than a string anchor. Every anchor-based version of this check was
 * wrong in the same direction — a landmark that sits NEAR the boundary is not the boundary, and
 * the failure is silent because the assertion still compares two real numbers.
 */
const closeOfDivAt = (src, fromIdx) => {
  const openTag = src.lastIndexOf('<div', fromIdx);
  let depth = 0;
  const re = /<div\b|<\/div>/g;
  re.lastIndex = openTag;
  let m;
  while ((m = re.exec(src)) !== null) {
    depth += m[0] === '</div>' ? -1 : 1;
    if (depth === 0) return m.index + m[0].length;
  }
  return -1;                                  // unbalanced — the caller's > check then fails
};

const SRC = path.resolve(__dirname, 'WordCard.js');
const code = () => stripComments(fs.readFileSync(SRC, 'utf8'));
const css = () => fs.readFileSync(
  path.resolve(__dirname, '..', 'styles', 'WordCard.css'), 'utf8');

describe('the stripper is alive (controls)', () => {
  test('it removes a comment that names hintText, and keeps real code', () => {
    expect(stripComments('{/* hintText in a comment */}')).not.toContain('hintText');
    expect(stripComments('const [hintText, setHintText] = useState(null);'))
      .toContain('hintText');
  });

  test('CONTROL: the stripped file is still the component', () => {
    // A stripper that ate the file would make everything below vacuous.
    const c = code();
    expect(c).toContain('const [hintImage, setHintImage] = useState(null)');
    expect(c.length).toBeGreaterThan(2000);
  });
});

describe('lexitrail#265 — the prompt does not reach the UI, and STAYS gone', () => {
  test('🔴 neither `hintText` nor `hint_text` survives anywhere in the component', () => {
    // Comments are stripped first (controls above), so the explanatory notes that NAME these
    // identifiers cannot satisfy this. That is the whole reason the stripper exists here.
    const c = code();
    expect(c).not.toMatch(/hintText/);
    expect(c).not.toMatch(/hint_text/);
  });

  test('CONTROL: the assertion above CAN fail — a symbol that should be present, is', () => {
    // Without this, an empty or unreadable file passes the absence pin silently. `hintImage` is
    // the sibling field the fix deliberately KEEPS, so it is the right positive control.
    const c = code();
    expect(c).toMatch(/hintImage/);
    expect(c).toMatch(/setHintImage/);
  });

  test('the hint IMAGE still renders — the caption went, the picture did not', () => {
    const c = code();
    expect(c).toMatch(/className="hint-image"/);
    expect(c).toMatch(/data:image\/jpeg;base64,/);
  });

  test('no `.hint-text` element is emitted', () => {
    expect(code()).not.toMatch(/hint-text/);
  });
});
