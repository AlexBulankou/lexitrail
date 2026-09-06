from flask import Blueprint, request
from ..models import db, UserWord, RecallHistory, Word
from ..utils import to_dict, success_response, error_response, not_found_response
from datetime import datetime, timedelta
import logging
from ..utils import validate_user_access  # Import the shared validation function
from ..recall_policy import is_recall_event, recall_provenance
from ..srs_ladder import distinct_state_intervals, interval_days
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
                RecallHistory.provenance,
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
                recall_subquery.c.old_recall_state,
                recall_subquery.c.provenance
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
                    'is_included': result.is_included,
                    # #109: 'single' | 'bulk' | None. A consumer that cannot see
                    # this cannot tell earned mastery from a bulk tap, which is
                    # the whole point -- so it ships with the write, not later.
                    'provenance': result.provenance
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


@bp.route('/due-counts', methods=['GET'])
@authenticate_user
def get_due_counts():
    """Per-wordset count of words DUE today, for one user. issue-384.

    ## Why this exists

    The Today home needs one integer per wordset. It used to get them by asking
    `/userwords/query` once per wordset -- seven concurrent requests, each
    returning every word in the set with up to three recall-history rows, then
    counting in the browser. ~5,600 words and ~16,000 rows of work to render
    seven numbers. Measured user-visible result: 10s+, then an outright failure
    ("Couldn't load today's reviews"), because the whole screen is a
    `Promise.all` and one slow set fails all of them.

    This returns the seven integers. It is fast BY CONSTRUCTION rather than by
    optimisation: the response does not grow with the size of the set, so it
    cannot regress back into the same shape as the sets grow.

    ## The due rule, and where it is defined

    `ui/src/utils/srs.js` remains the system of record for what "due" means.
    Only the interval LADDER is mirrored here (`srs_ladder.py`), pinned rung for
    rung by `test_srs_ladder_parity.py` against the actual arrays in that file.
    The rest of the rule is expressed directly in the query:

      * a word must be INCLUDED                     (`isWordDue`'s first line)
      * a word never practised is DUE               (`isDue`'s null branch)
      * otherwise DUE once its interval has elapsed since the MOST RECENT review

    "Most recent" is `MAX(recall_time)`, matching `lastRecallTimeOf`, which
    scans for the max rather than trusting order -- nothing sorts the history.

    ## One clock

    `now` is read ONCE and every cutoff derived from it, for the same reason
    `dueByWordset` threads a single `now` through every word: a clock read per
    row could count two words on the same rung against different instants, and
    the total would then correspond to no single moment.
    """
    user_id = request.args.get('user_id')
    if not user_id:
        return error_response("Missing 'user_id' query parameter", 400)

    validation_response = validate_user_access(user_id)
    if validation_response:
        return validation_response

    try:
        now = datetime.utcnow()

        # The most recent review per word, for THIS user only.
        #
        # The filter is on the inside on purpose. `/userwords/query` builds a
        # `row_number() OVER (PARTITION BY user_id, word_id)` with no WHERE at
        # all, so every request ranks the entire recall_history table before
        # anything is discarded -- seven times per page load. Here the user
        # predicate is applied before the aggregate, and MAX is all the Today
        # count needs; the ranked top-3 exists for the practice screen, which
        # genuinely uses the last three answers.
        latest = (
            db.session.query(
                RecallHistory.word_id.label('word_id'),
                db.func.max(RecallHistory.recall_time).label('last_time'),
            )
            .filter(RecallHistory.user_id == user_id)
            .group_by(RecallHistory.word_id)
            .subquery()
        )

        # `recall_state` NULL is state 0, matching srs.js's `recallState | 0`.
        state = db.func.coalesce(UserWord.recall_state, 0)

        # One OR-arm per rung, with the cutoff datetime computed in PYTHON
        # rather than as SQL date arithmetic -- portable across the sqlite the
        # tests run on and the MySQL production uses, and it keeps the single
        # `now` above authoritative instead of letting the database read its
        # own clock mid-statement.
        rungs = distinct_state_intervals()
        lo_state, hi_state = rungs[0][0], rungs[-1][0]
        arms = [latest.c.last_time.is_(None)]  # never practised -> always due
        for st, days in rungs:
            cutoff = now - timedelta(days=days)
            if st == lo_state:
                pred = state <= st          # saturated end of the graduation ladder
            elif st == hi_state:
                pred = state >= st          # saturated end of the learning ladder
            else:
                pred = state == st
            arms.append(db.and_(pred, latest.c.last_time <= cutoff))

        rows = (
            db.session.query(
                Word.wordset_id.label('wordset_id'),
                db.func.count(db.distinct(UserWord.word_id)).label('due'),
            )
            .join(Word, UserWord.word_id == Word.word_id)
            .outerjoin(latest, latest.c.word_id == UserWord.word_id)
            .filter(
                UserWord.user_id == user_id,
                UserWord.is_included.is_(True),
                db.or_(*arms),
            )
            .group_by(Word.wordset_id)
            .all()
        )

        # Wordsets with nothing due are ABSENT from a GROUP BY, and the caller
        # must not read absence as "no such set". Returning the counted sets
        # only, with the caller defaulting to 0, keeps that explicit -- the
        # alternative (a row per wordset) would need a second query for sets the
        # user has no rows in at all, to say the same thing.
        return success_response(
            data=[{'wordset_id': r.wordset_id, 'due': int(r.due)} for r in rows],
            query_metadata={'as_of': now.isoformat() + 'Z'},
        )

    except Exception as e:
        logger.error(f"Error computing due counts: {e}", exc_info=True)
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
    # #111: the caller asserts this call is an inclusion change, NOT a recall
    # event. Defaults False, so every existing caller (and an older UI talking
    # to a newer backend) behaves exactly as before.
    #
    # WHY THE CALLER DECIDES rather than the server inferring it: the server
    # could guess from "recall_state did not move", but a genuine recall that
    # happens not to change the state (already floored at 0 and answered
    # correctly) looks identical. That heuristic would silently drop real
    # recalls, which is a worse failure than the one being fixed.
    record_history = is_recall_event(data)
    # #109 (RD-6): the caller declares HOW this recall was produced. Absent or
    # unrecognised -> None (unknown), never 'single' -- see recall_policy.
    provenance = recall_provenance(data)
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

        # Add entry to RecallHistory -- unless the caller says this was not a
        # recall (#111).
        #
        # THE BUG THIS CLOSES: `toggleExclusion` reuses this endpoint, passing
        # `recall=False` because the signature demands a value. The row was
        # written unconditionally, and `historyTiles.js` renders every row as
        # `correct: Boolean(r.recall)` -- so excluding a word painted a RED
        # tile on its history, indistinguishable from a wrong answer, on the
        # surface whose whole job is to show the learner how they are doing.
        if record_history:
            recall_history = RecallHistory(
                user_id=user_id,
                word_id=word_id,
                recall=recall,  # Read the recall value from the request
                recall_time=datetime.utcnow(),
                new_recall_state=new_recall_state,
                old_recall_state=old_recall_state if userword_entry_exists else None,
                is_included=is_included,  # Save is_included in RecallHistory
                provenance=provenance  # #109: 'single' | 'bulk' | None
            )
            db.session.add(recall_history)
            db.session.commit()
        else:
            logger.info(
                f"Inclusion-only update for user {user_id} word {word_id} "
                f"(is_included={is_included}) -- no RecallHistory row written (#111)")

        return success_response(to_dict(userword), "Recall state and recall updated successfully")

    except Exception as e:
        # Log the error with details for debugging
        logging.error(f"Error occurred while updating recall state: {e}", exc_info=True)
        return error_response(f"An error occurred: {str(e)}", 500)

