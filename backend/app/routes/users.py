from os import abort
from flask import Blueprint, request, jsonify, abort
from ..models import db, User, UserWord, RecallHistory
from app.auth import authenticate_user, is_demo_email  # Import from auth.py
from ..utils import validate_user_access, error_response  # Import the shared validation function
import logging

bp = Blueprint('users', __name__, url_prefix='/users')

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

@bp.route('', methods=['POST'])
@authenticate_user  # Ensure only authenticated users can create themselves
def create_user():
    try:
        data = request.json

        # Ensure the authenticated user is creating themselves
        authenticated_email = request.user['email']  # Comes from the Google token
        if authenticated_email != data['email']:
            return jsonify({"message": "Unauthorized: You can only create yourself"}), 403

        # Check if the user already exists
        existing_user = User.query.filter_by(email=data['email']).first()
        if existing_user:
            return jsonify({"message": "User already exists"}), 200

        # Create the user
        user = User(email=data['email'])
        db.session.add(user)
        db.session.commit()
        return jsonify({"message": "User created successfully"}), 201
    except Exception as e:
        logger.error(f"Error create_user: {e}", exc_info=True)
        return error_response(str(e), 500) 

@bp.route('/<email>', methods=['GET'], endpoint='get_user')
@authenticate_user
def get_user(email):
    try:
        # Use the shared validation function
        validation_response = validate_user_access(email)
        if validation_response:
            return validation_response

        user = db.session.get(User, email)
        if user is None:
            return jsonify({"message": "User not found", "email": email}), 404
        return jsonify({"email": user.email})
    except Exception as e:
        logger.error(f"Error get_user: {e}", exc_info=True)
        return error_response(str(e), 500) 

@bp.route('/<email>', methods=['PUT'])
@authenticate_user
def update_user(email):
    try:
        # Use the shared validation function
        validation_response = validate_user_access(email)
        if validation_response:
            return validation_response

        user = db.session.get(User, email)
        if user is None:
            return jsonify({"message": "User not found", "email": email}), 404
        data = request.json
        user.email = data['email']
        db.session.commit()
        return jsonify({"message": "User updated successfully"})
    except Exception as e:
        logger.error(f"Error get_user: {e}", exc_info=True)
        return error_response(str(e), 500) 

@bp.route('/<email>', methods=['DELETE'])
@authenticate_user
def delete_user(email):
    try:
        # Use the shared validation function
        validation_response = validate_user_access(email)
        if validation_response:
            return validation_response

        user = db.session.get(User, email)
        if user is None:
            return jsonify({"message": "User not found", "email": email}), 404
        db.session.delete(user)
        db.session.commit()
        return jsonify({"message": "User deleted successfully"})
    except Exception as e:
        logger.error(f"Error get_user: {e}", exc_info=True)
        return error_response(str(e), 500) 


@bp.route('/migrate', methods=['POST'])
@authenticate_user
def migrate_user():
    """Move a guest (demo) session's progress onto the now-authenticated member.

    Called once, right after a real Google sign-in, when the user had been
    practicing as a guest. Target is always the authenticated caller — the demo
    account is supplied in the body — so a caller can only migrate INTO
    themselves, never harvest another member's data."""
    try:
        data = request.json or {}
        from_email = data.get('from_email')
        to_email = request.user['email']  # authenticated real member

        if not from_email:
            return jsonify({"message": "from_email is required"}), 400
        # Only a guest/demo session may be migrated, and only into a real member.
        if not is_demo_email(from_email):
            return jsonify({"message": "from_email must be a guest/demo account"}), 400
        if is_demo_email(to_email):
            return jsonify({"message": "Cannot migrate into a guest account"}), 400
        if from_email == to_email:
            return jsonify({"message": "from_email and target are the same"}), 400

        from_user = db.session.get(User, from_email)
        if from_user is None:
            # Nothing to migrate — idempotent no-op (e.g. already migrated).
            return jsonify({"message": "No demo data to migrate", "migrated_words": 0}), 200

        # Ensure the target member row exists before we re-point rows onto it.
        if db.session.get(User, to_email) is None:
            db.session.add(User(email=to_email))
            db.session.flush()

        # word_ids the member already owns — re-pointing onto these would violate
        # UNIQUE(user_id, word_id) on userwords, so keep the member's own progress.
        existing_word_ids = {
            uw.word_id for uw in UserWord.query.filter_by(user_id=to_email).all()
        }

        migrated = 0
        for uw in UserWord.query.filter_by(user_id=from_email).all():
            if uw.word_id in existing_word_ids:
                continue
            uw.user_id = to_email
            migrated += 1
        # Force the user_id UPDATEs out before the demo user is deleted, so the
        # ON DELETE CASCADE does not sweep up the rows we just re-pointed.
        db.session.flush()

        # recall_history is an append-only log with no uniqueness — re-point all.
        RecallHistory.query.filter_by(user_id=from_email).update(
            {RecallHistory.user_id: to_email}, synchronize_session=False
        )

        # Any userwords still on the demo account (the conflicting ones) cascade away.
        db.session.delete(from_user)
        db.session.commit()

        return jsonify({"message": "Migration complete", "migrated_words": migrated}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error migrate_user: {e}", exc_info=True)
        return error_response(str(e), 500)


@bp.route('', methods=['GET'])
@authenticate_user
def get_users():
    try:
        users = User.query.all()
        return jsonify([{"email": user.email} for user in users])
    except Exception as e:
        logger.error(f"Error get_user: {e}", exc_info=True)
        return error_response(str(e), 500) 
