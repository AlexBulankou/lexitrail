import unittest
from datetime import datetime
from tests.utils import TestUtils
from app.models import User, Wordset, Word, UserWord, RecallHistory
from app import db


class UserWordTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Set up the test application and temporary database
        cls.client, cls.app, cls.temp_db_name = TestUtils.setup_test_app()

    @classmethod
    def tearDownClass(cls):
        # Tear down the temporary database after all tests
        TestUtils.teardown_test_db(cls.app, cls.temp_db_name)

    def test_get_userwords(self):
        """Test fetching userwords by user and wordset."""
        with self.app.app_context():
            # Create a user, wordset, and word
            user = User(email='test@example.com')
            wordset = Wordset(description='Test Wordset')
            db.session.add(wordset)
            db.session.commit()

            word = Word(word='Test Word', wordset_id=wordset.wordset_id, def1='Definition 1', def2='Definition 2')
            db.session.add_all([user, word])
            db.session.commit()

        # Query userwords for the created user and wordset
        response = self.client.get('/userwords/query?user_id=test@example.com&wordset_id=1')
        self.assertEqual(response.status_code, 200)

    def test_update_recall_state(self):
        """Test updating the recall state of a userword."""
        with self.app.app_context():
            # Clean up existing data to avoid conflicts
            db.session.query(UserWord).delete()
            db.session.query(Word).delete()
            db.session.query(Wordset).delete()
            db.session.query(User).delete()
            db.session.commit()

            # Create unique user, wordset, and word
            user = User(email='user@example.com')
            wordset = Wordset(description='Test Wordset')
            db.session.add(wordset)
            db.session.commit()  # Commit wordset to get wordset_id

            word = Word(
                word=f'Test Word {datetime.utcnow().timestamp()}',
                wordset_id=wordset.wordset_id,
                def1='Definition 1',
                def2='Definition 2'
            )
            db.session.add(word)
            db.session.commit()  # Commit word to get word_id

            # Create UserWord with the populated word_id
            userword = UserWord(user_id=user.email, word_id=word.word_id, is_included=True, recall_state=1)
            db.session.add_all([user, userword])
            db.session.commit()

            # Perform update recall state test
            response = self.client.put(f'/userwords/{userword.id}/recall', json={'recall_state': 2})
            self.assertEqual(response.status_code, 200)

            # Verify that RecallHistory was updated
            recall_history = db.session.query(RecallHistory).filter_by(user_id=user.email, word_id=word.word_id).first()
            self.assertIsNotNone(recall_history)
            self.assertEqual(recall_history.new_recall_state, 2)
            self.assertEqual(recall_history.old_recall_state, 1)


if __name__ == '__main__':
    unittest.main()
