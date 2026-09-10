"""lexitrail#280: `generate_quiz_options`'s synthetic-concatenation dedup
replaces a colliding character exactly once, then uses the result without a
second membership check. The replacement can escape the collision it was
fixing only to land on a *different* member of `existing_words` -- or, when
both possible swap values ('的' and '一') are already taken, on nowhere at
all.

Both tests here force every random choice deterministically -- a single
available concatenation candidate (so `random.choice` has nothing to choose)
and a 1-character target syllable count (so `random.randint(0, 0)` is always
0) -- so neither depends on RNG luck. That is the same discipline
`test_quiz_self_collision_276b.py` established for #277's flake.

Follow-up from #279's review (HCL, non-blocking Q): "Worth a P3 follow-up
rather than expanding this PR? I'd rather this land as the one-liner it is
while main is red." Filed as #280 (and briefly duplicated at #281, closed).
"""
import unittest
from unittest.mock import patch

from app.models import Word
from app.routes.wordsets import generate_quiz_options


class QuizReplacementCollisionTests(unittest.TestCase):

    def test_replacement_that_collides_again_is_retried_until_clean(self):
        """target='的的' collides on first pass. `random.randint` is scripted
        (not seeded -- a seed only fixes the draw, not which index a given
        draw maps to, and this repo has a documented history of flaky RNG-
        luck tests, lexitrail#269/#277) so the replace always picks index 0
        first: '的的' -> '一的', which ALSO collides (a same-syllable
        distractor already placed as a real quiz option is '一的') -- a
        second attempt is forced to index 1: '一的' -> '一一', which is
        clean. With the bug (no recheck) this would ship '一的' -- the
        blocked value -- directly."""
        target = Word(word_id=1, word="的的", wordset_id=1, def1="of", def2="")
        # Same-syllable-count distractor: placed as a REAL quiz option before
        # the synthetic loop runs, so its word enters existing_words and
        # blocks the first swap's outcome.
        distractor_real = Word(word_id=2, word="一的", wordset_id=1, def1="one-of", def2="")
        # Only candidate available for synthetic concatenation -- forced
        # choice regardless of RNG, and its own text is the target's word,
        # so it collides on the very first pass (2 syllables, no portioning).
        collider = Word(word_id=3, word="的的", wordset_id=1, def1="of (dup)", def2="")

        words_by_syllable = {2: [target, distractor_real], 3: [collider]}

        # Two synthetic slots are needed (3 quiz options - 1 real distractor).
        # Both independently replay the identical collision sequence, since
        # existing_words doesn't change between them -- 4 randint calls total,
        # each slot: index 0 (blocked) then index 1 (clean).
        with patch("app.routes.wordsets.random.randint", side_effect=[0, 1, 0, 1]):
            quiz_options = generate_quiz_options(
                target, words_by_syllable, syllable_count=2, corpus_by_syllable=None)

        self.assertEqual(len(quiz_options), 3, quiz_options)
        # generate_quiz_options normalizes every entry to [word, def1, def2]
        # before returning -- a real Word and a synthetic option are no
        # longer distinguishable by type. "[quiz word]" (the def2 field) is
        # the synthetic-option marker (see the append call this test exists
        # to pin the correctness of).
        synthetic = [opt for opt in quiz_options if opt[2] == "[quiz word]"]
        self.assertEqual(len(synthetic), 2, quiz_options)
        for opt in synthetic:
            self.assertEqual(
                opt[0], "一一",
                f"expected the retried, converged value '一一', got '{opt[0]}': "
                f"{quiz_options}")
            self.assertNotIn(
                opt[0], {target.word, distractor_real.word},
                f"synthetic option '{opt[0]}' still collides after replacement: "
                f"{quiz_options}")

    def test_exhaustion_raises_rather_than_shipping_a_colliding_option(self):
        """Both possible swap targets ('的' and '一') are already taken by
        existing_words, so no bounded retry can ever converge -- this must
        raise, not silently return a colliding option or spin forever."""
        target = Word(word_id=1, word="的", wordset_id=1, def1="of", def2="")
        blocker = Word(word_id=2, word="一", wordset_id=1, def1="one", def2="")
        collider = Word(word_id=3, word="的", wordset_id=1, def1="of (dup)", def2="")

        words_by_syllable = {1: [target, blocker], 2: [collider]}

        with self.assertRaises(ValueError):
            generate_quiz_options(
                target, words_by_syllable, syllable_count=1, corpus_by_syllable=None)

    def test_single_collision_still_resolves_without_a_second_hit(self):
        """Negative control: the ordinary case -- one collision, one clean
        replacement -- must still converge in a single pass, not loop or
        raise. Same setup as the exhaustion test but WITHOUT the blocking
        same-syllable distractor, so '一' (the swap result) is free."""
        target = Word(word_id=1, word="的", wordset_id=1, def1="of", def2="")
        collider = Word(word_id=2, word="的", wordset_id=1, def1="of (dup)", def2="")

        words_by_syllable = {1: [target], 2: [collider]}

        quiz_options = generate_quiz_options(
            target, words_by_syllable, syllable_count=1, corpus_by_syllable=None)

        self.assertEqual(len(quiz_options), 3, quiz_options)
        option_words = [opt[0] for opt in quiz_options]
        self.assertNotIn(target.word, option_words)


if __name__ == "__main__":
    unittest.main()
