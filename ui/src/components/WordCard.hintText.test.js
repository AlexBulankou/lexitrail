// lexitrail#193 — the /hint response already returned an AI etymology and the UI discarded it.
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

describe('hint_text is read from the SAME cached response', () => {
  test('the text is taken off the /hint response', () => {
    expect(code()).toMatch(/setHintText\(response\.data\.hint_text/);
  });

  test('🔴 no SECOND request — the request count is unchanged', () => {
    // #193's AC: "No additional /hint request is issued (reuses the cached response)." The two
    // existing calls are the initial fetch and the explicit regenerate; a third would mean the
    // caption cost a network round trip per card, undoing SUG-2's whole point.
    const c = code();
    expect((c.match(/await getHint\(/g) || [])).toHaveLength(1);
    expect((c.match(/await regenerateHint\(/g) || [])).toHaveLength(1);
  });

  test('regenerate replaces BOTH fields, not just the image', () => {
    // BUG SHAPE: updating only hintImage leaves a stale caption describing the PREVIOUS mnemonic
    // next to a freshly generated image -- worse than no caption, because it reads as authoritative.
    const regen = code().split('regenerateHint(word.user_id, word.word_id)')[1] || '';
    expect(regen.slice(0, 400)).toMatch(/setHintText\(/);
  });
});

describe('the caption is independent of the image', () => {
  test('gated on hintText, not on hintImage', () => {
    // The two fields are independently nullable. A word with text and no image is exactly the
    // case where the caption is the ONLY hint content, so nesting it under the image would hide
    // it precisely where it matters most.
    expect(code()).toMatch(/isHintDisplayed && hintText &&/);
  });

  test('🔴 it is NOT inside .hint-image-container', () => {
    // That container is pinned to a hard 85px inline with the image at height:100%; a caption
    // placed inside it is squeezed against a fixed height. Asserted by position: the caption
    // block must appear AFTER the container closes.
    //
    // 🔴 MY FIRST VERSION OF THIS WAS VACUOUS and a mutation caught it. It compared the caption's
    // position against the WRAPPER's closing </div> -- which sits well inside the container -- so
    // a caption genuinely nested in the container still satisfied it. Anchor on the CONTAINER's
    // end, which is the `) : (<></>)}` that closes its conditional.
    const c = code();
    const containerStart = c.indexOf('className="hint-image-container"');
    const caption = c.indexOf('className="hint-text-container"');
    expect(containerStart).toBeGreaterThan(-1);      // both anchors exist, so the
    expect(caption).toBeGreaterThan(-1);             // comparison below is not vacuous
    const containerEnd = c.indexOf(') : (<></>)}', containerStart);
    expect(containerEnd).toBeGreaterThan(containerStart);
    expect(caption).toBeGreaterThan(containerEnd);
  });

  test('it is cleared on word change AND on a same-word action', () => {
    // Without the clear, a caption from the previous word survives onto the next one.
    expect((code().match(/setHintText\(null\)/g) || []).length).toBeGreaterThanOrEqual(2);
  });
});

test('the caption has styles, and they WRAP — unlike pinyin (#190)', () => {
  const s = css();
  expect(s).toMatch(/\.hint-text-container\s*\{/);
  expect(s).toMatch(/\.hint-text\s*\{/);
  // A mnemonic runs to a couple of sentences: this is prose. #190's nowrap is correct for a
  // pinyin token and would be wrong here, so the two are asserted apart deliberately.
  expect(s.split('.hint-text {')[1].slice(0, 300)).not.toMatch(/white-space:\s*nowrap/);
});
