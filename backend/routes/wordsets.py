from flask import Blueprint
from ..models import Wordset
from ..utils import to_dict, success_response, error_response

bp = Blueprint('wordsets', __name__, url_prefix='/wordsets')

@bp.route('', methods=['GET'])
def get_all_wordsets():
    try:
        wordsets = Wordset.query.all()
        wordsets_data = [to_dict(ws) for ws in wordsets]
        return success_response(wordsets_data)
    except Exception as e:
        return error_response(str(e), 500)
