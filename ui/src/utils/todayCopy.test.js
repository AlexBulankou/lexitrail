/**
 * lexitrail#392 — pins the definition exists, says BOTH halves, and that
 * Today.js actually renders it.
 *
 * ⚠️ This repo has no @testing-library, so a component cannot be rendered
 * (see WordCard.hintText.test.js for the same constraint). The module half is
 * a real unit test; the Today.js half is a STRUCTURAL pin and is use/mention
 * vulnerable — the comments I added to Today.js name `REVIEW_DEFINITION`
 * repeatedly, so a raw `src.includes(...)` would be satisfied by the
 * explanation rather than the code. Comments are stripped first, and there is
 * a control proving the stripping actually happened.
 */
import fs from 'fs';
import path from 'path';
import { stripComments } from './stripComments';
import {
  REVIEW_DEFINITION, REVIEW_NOUN, REVIEW_NOUN_PLURAL, TODAY_COPY,
  dueHeadlineSuffix,
} from './todayCopy';

const TODAY_SRC = fs.readFileSync(
  path.resolve(__dirname, '..', 'components', 'Today.js'), 'utf8');
const CODE = stripComments(TODAY_SRC);

describe('issue-392: "review" is defined on the screen', () => {
  /**
   * AC1 has TWO halves and the issue is explicit that either alone leaves the
   * learner where they started: what a review IS, and what makes one DUE.
   * Pinned as two assertions rather than one string match, so a future rewrite
   * that drops the timing half reds.
   */
  it('the definition says what a review IS and what makes it DUE', () => {
    expect(REVIEW_DEFINITION).toMatch(/seen before/i);        // what it is
    expect(REVIEW_DEFINITION).toMatch(/forget/i);             // what makes it due
    expect(REVIEW_DEFINITION.length).toBeLessThan(120);       // one mobile line
  });

  it('every Today string shares ONE noun, so a rename cannot half-land', () => {
    expect(TODAY_COPY.loading).toContain(REVIEW_NOUN_PLURAL);
    expect(TODAY_COPY.error).toContain(REVIEW_NOUN_PLURAL);
    expect(dueHeadlineSuffix(3)).toContain(REVIEW_NOUN_PLURAL);
    expect(dueHeadlineSuffix(1)).toContain(REVIEW_NOUN);
  });

  it('singular and plural are actually different — the count is not cosmetic', () => {
    expect(dueHeadlineSuffix(1)).toBe('review due today');
    expect(dueHeadlineSuffix(3)).toBe('reviews due today');
    expect(dueHeadlineSuffix(0)).toBe('reviews due today');
  });

  /**
   * AC2. "Practice anyway" only parses if you already know what you are
   * declining. This pins that the action NAMES what it offers, and that the
   * old bare form is gone.
   */
  it('the empty-state action names what it offers', () => {
    expect(TODAY_COPY.emptyAction).toMatch(/words/i);
    expect(TODAY_COPY.emptyAction).not.toBe('Practice anyway');
  });

  it('Today.js renders the definition on BOTH the empty and populated states', () => {
    const hits = CODE.match(/\{REVIEW_DEFINITION\}/g) || [];
    expect(hits).toHaveLength(2);
  });

  it('Today.js carries no hardcoded copy that could drift from the module', () => {
    expect(CODE).not.toContain("Checking today's reviews");
    expect(CODE).not.toContain("Couldn't load today's reviews");
    expect(CODE).not.toContain('Practice anyway');
    expect(CODE).not.toContain("'reviews due today'");
  });

  /**
   * CONTROL: without this, a `stripComments` that returned "" would make every
   * `not.toContain` above pass vacuously, and the `{REVIEW_DEFINITION}` count
   * would be 0 rather than 2 — so that one would red, but the four negative
   * assertions are the ones that need this.
   */
  it('CONTROL: stripComments left the CODE and removed the COMMENTS', () => {
    expect(CODE).toContain('REVIEW_DEFINITION');            // code survived
    expect(CODE).toContain('today-explainer');
    expect(TODAY_SRC).toContain('reviews concept is confusing');  // the comment IS there...
    expect(CODE).not.toContain('reviews concept is confusing');   // ...and was stripped
  });
});
