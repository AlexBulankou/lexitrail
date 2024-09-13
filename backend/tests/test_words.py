import unittest
from tests.utils import TestUtils
from app.models import Wordset
from app import db


class WordsTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client, cls.app, cls.temp_db_name = TestUtils.setup_test_app()

    @classmethod
    def tearDownClass(cls):
        TestUtils.teardown_test_db(cls.app, cls.temp_db_name)

    def test_get_words_by_wordset(self):
        with self.app.app_context():
            wordset = Wordset(description='Test Wordset')
            db.session.add(wordset)
            db.session.commit()
        response = self.client.get(f'/wordsets/{wordset.wordset_id}/words')
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
