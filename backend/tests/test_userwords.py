import unittest
from tests.utils import TestUtils
from app.models import User, Wordset, Word, UserWord

class UserWordTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client, cls.app, _ = TestUtils.setup_test_app()  # Ignore temp_db_name

    @classmethod
    def tearDownClass(cls):
        TestUtils.teardown_test_db(cls.app)

    def test_get_userwords(self):
        with self.app.app_context():
            user = User(email='test@example.com')
            wordset = Wordset(description='Test Wordset')
            word = Word(word='Test Word', wordset_id=1, def1='Definition 1', def2='Definition 2')
            db.session.add_all([user, wordset, word])
            db.session.commit()

        response = self.client.get('/userwords/query?user_id=test@example.com&wordset_id=1')
        self.assertEqual(response.status_code, 200)

    def test_update_recall_state(self):
        with self.app.app_context():
            user = User(email='user@example.com')
            wordset = Wordset(description='Test Wordset')
            word = Word(word='Test Word', wordset_id=1, def1='Definition 1', def2='Definition 2')
            userword = UserWord(user_id=user.email, word_id=word.word_id, is_included=True, recall_state=1)
            db.session.add_all([user, wordset, word, userword])
            db.session.commit()

        response = self.client.put(f'/userwords/{user.email}/{word.word_id}/recall', json={'recall_state': 3})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Recall state updated successfully', response.data)

if __name__ == '__main__':
    unittest.main()
