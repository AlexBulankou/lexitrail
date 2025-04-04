from flask import Blueprint, request
from ..models import db, UserWord, RecallHistory, Word
from ..utils import to_dict, success_response, error_response, not_found_response
from datetime import datetime
import logging
from ..utils import validate_user_access  # Import the shared validation function
from app.auth import authenticate_user  # Import from auth.py
import time

bp = Blueprint('userwords', __name__, url_prefix='/userwords')

logger = logging.getLogger(__name__)

@bp.route('/query', methods=['GET'])
@authenticate_user  # Protect this route
def get_userwords_by_user_and_wordset():
    """
    Retrieve all userwords for a given user and wordset.
    Expects 'user_id' and 'wordset_id' as query parameters.
    """
    user_id = request.args.get('user_id')
    wordset_id = request.args.get('wordset_id')
    
    if not user_id or not wordset_id:
        return error_response("Missing 'user_id' or 'wordset_id' query parameters", 400)
    
    # Use the shared validation function
    validation_response = validate_user_access(user_id)
    if validation_response:
        return validation_response
    
    try:
        # Create a subquery to get the latest 3 recall histories per word
        recall_subquery = (
            db.session.query(
                RecallHistory.user_id,
                RecallHistory.word_id,
                RecallHistory.recall,
                RecallHistory.recall_time,
                RecallHistory.new_recall_state,
                RecallHistory.old_recall_state,
                db.func.row_number().over(
                    partition_by=(RecallHistory.user_id, RecallHistory.word_id),
                    order_by=RecallHistory.recall_time.desc()
                ).label('rn')
            ).subquery()
        )

        # Main query joining UserWord with the recall histories
        query = (
            db.session.query(
                UserWord.user_id,
                UserWord.word_id,
                UserWord.is_included,
                UserWord.recall_state,
                recall_subquery.c.recall,
                recall_subquery.c.recall_time,
                recall_subquery.c.new_recall_state,
                recall_subquery.c.old_recall_state
            )
            .join(Word, UserWord.word_id == Word.word_id)
            .outerjoin(
                recall_subquery,
                db.and_(
                    UserWord.user_id == recall_subquery.c.user_id,
                    UserWord.word_id == recall_subquery.c.word_id,
                    recall_subquery.c.rn <= 3
                )
            )
            .filter(
                UserWord.user_id == user_id,
                Word.wordset_id == wordset_id
            )
            .order_by(UserWord.word_id, recall_subquery.c.recall_time.desc())
        )

        # Get the SQL query as string
        sql_query = str(query.statement.compile(compile_kwargs={"literal_binds": True}))
        
        # Execute query with timing
        start_time = time.time()
        results = query.all()
        query_time_ms = (time.time() - start_time) * 1000  # Convert to milliseconds

        # Process results into the desired format
        userwords_data = {}
        for result in results:
            word_id = result.word_id
            if word_id not in userwords_data:
                userwords_data[word_id] = {
                    'user_id': result.user_id,
                    'word_id': word_id,
                    'is_included': result.is_included,
                    'recall_state': result.recall_state,
                    'recall_histories': []
                }
            
            if result.recall_time:  # Only add recall history if it exists
                userwords_data[word_id]['recall_histories'].append({
                    'recall': result.recall,
                    'recall_time': result.recall_time,
                    'new_recall_state': result.new_recall_state,
                    'old_recall_state': result.old_recall_state,
                    'is_included': result.is_included
                })

        return success_response(
            data=list(userwords_data.values()),
            query_metadata={
                "sql_query": sql_query,
                "execution_time_ms": round(query_time_ms, 2)
            }
        )

    except Exception as e:
        logger.error(f"Error retrieving userwords: {e}", exc_info=True)
        return error_response(str(e), 500)


@bp.route('/<string:user_id>/<int:word_id>/recall', methods=['PUT'])
@authenticate_user  # Protect this route
def update_recall_state(user_id, word_id):
    """
    Update or create a userword entry and update recall state, recall (boolean), and is_included.
    Also updates RecallHistory accordingly.
    Expects JSON payload with 'recall', 'recall_state', and 'is_included' (all required).
    """
    # Use the shared validation function
    validation_response = validate_user_access(user_id)
    if validation_response:
        return validation_response
    
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
        logging.error(f"Error occurred while updating recall state: {e}", exc_info=True)
        return error_response(f"An error occurred: {str(e)}", 500)

