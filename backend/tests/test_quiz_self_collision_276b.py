"""lexitrail: main went RED on backend-tests right after #277 merged
(`issue-276: derive the worker count from the cgroup quota, not from nproc`).

The bug is NOT in #277's cpu_quota logic — it is a pre-existing dedup gap in
`generate_quiz_options`'s synthetic-concatenation fallback, present since the
2024-11-08 original (`git blame` confirms), that #277 merely tripped by
changing thread-interleaving on the seedless, module-global `random` state.
It was flagged as a known flake in lexitrail#269's own PR body ("1 of 8 local
full-suite runs... worth a follow-up if it recurs in CI") — it recurred.

The gap: `existing_words` (the dedup set the concatenation loop checks against)
is built from `all_available_words`, which by construction EXCLUDES the target
word (its id is already in `used_word_ids` before `all_available_words` is
computed). So a portioned PREFIX of another word that happens to equal the
TARGET's own text is never caught — e.g. "怎么样了"[:3] == "怎么样" — and the
route can hand back a quiz question whose "distractor" is the word itself.

This test calls `generate_quiz_options` directly (bypassing the Flask route,
the DB, and the `random.seed(int(time.time()))` call) so the reproduction is
deterministic rather than luck-of-the-second: with exactly one candidate word
available for concatenation, `random.choice` over a 1-element list always
returns that element — no RNG required to trigger the bug.

Verified against the real flake, not just this isolated call: reverting the
fix and running `test_words.py::test_get_words_by_wordset_with_portioned_options`
(the full Flask+MySQL integration path) 5x failed 2/5; with the fix, 10/10
passed.
"""
import unittest

from app.models import Word
from app.routes.wordsets import generate_quiz_options


class QuizOptionSelfCollisionTests(unittest.TestCase):

    def test_portioned_prefix_matching_target_word_is_not_offered_as_a_distractor(self):
        target = Word(word_id=1, word="怎么样", wordset_id=1, def1="how is it", def2="")
        # The only concatenation candidate. Its first 3 characters equal the
        # target's own text -- the exact collision shape.
        collider = Word(word_id=2, word="怎么样了", wordset_id=1, def1="how is it now", def2="")

        words_by_syllable = {3: [target], 4: [collider]}

        quiz_options = generate_quiz_options(
            target, words_by_syllable, syllable_count=3, corpus_by_syllable=None)

        option_words = [opt[0] for opt in quiz_options]
        self.assertNotIn(
            target.word, option_words,
            f"target word offered as its own quiz option: {quiz_options}")

    def test_still_lands_on_three_options_after_the_fix(self):
        """Negative control: the fix must not just suppress the collision -- the
        loop still has to converge on 3 options rather than looping forever or
        producing fewer."""
        target = Word(word_id=1, word="怎么样", wordset_id=1, def1="how is it", def2="")
        collider = Word(word_id=2, word="怎么样了", wordset_id=1, def1="how is it now", def2="")

        words_by_syllable = {3: [target], 4: [collider]}

        quiz_options = generate_quiz_options(
            target, words_by_syllable, syllable_count=3, corpus_by_syllable=None)

        self.assertEqual(len(quiz_options), 3)
        option_words = [opt[0] for opt in quiz_options]
        self.assertNotIn(target.word, option_words)


if __name__ == "__main__":
    unittest.main()
