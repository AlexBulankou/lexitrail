// issue-344 — what a WRONG answer in Test mode should show before advancing.
//
// Extracted so the decision is testable at all: this repo has no React testing
// library (see `useDueToday.js`'s docstring for why), so logic left inside
// `WordCard` is logic nothing can pin — which is how #338's layout default sat
// live for six weeks.
//
// THE FINDING (#42, ITP round-2 NEW-5). Picking a wrong option marked the word
// missed and moved on. The learner never saw WHICH option was right or what the
// word meant, so a wrong answer produced no information — in the one moment of
// a session with the most learning value in it.

/** How long the correct answer stays up after a wrong pick, in ms.
 *
 * 1200 rather than something longer, and this is the number to revisit first if
 * the feature feels wrong: the cost is paid PER WRONG ANSWER, so it scales with
 * how badly the session is going — the learner having the worst session waits
 * the longest. #108/#137 spent real effort making sessions finishable and this
 * is the obvious way to undo that quietly.
 */
export const REVEAL_MS = 1200;

/**
 * The option flagged correct, or `null` when none is.
 *
 * NULL IS A REAL ANSWER, not a defensive shrug. `quiz_option1..4` come from the
 * generator (#280/#281 track its collision handling), and a card whose options
 * are missing or unflagged must fall back to today's behaviour — advance with
 * no reveal — rather than render an empty highlight. A caller that treats null
 * as "reveal nothing" degrades to the pre-#344 experience, which is the correct
 * failure direction.
 *
 * FIRST match wins, deliberately. Two options flagged correct is a generator
 * bug, and picking the first is what `.find()` already did at the call site; a
 * silent "last wins" here would make the highlighted option disagree with the
 * one the click handler scored.
 */
export const correctOption = (options) => {
  if (!Array.isArray(options)) return null;
  return options.find((o) => o && o.correct) || null;
};

/**
 * Should a click be revealed rather than advanced immediately?
 *
 * Only a WRONG answer reveals. A correct pick keeps today's timing exactly —
 * asserted in the tests, because the reveal path shares `provideFeedback` with
 * the success path and a change there would slow down the common case.
 */
export const shouldReveal = (isCorrect, options) =>
  !isCorrect && correctOption(options) !== null;
