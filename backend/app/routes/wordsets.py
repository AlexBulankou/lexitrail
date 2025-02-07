from flask import request, Blueprint, jsonify, current_app
from ..models import Wordset, Word
from ..utils import to_dict, success_response, error_response
from app import db
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import multiprocessing
from threading import Lock

bp = Blueprint('wordsets', __name__, url_prefix='/wordsets')
logger = logging.getLogger(__name__)

# Replace TTLCache with a regular dictionary
cache = {}  # Indefinite in-memory cache
cache_lock = Lock()

def initialize_cache():
    """Initialize cache with all wordsets data."""
    logger.info("Starting cache initialization for all wordsets")
    try:
        # Get all wordsets within the main application context
        wordsets = Wordset.query.all()
        
        def init_wordset_cache(app, ws):
            """Initialize cache for a single wordset with proper app context"""
            with app.app_context():
                return get_words_by_wordset(ws.wordset_id, skip_cache=True)
        
        # Get the current app
        app = current_app._get_current_object()
        
        with ThreadPoolExecutor() as executor:
            # Create futures for each wordset with app context
            futures = [
                executor.submit(init_wordset_cache, app, ws)
                for ws in wordsets
            ]
            
            # Wait for all futures to complete
            for future in futures:
                try:
                    result = future.result()
                    if isinstance(result, tuple):  # Error response
                        logger.error(f"Error initializing cache: {result[0]}")
                except Exception as e:
                    logger.error(f"Error initializing cache: {e}", exc_info=True)
                    
        logger.info("Cache initialization completed")
    except Exception as e:
        logger.error(f"Error during cache initialization: {e}", exc_info=True)

@bp.route('', methods=['GET'])
def get_all_wordsets():
    """Fetch all wordsets."""
    try:
        wordsets = Wordset.query.all()
        wordsets_data = [to_dict(ws) for ws in wordsets]
        return success_response(wordsets_data)
    except Exception as e:
        logger.error(f"Error get_all_wordsets: {e}", exc_info=True)
        return error_response(str(e), 500)

def count_syllables(word):
    """Simple function to count the syllables in a Chinese word."""
    return len(word)

def generate_quiz_options(word, words_by_syllable, syllable_count):
    logger.debug(f"Generating quiz options for word '{word.word}' with syllable count {syllable_count}")
    used_word_ids = {word.word_id}

    all_available_words = [w for words in words_by_syllable.values() for w in words if w.word_id not in used_word_ids]

    quiz_options = []
    same_syllable_words = [w for w in words_by_syllable.get(syllable_count, []) if w.word_id not in used_word_ids]

    if len(same_syllable_words) >= 3:
        quiz_options = random.sample(same_syllable_words, 3)
        used_word_ids.update(opt.word_id for opt in quiz_options)
        logger.debug(f"Selected same syllable words: {[opt.word for opt in quiz_options]}")
    else:
        # Add available same-syllable words first
        quiz_options.extend(same_syllable_words)
        used_word_ids.update(opt.word_id for opt in same_syllable_words)
        logger.debug(f"Not enough same syllable words, selected so far: {[opt.word for opt in quiz_options]}")

        # Continue filling up quiz options to reach 3
        while len(quiz_options) < 3:
           
            total_syllables = 0
            concatenated_word = ""
            concatenated_def1 = ""

            # Loop for concatenation
            while total_syllables < syllable_count:
                remaining_words = [w for w in all_available_words if w.word_id not in used_word_ids]
                logger.debug(f"Remaining words: {[w.word for w in remaining_words]}, count: {len(remaining_words)}")

                if not remaining_words:
                    error_msg = "Not enough words to continue concatenation to meet syllable count."
                    logger.error(error_msg)
                    raise ValueError(error_msg)

                next_word = random.choice(remaining_words)
                remaining_syllables_needed = syllable_count - total_syllables
                next_word_syllables = count_syllables(next_word.word)


                # Take only the needed portion of the word
                if next_word_syllables > remaining_syllables_needed:
                    portioned_word = next_word.word[:remaining_syllables_needed]
                    portioned_def1 = next_word.def1
                    concatenated_word += portioned_word
                    concatenated_def1 += ' ' + portioned_def1
                    total_syllables += remaining_syllables_needed
                    logger.debug(f"Portioned '{next_word.word}' to '{portioned_word}' for syllable count match.")
                else:
                    logger.debug(f"Concatenating '{next_word.word}' to '{concatenated_word}' to reach syllable count.")
                    concatenated_word += next_word.word
                    concatenated_def1 += ' ' + next_word.def1
                    total_syllables += next_word_syllables
                    
                    
                # Ensure no duplicate with an existing word
                existing_words = {w.word for w in all_available_words if w.word_id in used_word_ids}
                if concatenated_word in existing_words:
                    # Replace a character to ensure uniqueness
                    replace_index = random.randint(0, len(concatenated_word) - 1)
                    replacement_char = '的' if concatenated_word[replace_index] != '的' else '一'
                    concatenated_word = (
                        concatenated_word[:replace_index] + replacement_char + concatenated_word[replace_index + 1:]
                    )
                    logger.debug(
                        f"Replaced character at index {replace_index} in '{concatenated_word}' "
                        f"to avoid duplication, new word: '{concatenated_word}'"
                    )
                logger.debug(f"After concatenation: {concatenated_word} ({total_syllables}/{syllable_count} syllables)")

            # Append the final concatenated option
            quiz_options.append([
                concatenated_word[:syllable_count],  # Ensure it slices only if needed
                concatenated_def1.strip(),
                "[quiz word]"
            ])

    quiz_options_formatted = [
        [opt.word, opt.def1, opt.def2] if isinstance(opt, Word) else opt
        for opt in quiz_options
    ]
    logger.debug(f"Final quiz options for word '{word.word}': {quiz_options_formatted}")
    return quiz_options_formatted

