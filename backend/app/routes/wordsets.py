from flask import Blueprint, jsonify
from ..models import Wordset, Word
from ..utils import to_dict, success_response, error_response
from app import db  # Import the db object

bp = Blueprint('wordsets', __name__, url_prefix='/wordsets')

@bp.route('', methods=['GET'])
def get_all_wordsets():
    """Fetch all wordsets."""
    try:
        wordsets = Wordset.query.all()
        wordsets_data = [to_dict(ws) for ws in wordsets]
        return success_response(wordsets_data)
    except Exception as e:
        return error_response(str(e), 500)

@bp.route('/<int:wordset_id>/words', methods=['GET'])
def get_words_by_wordset(wordset_id):
    """Fetch words by wordset."""
    try:
        # Fetch the wordset by ID
        wordset = db.session.get(Wordset, wordset_id)
        if not wordset:
            return error_response('Wordset not found', 404)

        # Query words that belong to this wordset
        words = Word.query.filter_by(wordset_id=wordset_id).all()
        words_data = [to_dict(word) for word in words]
        
        return success_response(words_data)
    except Exception as e:
        return error_response(f"Error fetching words: {str(e)}", 500)
