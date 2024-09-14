from flask import Blueprint, request
from ..models import db, UserWord, RecallHistory, Word
from ..utils import to_dict, success_response, error_response, not_found_response
from datetime import datetime
import logging

bp = Blueprint('userwords', __name__, url_prefix='/userwords')

@bp.route('/query', methods=['GET'])
def get_userwords_by_user_and_wordset():
    """
    Retrieve all userwords for a given user and wordset.
    Expects 'user_id' and 'wordset_id' as query parameters.
    """
    user_id = request.args.get('user_id')
    wordset_id = request.args.get('wordset_id')
    
    if not user_id or not wordset_id:
        return error_response("Missing 'user_id' or 'wordset_id' query parameters", 400)
    
    try:
        userwords = UserWord.query.join(UserWord.word).filter(
            UserWord.user_id == user_id,
            Word.wordset_id == wordset_id
        ).all()
        userwords_data = [to_dict(uw) for uw in userwords]
        return success_response(userwords_data)
    except Exception as e:
        return error_response(str(e), 500)

@bp.route('/<string:user_id>/<int:word_id>/recall', methods=['PUT'])
def update_recall_state(user_id, word_id):
    """
    Update or create a userword entry and update recall state, recall (boolean), and is_included.
    Also updates RecallHistory accordingly.
    Expects JSON payload with 'recall', 'recall_state', and 'is_included' (all required).
    """
    data = request.json
    new_recall_state = data.get('recall_state')
    recall = data.get('recall')
    is_included = data.get('is_included')
    userword_entry_exists = False

    # Validate input fields
    if new_recall_state is None or recall is None or is_included is None:
        return error_response("Missing 'recall', 'recall_state', or 'is_included' in request body", 400)

    try:
        # Fetch or create a UserWord entry
        userword = UserWord.query.filter_by(user_id=user_id, word_id=word_id).first()
        if not userword:
            # Create a new UserWord entry if it does not exist
            userword = UserWord(
                user_id=user_id,
                word_id=word_id,
                is_included=is_included,
                recall_state=new_recall_state,
                is_included_change_time=datetime.utcnow()  # Set change time for new entries
            )
            db.session.add(userword)
        else:
            userword_entry_exists = True
            # Check if is_included value has changed
            if userword.is_included != is_included:
                userword.is_included = is_included
                userword.is_included_change_time = datetime.utcnow()  # Update change time only when changed

            # Update other fields
            userword.last_recall = recall
            userword.last_recall_time = datetime.utcnow()
            old_recall_state = userword.recall_state
            userword.recall_state = new_recall_state

        db.session.commit()

        # Add entry to RecallHistory (Always created)
        recall_history = RecallHistory(
            user_id=user_id,
            word_id=word_id,
            recall=recall,  # Read the recall value from the request
            recall_time=datetime.utcnow(),
            new_recall_state=new_recall_state,
            old_recall_state=old_recall_state if userword_entry_exists else None,
            is_included=is_included  # Save is_included in RecallHistory
        )
        db.session.add(recall_history)
        db.session.commit()

        return success_response(to_dict(userword), "Recall state and recall updated successfully")

    except Exception as e:
        # Log the error with details for debugging
        logging.error(f"Error occurred while updating recall state: {e}")
        return error_response(f"An error occurred: {str(e)}", 500)

