import unittest
from unittest.mock import patch
from flask import jsonify, request
from app.auth import authenticate_user, default_mock_user
from app.config import Config
from tests.utils import TestUtils
import os

class TestAuthenticateUser(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up the test app and client."""
        cls.client, cls.app, cls.temp_db_name = TestUtils.setup_test_app()

        # Define a protected route in the app for all tests
        @cls.app.route('/protected', methods=['GET'])
        @authenticate_user
        def protected_route():
            return jsonify({"email": request.user['email']})

    @classmethod
    def tearDownClass(cls):
        """Tear down the test database."""
        TestUtils.teardown_test_db(cls.temp_db_name)

    def setUp(self):
        """Initialize default headers."""
        self.headers = {}

    def test_test_mode_with_authorization_header(self):
        """Test that in test mode, user is set from Authorization header."""
        # Simulate test mode and set the Authorization header
        os.environ['TESTING'] = 'True'
        TestUtils.mock_auth_header(self.headers, email='testuser@example.com')

        # Call the protected route
        response = self.client.get('/protected', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'testuser@example.com', response.data)

    def test_test_mode_without_authorization_header(self):
        """Test that in test mode, user is set to default mock user when no Authorization header is provided."""
        os.environ['TESTING'] = 'True'  # Simulate test mode

        # Call the protected route without setting the Authorization header
        response = self.client.get('/protected')
        self.assertEqual(response.status_code, 200)
        self.assertIn(default_mock_user.encode(), response.data)

    def test_missing_token_in_non_test_mode(self):
        """Test that in non-test mode, missing token results in 401 error."""
        os.environ['TESTING'] = 'False'  # Simulate non-test mode

        # Call the protected route without a token
        response = self.client.get('/protected')
        self.assertEqual(response.status_code, 401)
        self.assertIn(b'Missing token', response.data)

    def test_invalid_token_format(self):
        """Test that in non-test mode, an invalid token format returns 401 error."""
        os.environ['TESTING'] = 'False'  # Simulate non-test mode

        # Set an invalid Authorization header format
        self.headers['Authorization'] = 'InvalidFormat'
        response = self.client.get('/protected', headers=self.headers)
        self.assertEqual(response.status_code, 401)
        self.assertIn(b'Invalid token format', response.data)

    @patch('requests.get')
    def test_valid_token(self, mock_get):
        """Test that in non-test mode, a valid token sets request.user properly."""
        os.environ['TESTING'] = 'False'  # Simulate non-test mode

        # Mock a valid token verification
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            'email': 'validuser@example.com',
            'issued_to': Config.GOOGLE_CLIENT_ID
        }
        TestUtils.mock_auth_header(self.headers, 'valid_token')

        # Call the protected route with the mocked token
        response = self.client.get('/protected', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'validuser@example.com', response.data)

    @patch('requests.get')
    def test_invalid_token(self, mock_get):
        """Test that an invalid token returns a 401 response."""
        os.environ['TESTING'] = 'False'  # Simulate non-test mode

        # Mock token verification to return an invalid response
        mock_get.return_value.status_code = 400
        TestUtils.mock_auth_header(self.headers, 'invalid_token')

        # Call the protected route with the mocked invalid token
        response = self.client.get('/protected', headers=self.headers)
        self.assertEqual(response.status_code, 401)
        self.assertIn(b'Invalid access token', response.data)

    def test_guest_token_demo_domain_allowed(self):
        """A guest UNAUTH_USER token on the demo domain is accepted without Google validation."""
        os.environ['TESTING'] = 'False'  # Simulate non-test mode

        demo_email = f'abc12@{Config.DEMO_EMAIL_DOMAIN}'
        self.headers['Authorization'] = f'Bearer UNAUTH_USER:{demo_email}'
        response = self.client.get('/protected', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn(demo_email.encode(), response.data)

    def test_guest_token_real_email_rejected(self):
        """A guest UNAUTH_USER token spoofing a real (non-demo) email is rejected with 401."""
        os.environ['TESTING'] = 'False'  # Simulate non-test mode

        self.headers['Authorization'] = 'Bearer UNAUTH_USER:victim@gmail.com'
        response = self.client.get('/protected', headers=self.headers)
        self.assertEqual(response.status_code, 401)
        self.assertIn(b'Invalid guest token', response.data)

if __name__ == '__main__':
    unittest.main()
