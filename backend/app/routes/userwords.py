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

@bp.route('/<int:userword_id>/recall', methods=['PUT'])
def update_recall_state(userword_id):
    """
    Update recall state and recall (boolean) for a specific userword.
    Also updates RecallHistory accordingly.
    Expects JSON payload with 'recall' (boolean) and 'recall_state' (integer).
    """
    data = request.json
    new_recall_state = data.get('recall_state')
    recall = data.get('recall')

    # Validate input
    if new_recall_state is None or recall is None:
        return error_response("Missing 'recall' or 'recall_state' in request body", 400)
    
    try:
        userword = UserWord.query.get(userword_id)
        if not userword:
            return not_found_response("UserWord not found")
        
        # Update UserWord fields
        userword.last_recall = recall
        userword.last_recall_time = datetime.utcnow()
        old_recall_state = userword.recall_state
        userword.recall_state = new_recall_state
        db.session.commit()

        # Add entry to RecallHistory
        recall_history = RecallHistory(
            user_id=userword.user_id,
            word_id=userword.word_id,
            recall=recall,  # Read the recall value from the request
            recall_time=datetime.utcnow(),
            new_recall_state=new_recall_state,
            old_recall_state=old_recall_state
        )
        db.session.add(recall_history)
        db.session.commit()
        
        return success_response(to_dict(userword), "Recall state and recall updated successfully")
    except Exception as e:
        # Log the error with details
        logging.error(f"Error occurred while updating recall state: {e}")
        return error_response(f"An error occurred: {str(e)}", 500)
