import os
from flask import request, jsonify
import requests as req
from app.config import Config
import functools
import logging

logger = logging.getLogger(__name__)

default_mock_user = "test@example.com"


def is_demo_email(email):
    """A guest (UNAUTH_USER) token is only valid for the demo domain, so it can
    never impersonate a real member. Match case-insensitively on the exact
    domain suffix."""
    if not email or '@' not in email:
        return False
    return email.rsplit('@', 1)[1].lower() == Config.DEMO_EMAIL_DOMAIN.lower()

def authenticate_user(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if os.getenv('TESTING') == 'True':
            # If in test mode, mock the user info
            token = request.headers.get('Authorization')
            if token:
                parts = token.split(' ')
                if len(parts) == 2 and parts[0] == 'Bearer':
                    access_token = parts[1]
                    # Handle test token format
                    if access_token.startswith('test_token_'):
                        email = access_token.replace('test_token_', '')
                        request.user = {"email": email}
                    # Handle unauth token format (TESTING mock — trusts the header;
                    # the real demo-domain guard is enforced on the prod path below)
                    elif access_token.startswith('UNAUTH_USER:'):
                        email = access_token.split('UNAUTH_USER:')[1]
                        request.user = {"email": email}
                    else:
                        request.user = {"email": access_token}  # Fallback
            else:
                request.user = {"email": default_mock_user}  # Default mock user in test mode
            return func(*args, **kwargs)

        # Extract the token from the Authorization header
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({"message": "Missing token"}), 401

        try:
            parts = token.split(' ')
            if len(parts) != 2 or parts[0] != 'Bearer':
                return jsonify({"message": "Invalid token format"}), 401

            access_token = parts[1]
            
            # Check for unauthenticated user token format
            if access_token.startswith('UNAUTH_USER:'):
                email = access_token.split('UNAUTH_USER:')[1]
                if not is_demo_email(email):
                    return jsonify({"message": "Invalid guest token"}), 401
                request.user = {"email": email}
                return func(*args, **kwargs)

            # Regular Google token validation
            google_url = f"https://www.googleapis.com/oauth2/v1/tokeninfo?access_token={access_token}"
            response = req.get(google_url)
            print (response)

            if response.status_code != 200:
                return jsonify({"message": "Invalid access token"}), 401

            idinfo = response.json()
            issued_to = idinfo.get('issued_to')

            # Check if the token matches the expected client_id
            if issued_to != Config.GOOGLE_CLIENT_ID:
                return jsonify({"message": 
                                f"Token's client ID: {issued_to} does not match app's client ID {Config.GOOGLE_CLIENT_ID}. More: {str(idinfo)}"}), 401

            # Set the user info on the request
            request.user = {"email": idinfo.get('email')}
            return func(*args, **kwargs)

        except Exception as e:
            logger.error(f"Error authenticate_user: {e}", exc_info=True)
            return jsonify({"message": "Error verifying access token", "error": str(e)}), 401

    return wrapper
