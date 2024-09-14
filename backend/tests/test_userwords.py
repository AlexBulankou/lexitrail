import unittest
from datetime import datetime
from tests.utils import TestUtils
from app.models import User, Wordset, Word, UserWord, RecallHistory
from app import db


class UserWordTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up the test application and temporary database."""
        cls.client, cls.app, cls.temp_db_name = TestUtils.setup_test_app()

    @classmethod
    def tearDownClass(cls):
        """Tear down the temporary database after all tests."""
        TestUtils.teardown_test_db(cls.app, cls.temp_db_name)

    def setUp(self):
        """Clean up the database before each test."""
        with self.app.app_context():
            TestUtils.clear_database(db)

    def test_get_userwords(self):
        """Test fetching userwords by user and wordset."""
        with self.app.app_context():
            # Create test userword
            user, wordset, word, _ = TestUtils.create_test_userword(db)

            # Query userwords for the created user and wordset
            response = self.client.get(f'/userwords/query?user_id={user.email}&wordset_id={wordset.wordset_id}')
            self.assertEqual(response.status_code, 200)

            # Get the JSON response and extract the 'data' field
            response_data = response.get_json()
            userword_data = response_data.get('data')

            # Assert that the data is a list and contains expected data
            self.assertIsInstance(userword_data, list)
            self.assertGreater(len(userword_data), 0)



    def test_update_recall_state_existing_userword(self):
        """Test updating the recall state of an existing userword."""
        with self.app.app_context():
            # Create test data
            user, _, word, userword = TestUtils.create_test_userword(db)

            # Perform update recall state test
            response = self.client.put(
                f'/userwords/{user.email}/{word.word_id}/recall',
                json={'recall_state': 2, 'recall': True, 'is_included': True}
            )
            self.assertEqual(response.status_code, 200)

            # Verify that the UserWord was updated
            updated_userword = db.session.query(UserWord).filter_by(user_id=user.email, word_id=word.word_id).first()
            self.assertIsNotNone(updated_userword)
            self.assertEqual(updated_userword.recall_state, 2)
            self.assertEqual(updated_userword.is_included, True)

            # Verify that RecallHistory was updated
            recall_history = db.session.query(RecallHistory).filter_by(user_id=user.email, word_id=word.word_id).first()
            self.assertIsNotNone(recall_history)
            self.assertEqual(recall_history.new_recall_state, 2)
            self.assertEqual(recall_history.old_recall_state, 1)

    def test_update_recall_state_new_userword(self):
        """Test creating a new userword entry and updating recall state."""
        with self.app.app_context():
            # Use TestUtils to create the test user, wordset, and word
            user, wordset, word = TestUtils.create_test_word(db)

            # Perform update recall state test for a new userword entry
            response = self.client.put(
                f'/userwords/{user.email}/{word.word_id}/recall',
                json={'recall_state': 2, 'recall': True, 'is_included': True}
            )
            self.assertEqual(response.status_code, 200)

            # Verify the new userword was created
            userword = db.session.query(UserWord).filter_by(user_id=user.email, word_id=word.word_id).first()
            self.assertIsNotNone(userword)
            self.assertEqual(userword.recall_state, 2)
            self.assertEqual(userword.is_included, True)

            # Verify that RecallHistory was updated
            recall_history = db.session.query(RecallHistory).filter_by(user_id=user.email, word_id=word.word_id).first()
            self.assertIsNotNone(recall_history)
            self.assertEqual(recall_history.new_recall_state, 2)
            self.assertEqual(recall_history.old_recall_state, None)  # No old recall state for new entry
            self.assertEqual(recall_history.recall, True)



if __name__ == '__main__':
    unittest.main()
