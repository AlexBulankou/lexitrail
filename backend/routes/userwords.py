from flask import Blueprint, request
from ..models import db, UserWord, RecallHistory
from ..utils import to_dict, success_response, error_response, not_found_response
from datetime import datetime

bp = Blueprint('userwords', __name__, url_prefix='/userwords')

# Existing CRUD operations can be omitted as per user's earlier request,
# but since user wants additional functionalities, we implement those.

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
    Update recall state for a specific userword.
    Also updates RecallHistory accordingly.
    Expects JSON payload with 'recall_state'.
    """
    data = request.json
    new_recall_state = data.get('recall_state')
    
    if new_recall_state is None:
        return error_response("Missing 'recall_state' in request body", 400)
    
    try:
        userword = UserWord.query.get((user_id, word_id))
        if not userword:
            return not_found_response("UserWord not found")
        
        # Update UserWord fields
        userword.last_recall = datetime.utcnow()
        userword.last_recall_time = datetime.utcnow()
        old_recall_state = userword.recall_state
        userword.recall_state = new_recall_state
        db.session.commit()
        
        # Add entry to RecallHistory
        recall_history = RecallHistory(
            user_id=user_id,
            word_id=word_id,
            recall=True,  # Assuming 'recall' is True when updating
            recall_time=datetime.utcnow(),
            new_recall_state=new_recall_state,
            old_recall_state=old_recall_state
        )
        db.session.add(recall_history)
        db.session.commit()
        
        return success_response(to_dict(userword), "Recall state updated successfully")
    except Exception as e:
        return error_response(str(e), 500)
