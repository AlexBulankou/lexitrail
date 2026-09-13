import unittest
from tests.utils import TestUtils
from app import db


class WordsetTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client, cls.app, cls.temp_db_name = TestUtils.setup_test_app()

    @classmethod
    def tearDownClass(cls):
        TestUtils.teardown_test_db(cls.temp_db_name)

    def setUp(self):
        """Clean up the database before each test."""
        with self.app.app_context():
            TestUtils.clear_database(db)

    def test_get_wordsets(self):
        response = self.client.get('/wordsets')
        self.assertEqual(response.status_code, 200)

    # ---- lexitrail#427: exclude testing-artifact wordsets from GET /wordsets ----

    def test_get_wordsets_excludes_a_test_description_wordset(self):
        """THE bug's own shape: a wordset whose description is exactly
        'test' must not appear in the public list -- that is what rendered
        as a homepage product tile on the signed-out marketing surface."""
        with self.app.app_context():
            TestUtils.create_test_wordset(db, description='test')
            TestUtils.create_test_wordset(db, description='HSK1')

        response = self.client.get('/wordsets')
        self.assertEqual(response.status_code, 200)
        descriptions = [ws['description'] for ws in response.get_json()['data']]
        self.assertNotIn('test', descriptions)
        self.assertIn('HSK1', descriptions)

    def test_get_wordsets_excludes_test_description_case_insensitively(self):
        """The known bad row's description could plausibly be 'Test' or
        'TEST' depending on how it was entered -- the exclusion must not
        depend on exact casing."""
        with self.app.app_context():
            TestUtils.create_test_wordset(db, description='Test')

        response = self.client.get('/wordsets')
        descriptions = [ws['description'] for ws in response.get_json()['data']]
        self.assertNotIn('Test', descriptions)

    def test_get_wordsets_does_not_sweep_up_the_test_suites_own_fixtures(self):
        """THE control. TestUtils.create_test_wordset's default description
        is 'Test Wordset' -- an exact-match denylist on 'test' must not
        also exclude it, or this fix would silently break every other test
        in the suite that relies on the default fixture name being visible
        via this endpoint."""
        with self.app.app_context():
            TestUtils.create_test_wordset(db)  # default description="Test Wordset"

        response = self.client.get('/wordsets')
        descriptions = [ws['description'] for ws in response.get_json()['data']]
        self.assertIn('Test Wordset', descriptions)


if __name__ == '__main__':
    unittest.main()
