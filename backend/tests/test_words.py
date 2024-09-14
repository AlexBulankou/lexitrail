import unittest
from tests.utils import TestUtils
from app import db


class WordsTests(unittest.TestCase):

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
        # Ensure the database cleanup happens within an application context
        with self.app.app_context():
            TestUtils.clear_database(db)

    def test_get_words_by_wordset(self):
        """Test retrieving words by wordset using TestUtils."""
        with self.app.app_context():
            # Create test word, wordset, and user using the utility function
            user, wordset, word = TestUtils.create_test_word(db)
    
        # Send a request to get words by wordset
        response = self.client.get(f'/wordsets/{wordset.wordset_id}/words')
    
        # Print the response in case of failure for debugging
        if response.status_code != 200:
            print("Response JSON:", response.get_json())
            print("Response Status Code:", response.status_code)
    
        # Verify the response is successful
        self.assertEqual(response.status_code, 200)

        # Verify the response contains the expected word data
        words_data = response.get_json()
        self.assertIsInstance(words_data, dict)
        self.assertGreater(len(words_data.get('data', [])), 0)


if __name__ == '__main__':
    unittest.main()
