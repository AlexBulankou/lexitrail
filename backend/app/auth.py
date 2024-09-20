import os
from flask import request, jsonify
from google.oauth2 import id_token
from google.auth.transport import requests
from app.config import Config
import functools

default_mock_user = "test@example.com"

def authenticate_user(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if os.getenv('TESTING') == 'True':
            # If in test mode, extract the email from the Authorization header
            token = request.headers.get('Authorization')
            if token:
                parts = token.split(' ')
                if len(parts) == 2 and parts[0] == 'Bearer':
                    # In test mode, treat the token part as the email address
                    email = parts[1]
                    request.user = {"email": email}  # Mock user info for testing
            else:
                # Default to the mock email if no Authorization header is present
                request.user = {"email": default_mock_user}  # Default mock user
            return func(*args, **kwargs)

        # Extract the token from the Authorization header in non-test mode
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({"message": "Missing token"}), 401

        try:
            # Split the token, ensuring it follows the 'Bearer <token>' format
            parts = token.split(' ')
            if len(parts) != 2 or parts[0] != 'Bearer':
                return jsonify({"message": "Invalid token format"}), 401

            token = parts[1]  # Extract the actual token
            idinfo = id_token.verify_oauth2_token(token, requests.Request(), Config.GOOGLE_CLIENT_ID)

            # Set the user info on the request
            request.user = idinfo
            return func(*args, **kwargs)

        except ValueError:
            return jsonify({"message": "Invalid token"}), 401

    return wrapper
