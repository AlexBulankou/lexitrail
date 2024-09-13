import unittest
from tests.utils import TestUtils

class UserTests(unittest.TestCase):

    temp_db_name=''

    @classmethod
    def setUpClass(cls):
        cls.client, cls.app, cls.temp_db_name = TestUtils.setup_test_app()

    @classmethod
    def tearDownClass(cls):
        TestUtils.teardown_test_db(cls.app, cls.temp_db_name)
        
    def test_create_user(self):
        response = self.client.post('/users', json={'email': 'test@example.com'})
        self.assertEqual(response.status_code, 201)
        self.assertIn(b'User created successfully', response.data)

    def test_get_users(self):
        response = self.client.get('/users')
        self.assertEqual(response.status_code, 200)

    def test_get_user(self):
        self.client.post('/users', json={'email': 'user1@example.com'})
        response = self.client.get('/users/user1@example.com')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'user1@example.com', response.data)

    def test_update_user(self):
        self.client.post('/users', json={'email': 'user2@example.com'})
        response = self.client.put('/users/user2@example.com', json={'email': 'newemail@example.com'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'User updated successfully', response.data)

    def test_delete_user(self):
        self.client.post('/users', json={'email': 'user3@example.com'})
        response = self.client.delete('/users/user3@example.com')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'User deleted successfully', response.data)

if __name__ == '__main__':
    unittest.main()
