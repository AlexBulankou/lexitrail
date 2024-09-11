import unittest
from tests.utils import TestUtils

class WordsetTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client, cls.app = TestUtils.setup_test_app()

    @classmethod
    def tearDownClass(cls):
        TestUtils.teardown_test_db(cls.app)

    def test_get_wordsets(self):
        response = self.client.get('/wordsets')
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
