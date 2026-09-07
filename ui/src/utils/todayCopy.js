/**
 * lexitrail#392 — the copy for the Today screen, in ONE place.
 *
 * Alex, 2026-09-06: *"Also reviews concept is confusing, explain what it means."*
 * I explained it to him in Slack; nothing changed on the screen, so every
 * learner still got the version without the explanation.
 *
 * ## Why a module and not four string literals in Today.js
 *
 * The issue's AC3 asks that the loading, error, headline and empty-state copy
 * "stay consistent with each other — they currently share the word and would
 * drift apart under a partial rename". A test asserting that after the fact
 * catches drift once it exists. A shared constant makes the drift
 * unrepresentable, which is the stronger form of the same requirement, and it
 * is what makes option B (a rename) a one-file change if it is ever picked.
 *
 * ## This is option A, deliberately, and B is NOT ours to take silently
 *
 * The issue offers A (keep "reviews", add a definition), B (rename to
 * something self-defining), C (both). A ships today and is trivially
 * reversible. B changes user-visible vocabulary across several screens and
 * needs Alex or zz1 to pick — a silent vocabulary change is not a bug fix.
 * `REVIEW_NOUN` exists so that pick, if it comes, is an edit here rather than
 * a hunt through JSX.
 */

/** The noun under discussion. Kept as a constant so option B is one edit. */
export const REVIEW_NOUN = 'review';
export const REVIEW_NOUN_PLURAL = 'reviews';

/**
 * The sentence the whole issue is about.
 *
 * It has to carry BOTH halves of AC1 — what a review IS ("a word you have seen
 * before") and what makes one DUE ("just before you are likely to forget it").
 * Either half alone leaves the learner where they started: the first without
 * the second explains the noun but not the number on the screen.
 */
export const REVIEW_DEFINITION =
  'A word you have seen before, back just before you are likely to forget it.';

/** `3 reviews due today` / `1 review due today`. */
export const dueHeadlineSuffix = (total) =>
  `${total === 1 ? REVIEW_NOUN : REVIEW_NOUN_PLURAL} due today`;

export const TODAY_COPY = {
  loading: `Checking today's ${REVIEW_NOUN_PLURAL}…`,
  error: `Couldn't load today's ${REVIEW_NOUN_PLURAL}.`,
  emptyHeadline: 'All caught up',
  emptySub: 'Nothing is due right now. Come back tomorrow.',
  /**
   * Was "Practice anyway", which only parses if you already know what you are
   * declining (AC2). Naming the alternative makes it a choice rather than a
   * dismissal of a thing you were never told about.
   */
  emptyAction: 'Practice other words anyway',
};
