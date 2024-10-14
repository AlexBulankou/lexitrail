from flask import Blueprint, request
from ..models import Word, Wordset
from ..utils import to_dict, success_response, error_response, not_found_response
import logging

bp = Blueprint('words', __name__, url_prefix='/wordsets/<int:wordset_id>/words')
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

@bp.route('', methods=['GET'])
def get_words_by_wordset(wordset_id):
    try:
        wordset = db.session.get(Wordset, wordset_id)
        if not wordset:
            return not_found_response("Wordset not found")
        words = Word.query.filter_by(wordset_id=wordset_id).all()
        words_data = [to_dict(word) for word in words]
        return success_response(words_data)
    except Exception as e:
        logger.error(f"Error get_words_by_wordset: {e}", exc_info=True)
        return error_response(str(e), 500)
