import unittest
from tests.utils import TestUtils
from app.auth import default_mock_user
from app import db
from app.models import User, UserWord

class UserTests(unittest.TestCase):

    temp_db_name = ''

    @classmethod
    def setUpClass(cls):
        cls.client, cls.app, cls.temp_db_name = TestUtils.setup_test_app()

    @classmethod
    def tearDownClass(cls):
        TestUtils.teardown_test_db(cls.temp_db_name)
    
    def setUp(self):
        """Set up default mock Authorization header."""
        self.headers = {}

    def test_create_user(self):
        response = TestUtils.authenticate_and_create_user(self.client, default_mock_user)
        self.assertEqual(response.status_code, 201)
        self.assertIn(b'User created successfully', response.data)

    def test_get_user(self):
        TestUtils.authenticate_and_create_user(self.client, 'user1@example.com')  # Create user
        TestUtils.mock_auth_header(self.headers, 'user1@example.com')  # Mock auth header

        response = self.client.get('/users/user1@example.com', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'user1@example.com', response.data)

    def test_update_user(self):
        TestUtils.authenticate_and_create_user(self.client, 'user2@example.com')  # Create user
        TestUtils.mock_auth_header(self.headers, 'user2@example.com')  # Mock auth header

        response = self.client.put('/users/user2@example.com', json={'email': 'newemail@example.com'}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'User updated successfully', response.data)

    def test_delete_user(self):
        TestUtils.authenticate_and_create_user(self.client, 'user3@example.com')  # Create user
        TestUtils.mock_auth_header(self.headers, 'user3@example.com')  # Mock auth header

        response = self.client.delete('/users/user3@example.com', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'User deleted successfully', response.data)

    def test_get_users(self):
        """This might be failing because the GET /users route is missing."""
        TestUtils.authenticate_and_create_user(self.client, default_mock_user)  # Create user
        TestUtils.mock_auth_header(self.headers, default_mock_user)  # Mock auth header

        response = self.client.get('/users', headers=self.headers)
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_user_access(self):
        """Test that unauthenticated users can access endpoints with special token format."""
        test_email = 'unauthenticated@example.com'
        TestUtils.mock_unauth_header(self.headers, test_email)

        # Test user creation
        response = self.client.post('/users', 
            json={
                'email': test_email,
                'name': 'Test User',
                'picture': 'https://example.com/picture.jpg'
            },
            headers=self.headers
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn(b'User created successfully', response.data)

        # Test user retrieval
        response = self.client.get(f'/users/{test_email}', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn(test_email.encode(), response.data)

class UserMigrationTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client, cls.app, cls.temp_db_name = TestUtils.setup_test_app()

    @classmethod
    def tearDownClass(cls):
        TestUtils.teardown_test_db(cls.temp_db_name)

    def setUp(self):
        self.headers = {}
        with self.app.app_context():
            TestUtils.clear_database(db)

    def test_migrate_demo_progress_to_member(self):
        """A guest's practiced word is re-pointed to the member, demo user deleted."""
        demo_email = 'guest99@lexitrail.demo'
        member_email = 'member@example.com'

        with self.app.app_context():
            TestUtils.create_test_userword(db, user_email=demo_email, word_name='alpha')

        TestUtils.mock_auth_header(self.headers, member_email)
        response = self.client.post('/users/migrate', json={'from_email': demo_email}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['migrated_words'], 1)

        with self.app.app_context():
            self.assertIsNone(db.session.get(User, demo_email))
            self.assertIsNotNone(db.session.get(User, member_email))
            member_words = UserWord.query.filter_by(user_id=member_email).all()
            self.assertEqual(len(member_words), 1)

    def test_migrate_noop_when_no_demo_data(self):
        """Migrating a demo account that has no row is an idempotent no-op."""
        TestUtils.mock_auth_header(self.headers, 'member2@example.com')
        response = self.client.post('/users/migrate', json={'from_email': 'ghost@lexitrail.demo'}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['migrated_words'], 0)

    def test_migrate_rejects_non_demo_source(self):
        """from_email must be a guest/demo account — a real email is rejected."""
        TestUtils.mock_auth_header(self.headers, 'member@example.com')
        response = self.client.post('/users/migrate', json={'from_email': 'someoneelse@gmail.com'}, headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_migrate_rejects_demo_target(self):
        """A guest caller cannot be a migration target."""
        TestUtils.mock_unauth_header(self.headers, 'guest2@lexitrail.demo')
        response = self.client.post('/users/migrate', json={'from_email': 'guest3@lexitrail.demo'}, headers=self.headers)
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