def process_word_with_options(word, words_by_syllable, total_syllables):
    """Process a single word and generate its quiz options."""
    syllable_count = count_syllables(word.word)
    remaining_syllables = total_syllables - syllable_count
    required_syllables = syllable_count * 3

    # Early validation
    if remaining_syllables < required_syllables:
        error_msg = (
            f"Insufficient syllables in wordset to generate quiz options for word '{word.word}' "
            f"with required syllable count {syllable_count} per option."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.debug(f"Processing word '{word.word}' with syllable count {syllable_count}")
    quiz_options = generate_quiz_options(word, words_by_syllable, syllable_count)

    return {
        "word_id": word.word_id,
        "wordset_id": word.wordset_id,
        "word": word.word,
        "def1": word.def1,
        "def2": word.def2,
        "quiz_options": quiz_options
    }

@bp.route('/<int:wordset_id>/words', methods=['GET'])
def get_words_by_wordset(wordset_id, skip_cache=False):
    """Fetch words by wordset with quiz options and optional random seed."""
    start_time = time.time()
    
    # Check cache first unless skip_cache is True
    if not skip_cache:
        cached_data = cache.get(wordset_id)
        if cached_data:
            logger.debug(f"Cache hit for wordset_id: {wordset_id}")
            return cached_data

    try:
        # Fetch the wordset by ID
        wordset = db.session.get(Wordset, wordset_id)
        if not wordset:
            return error_response('Wordset not found', 404)

        # Set the random seed - use time if no request context
        try:
            seed = request.args.get('seed', default=int(time.time()), type=int)
        except RuntimeError:  # When outside request context
            seed = int(time.time())
            
        random.seed(seed)
        logger.debug(f"Using random seed: {seed}")

        # Query words that belong to this wordset
        query = Word.query.filter_by(wordset_id=wordset_id)
        query_str = str(query.statement.compile(compile_kwargs={"literal_binds": True}))
        words = query.all()
        query_time = time.time() - start_time

        # Pre-calculate syllable counts and organize words
        total_syllables = sum(count_syllables(word.word) for word in words)
        logger.debug(f"Total syllables in wordset (all words): {total_syllables}")

        # Create words_by_syllable dictionary
        words_by_syllable = {}
        for word in words:
            syllable_count = count_syllables(word.word)
            if syllable_count not in words_by_syllable:
                words_by_syllable[syllable_count] = []
            words_by_syllable[syllable_count].append(word)

        # Determine optimal number of workers
        num_workers = min(multiprocessing.cpu_count(), len(words))
        
        # Process words in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Create a partial function with the common arguments
            process_word_partial = partial(
                process_word_with_options,
                words_by_syllable=words_by_syllable,
                total_syllables=total_syllables
            )
            
            # Process all words in parallel
            word_data = list(executor.map(process_word_partial, words))

        processing_time = time.time() - start_time - query_time
        response = success_response(
            word_data,
            metadata={
                'query': query_str,
                'query_time_ms': round(query_time * 1000, 2),
                'processing_time_ms': round(processing_time * 1000, 2),
                'total_time_ms': round((query_time + processing_time) * 1000, 2),
                'num_workers': num_workers,
                'words_processed': len(words),
                'cache_status': 'miss'
            }
        )
        
        # Store in cache (now always, regardless of skip_cache)
        with cache_lock:
            cache[wordset_id] = response
            
        return response
    except Exception as e:
        error_time = time.time() - start_time
        logger.error(f"Error in get_words_by_wordset: {e}", exc_info=True)
        return error_response(
            f"Error fetching words: {str(e)}", 
            500,
            metadata={
                'error_time_ms': round(error_time * 1000, 2)
            }
        )

def init_app(app):
    """Initialize the blueprint with the app context."""
    with app.app_context():
        initialize_cache()

