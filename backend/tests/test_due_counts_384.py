"""issue-384: `/userwords/due-counts` — the Today home's seven integers.

The screen this replaces asked `/userwords/query` once per wordset and counted
in the browser: ~5,600 words with recall history across seven concurrent
requests, to render seven numbers. It took 10s+ and then failed outright.

These tests pin the DUE RULE, not the speed — speed here is structural (the
response does not grow with the set) and needs no test to stay true. What needs
pinning is that this second implementation agrees with `ui/src/utils/srs.js`,
because a count that disagrees with the session it opens is the one failure the
Today home cannot survive.
"""
import unittest
from datetime import datetime, timedelta

from tests.utils import TestUtils
from app.auth import default_mock_user
from app.models import User, Wordset, Word, UserWord, RecallHistory
from app import db
from app.srs_ladder import interval_days


class DueCountsTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client, cls.app, cls.temp_db_name = TestUtils.setup_test_app()

    @classmethod
    def tearDownClass(cls):
        TestUtils.teardown_test_db(cls.temp_db_name)

    def setUp(self):
        with self.app.app_context():
            TestUtils.clear_database(db)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _word(self, wordset, name):
        w = Word(word=name, wordset_id=wordset.wordset_id, def1='p', def2='e')
        db.session.add(w)
        db.session.commit()
        return w

    def _userword(self, user, word, *, recall_state=0, is_included=True,
                  last_review_days_ago=None):
        uw = UserWord(user_id=user.email, word_id=word.word_id,
                      is_included=is_included, recall_state=recall_state)
        db.session.add(uw)
        if last_review_days_ago is not None:
            db.session.add(RecallHistory(
                user_id=user.email, word_id=word.word_id, is_included=is_included,
                recall=True,
                recall_time=datetime.utcnow() - timedelta(days=last_review_days_ago),
                new_recall_state=recall_state, old_recall_state=recall_state,
            ))
        db.session.commit()
        return uw

    def _counts(self):
        r = self.client.get('/userwords/due-counts?user_id=' + default_mock_user)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        return {row['wordset_id']: row['due'] for row in r.get_json()['data']}

    def _fixture(self):
        user = db.session.query(User).filter_by(email=default_mock_user).first()
        if user is None:
            user = User(email=default_mock_user)
            db.session.add(user)
        ws = Wordset(description='HSK-test')
        db.session.add(ws)
        db.session.commit()
        return user, ws

    # ── the rule ─────────────────────────────────────────────────────────────

    def test_a_word_never_practised_is_due(self):
        """`isDue`'s null branch. This is the arm that makes a fresh set count
        as entirely due, and getting it wrong silently reports 0 to a learner
        who has everything to do."""
        with self.app.app_context():
            user, ws = self._fixture()
            self._userword(user, self._word(ws, 'a'), last_review_days_ago=None)
            self.assertEqual(self._counts().get(ws.wordset_id), 1)

    def test_a_word_reviewed_inside_its_interval_is_NOT_due(self):
        with self.app.app_context():
            user, ws = self._fixture()
            # state 0 rests 7 days; reviewed 1 day ago -> not due.
            self._userword(user, self._word(ws, 'a'), recall_state=0,
                           last_review_days_ago=1)
            self.assertEqual(self._counts().get(ws.wordset_id, 0), 0)

    def test_a_word_past_its_interval_is_due(self):
        with self.app.app_context():
            user, ws = self._fixture()
            self._userword(user, self._word(ws, 'a'), recall_state=0,
                           last_review_days_ago=8)
            self.assertEqual(self._counts().get(ws.wordset_id), 1)

    def test_an_EXCLUDED_word_never_counts(self):
        """`isWordDue`'s first line. An excluded word can be long overdue and
        must still not appear — otherwise the headline offers work the session
        will not contain."""
        with self.app.app_context():
            user, ws = self._fixture()
            self._userword(user, self._word(ws, 'a'), recall_state=0,
                           is_included=False, last_review_days_ago=999)
            self.assertEqual(self._counts().get(ws.wordset_id, 0), 0)

    def test_every_rung_of_the_ladder_is_honoured(self):
        """One word per rung, each reviewed exactly one day INSIDE its interval
        and one day PAST it. Pins the whole ladder rather than a sample: an
        off-by-one in a single CASE arm is invisible to a spot check.
        """
        with self.app.app_context():
            user, ws = self._fixture()
            states = [-4, -3, -2, -1, 0, 1, 2, 3, 9]
            for i, st in enumerate(states):
                days = interval_days(st)
                # PAST its interval -> due. (+1 day, and +1 for the 0-day rungs
                # where "inside" does not exist.)
                self._userword(user, self._word(ws, f'past{i}'), recall_state=st,
                               last_review_days_ago=days + 1)
            self.assertEqual(self._counts().get(ws.wordset_id), len(states),
                             'every state past its interval must be due')

            TestUtils.clear_database(db)
            user, ws = self._fixture()
            inside = [st for st in states if interval_days(st) > 0]
            for i, st in enumerate(inside):
                self._userword(user, self._word(ws, f'in{i}'), recall_state=st,
                               last_review_days_ago=interval_days(st) - 1)
            self.assertEqual(self._counts().get(ws.wordset_id, 0), 0,
                             'no state inside its interval may be due')

    def test_the_MOST_RECENT_review_decides_not_the_first_row(self):
        """`lastRecallTimeOf` takes the max because nothing sorts the history.
        A word with an old review AND a fresh one is rested, and reading the
        wrong row would mark it due — offering work that is not there."""
        with self.app.app_context():
            user, ws = self._fixture()
            w = self._word(ws, 'a')
            self._userword(user, w, recall_state=0, last_review_days_ago=99)
            db.session.add(RecallHistory(
                user_id=user.email, word_id=w.word_id, is_included=True,
                recall=True, recall_time=datetime.utcnow() - timedelta(days=1),
                new_recall_state=0, old_recall_state=0))
            db.session.commit()
            self.assertEqual(self._counts().get(ws.wordset_id, 0), 0)

    def test_counts_are_PER_WORDSET(self):
        with self.app.app_context():
            user, ws1 = self._fixture()
            ws2 = Wordset(description='HSK-test-2')
            db.session.add(ws2)
            db.session.commit()
            self._userword(user, self._word(ws1, 'a'), last_review_days_ago=None)
            self._userword(user, self._word(ws1, 'b'), last_review_days_ago=None)
            self._userword(user, self._word(ws2, 'c'), last_review_days_ago=None)
            counts = self._counts()
            self.assertEqual(counts.get(ws1.wordset_id), 2)
            self.assertEqual(counts.get(ws2.wordset_id), 1)

    def test_a_wordset_with_nothing_due_is_ABSENT_not_zero(self):
        """Documented contract, pinned so a caller cannot start relying on a
        zero row appearing. The client defaults a missing set to 0."""
        with self.app.app_context():
            user, ws = self._fixture()
            self._userword(user, self._word(ws, 'a'), recall_state=0,
                           last_review_days_ago=1)
            self.assertNotIn(ws.wordset_id, self._counts())

    def test_another_users_history_cannot_rest_your_word(self):
        """The MAX subquery filters on user_id. Without that filter a second
        learner's recent review of the same word would mark it rested for
        everyone — a wrong answer in the direction of showing LESS work, which
        nobody reports."""
        with self.app.app_context():
            user, ws = self._fixture()
            other = User(email='other@example.com')
            db.session.add(other)
            db.session.commit()
            w = self._word(ws, 'a')
            self._userword(user, w, recall_state=0, last_review_days_ago=99)
            db.session.add(RecallHistory(
                user_id=other.email, word_id=w.word_id, is_included=True,
                recall=True, recall_time=datetime.utcnow(),
                new_recall_state=0, old_recall_state=0))
            db.session.commit()
            self.assertEqual(self._counts().get(ws.wordset_id), 1)

    def test_missing_user_id_is_a_400(self):
        with self.app.app_context():
            r = self.client.get('/userwords/due-counts')
            self.assertEqual(r.status_code, 400)


if __name__ == '__main__':
    unittest.main()
