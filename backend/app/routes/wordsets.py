from flask import request, Blueprint, jsonify, current_app
from ..models import Wordset, Word
from ..utils import to_dict, success_response, error_response
from app import db
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError
from ..cache_warm_policy import (CACHE_WARM_DEADLINE_S, WARM_FAILED,
                                 WARM_OK, WARM_RESULT_ERROR_RESPONSE,
                                 WARM_RESULT_OK, classify_warm_result,
                                 warm_verdict)
from functools import partial
import multiprocessing
from ..cpu_quota import effective_cpus
from threading import Lock
import threading

bp = Blueprint('wordsets', __name__, url_prefix='/wordsets')
logger = logging.getLogger(__name__)

# Replace TTLCache with a regular dictionary
cache = {}  # Indefinite in-memory cache
cache_lock = Lock()
cache_status = {"initialized": False, "complete": False, "progress": 0, "total": 0, "error": None,
                "state": "cold", "succeeded": 0, "unfinished": 0,
                # issue-266: None until the background warm thread starts.
                "started_at": None}

def initialize_cache():
    """Initialize cache with all wordsets data."""
    logger.info("Starting cache initialization for all wordsets")
    # issue-266: stamp when the warm BEGAN. /readyz needs an elapsed time to
    # apply CACHE_WARM_DEADLINE_S -- without it, a warm that hangs holds every
    # replica NotReady forever and a partial degradation becomes a total
    # outage. The deadline is the escape hatch and it cannot be evaluated
    # without a start time.
    cache_status["started_at"] = time.time()
    try:
        # Get all wordsets within the main application context
        wordsets = Wordset.query.all()
        cache_status["total"] = len(wordsets)
        cache_status["progress"] = 0
        
        def init_wordset_cache(app, ws):
            """Initialize cache for a single wordset with proper app context.

            #106: this deliberately does NOT catch. It used to swallow every
            exception and `return None`, and the consumer below counted any
            non-tuple as a success — so a wordset whose warm RAISED was counted
            as warmed and the whole warm reported `ok`. The outer `except` fired
            on things like `app.app_context()` itself failing: rare, and exactly
            the infrastructure failure you most want visible.

            Letting it propagate routes it into the consumer's own
            `except Exception` around `future.result()`, which already logs and
            does not increment. Per #106 AC4, the fix is NOT to return a tuple
            here to satisfy the `isinstance` check — that would make the
            sentinel carry two meanings and leave the reader unable to tell the
            two failure kinds apart.
            """
            with app.app_context():
                result = get_words_by_wordset(ws.wordset_id, skip_cache=True)
                cache_status["progress"] += 1
                logger.info(f"Cache initialized for wordset {ws.wordset_id} ({cache_status['progress']}/{cache_status['total']})")
                return result

        # Get the current app
        app = current_app._get_current_object()
        
        succeeded = 0
        # #97 — deliberately NOT a `with` block (hc2 review of PR #103).
        # `ThreadPoolExecutor.__exit__` unconditionally calls `shutdown(wait=True)`,
        # INCLUDING when an exception was caught and handled inside the block. So a
        # `with` here would honour the deadline for the LOG LINE and then block on
        # the full drain before any `cache_status` assignment could run — the
        # deadline would bound what we SAY and not what we DO. Measured on a
        # 5-task / 1-worker / 2s-each pool with a 0.5s deadline:
        #
        #     caught inside the with-block      t=0.50s   <- deadline honoured
        #     first statement AFTER the block   t=10.00s  <- the full drain
        #     explicit shutdown(wait=False)     t=0.50s   <- what we do now
        #
        # A caller polling /wordsets/cache-status during those 9.5s would see the
        # pre-warm default (`initialized: False, complete: False`) rather than
        # `degraded`/`failed` — i.e. AC2/AC3's observability would be missing in
        # exactly the scenario they exist for, and `initialize_cache` itself would
        # not return until every straggler finished. That is the unbounded wait
        # this issue set out to remove, relabelled.
        executor = ThreadPoolExecutor(max_workers=2)  # Limit to 2 workers to reduce load
        try:
            # Create futures for each wordset with app context
            futures = {
                executor.submit(init_wordset_cache, app, ws): ws.wordset_id
                for ws in wordsets
            }

            # Consume in COMPLETION order against one deadline for the whole warm.
            # The old code iterated in SUBMISSION order and gave each future 60s
            # from the moment the loop reached it, so a future still sitting in the
            # queue was charged for waiting -- and the timeout cancelled nothing.
            try:
                for future in as_completed(futures, timeout=CACHE_WARM_DEADLINE_S):
                    ws_id = futures[future]
                    try:
                        result = future.result()
                        # #106: classify on a POSITIVE success signal. The old
                        # `else: succeeded += 1` adopted every non-tuple value,
                        # including the `None` the swallowing except returned.
                        outcome = classify_warm_result(result)
                        if outcome == WARM_RESULT_ERROR_RESPONSE:
                            logger.error(
                                f"Cache warm FAILED (error_response) for wordset {ws_id}: {result[0]}")
                            cache_status["error"] = str(result[0])
                        elif outcome == WARM_RESULT_OK:
                            succeeded += 1
                        else:
                            # #106 AC2: a distinct line. A wordset that returned
                            # nothing is not the same event as one whose query
                            # failed, and merging them is what let this hide.
                            msg = (f"Cache warm RETURNED NOTHING for wordset {ws_id} "
                                   f"(outcome={outcome}) -- NOT counted as warmed.")
                            logger.error(msg)
                            cache_status["error"] = msg
                    except Exception as e:
                        # #106 AC2: "RAISED", not "FAILED" -- a propagated
                        # exception and a converted error_response are different
                        # events with different causes, and the old code gave
                        # them near-identical lines.
                        logger.error(f"Cache warm RAISED for wordset {ws_id}: {e}", exc_info=True)
                        cache_status["error"] = str(e)
            except FuturesTimeoutError:
                # AC2: name the wordsets that never finished, and say so in words
                # that cannot be confused with a wordset whose warm actually broke.
                # Previously both produced the identical "Error initializing cache"
                # line, so the logs could not tell a real failure from a queue.
                unfinished = [ws_id for f, ws_id in futures.items() if not f.done()]
                msg = (f"Cache warm DID NOT FINISH within {CACHE_WARM_DEADLINE_S}s -- "
                       f"{len(unfinished)} wordset(s) still running or queued: {unfinished}. "
                       "This is a deadline, NOT a per-wordset failure.")
                logger.error(msg)
                cache_status["error"] = msg
                # Release the deadline NOW. `cancel_futures=True` drops anything
                # still QUEUED; the 1-2 already running cannot be cancelled, but
                # `wait=False` means they finish in the background instead of
                # holding this thread. Threads are daemon-managed by the pool, so
                # nothing leaks beyond process lifetime.
                executor.shutdown(wait=False, cancel_futures=True)
        finally:
            # Idempotent: a second shutdown after the one above is a no-op, and on
            # the normal path this is the only one. Never `wait=True` -- see above.
            executor.shutdown(wait=False)

        cache_status["succeeded"] = succeeded
        cache_status["unfinished"] = max(cache_status["total"] - succeeded, 0)
        cache_status["state"] = warm_verdict(cache_status["total"], succeeded)
        # AC3: `initialized` now means "every wordset warmed", not "the function
        # reached its end". A degraded warm leaves it False so a reader cannot
        # mistake a partial cache for a complete one; `state` carries which.
        #
        # ⚠️ `complete` is separate ON PURPOSE, and is what a poller should wait
        # on. Narrowing `initialized` without it would convert "the warm finished
        # imperfectly" into "the warm never finished" for anyone blocking on that
        # flag -- an unbounded wait, which is a worse failure than the dishonest
        # True it replaces.
        #
        # ⚠️ UPDATED by issue-266: this used to say "nothing in this repo reads
        # the field and no k8s probe gates on it (both checked)". That was true
        # when written and is now FALSE -- /readyz consults `complete` and
        # `state` through cache_warm_policy.cache_warm_readiness(), so these
        # fields decide whether the pod takes user traffic. Treat every write
        # to them as probe-visible.
        cache_status["complete"] = True
        cache_status["initialized"] = cache_status["state"] == WARM_OK
        logger.info(
            f"Cache initialization completed: state={cache_status['state']} "
            f"{succeeded}/{cache_status['total']} warmed")
    except Exception as e:
        logger.error(f"Error during cache initialization: {e}", exc_info=True)
        cache_status["error"] = str(e)
        # issue-266 (hc2's #309 review): classify the TOTAL failure too.
        # Everything above this handler -- including `Wordset.query.all()` --
        # can throw before any per-wordset classification runs, and this
        # handler used to set only `error`, leaving `state` at its module
        # default "cold" and `complete` False FOREVER. Nothing consumed those
        # fields, so it was invisible; #266 made /readyz consume them, and a
        # third shape neither branch handled appeared: not complete, not
        # FAILED, just never classified. A pod would then sit NotReady for the
        # full CACHE_WARM_DEADLINE_S before serving degraded -- strictly worse
        # than the outright-FAILED case, which degrades to serving at once.
        cache_status["state"] = WARM_FAILED

@bp.route('/cache-status', methods=['GET'])
def get_cache_status():
    """Get the status of cache initialization."""
    return success_response(cache_status)

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

def generate_quiz_options(word, words_by_syllable, syllable_count, corpus_by_syllable=None):
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
        # Add available same-syllable words from this wordset first
        quiz_options.extend(same_syllable_words)
        used_word_ids.update(opt.word_id for opt in same_syllable_words)
        logger.debug(f"Not enough same syllable words, selected so far: {[opt.word for opt in quiz_options]}")

        # SUG-3: before synthesizing pseudo-words, fill with REAL words of the
        # same syllable length drawn from the full corpus (all wordsets).
        if len(quiz_options) < 3 and corpus_by_syllable:
            corpus_same_syllable = [
                w for w in corpus_by_syllable.get(syllable_count, [])
                if w.word_id not in used_word_ids
            ]
            random.shuffle(corpus_same_syllable)
            for w in corpus_same_syllable:
                if len(quiz_options) >= 3:
                    break
                quiz_options.append(w)
                used_word_ids.add(w.word_id)
            logger.debug(f"After corpus fill: {[opt.word for opt in quiz_options if isinstance(opt, Word)]}")

        # Last resort: synthetic concatenation, only when neither this wordset
        # nor the corpus can supply enough real words of this length.
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
                    
                    
                # Ensure no duplicate with an existing word (or with the target word
                # itself -- `all_available_words` excludes the target by construction,
                # so without adding it explicitly here a portioned prefix of another
                # word that happens to equal the target's own text is never caught;
                # e.g. "怎么样了"[:3] == "怎么样". See lexitrail#277's post-merge red.)
                existing_words = {word.word} | {
                    w.word for w in all_available_words if w.word_id in used_word_ids
                }
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

def process_word_with_options(word, words_by_syllable, total_syllables, corpus_by_syllable=None):
    """Process a single word and generate its quiz options."""
    syllable_count = count_syllables(word.word)

    # SUG-3: count REAL same-length distractor candidates from this wordset plus
    # the full corpus. Only when those can't supply 3 options do we fall back to
    # synthetic concatenation, which needs a wordset syllable budget.
    corpus_pool = corpus_by_syllable or {}
    real_candidate_ids = {
        w.word_id
        for w in words_by_syllable.get(syllable_count, []) + corpus_pool.get(syllable_count, [])
        if w.word_id != word.word_id
    }
    if len(real_candidate_ids) < 3:
        remaining_syllables = total_syllables - syllable_count
        required_syllables = syllable_count * 3
        if remaining_syllables < required_syllables:
            error_msg = (
                f"Insufficient syllables in wordset to generate quiz options for word '{word.word}' "
                f"with required syllable count {syllable_count} per option."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

    logger.debug(f"Processing word '{word.word}' with syllable count {syllable_count}")
    quiz_options = generate_quiz_options(word, words_by_syllable, syllable_count, corpus_by_syllable)

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
        else:
            # If cache is still initializing, inform the client
            if not cache_status["initialized"] and cache_status["progress"] > 0:
                logger.info(f"Cache miss for wordset_id: {wordset_id}, cache still initializing ({cache_status['progress']}/{cache_status['total']})")
            else:
                logger.debug(f"Cache miss for wordset_id: {wordset_id}")

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

        # SUG-3: corpus-wide pool of REAL words grouped by syllable length,
        # used as distractors so quiz options are real words of matching length
        # rather than synthetic syllable concatenations (e.g. "wǒmen diànnǎo").
        corpus_by_syllable = {}
        for w in Word.query.all():
            corpus_by_syllable.setdefault(count_syllables(w.word), []).append(w)

        # Determine optimal number of workers
        # lexitrail#276: effective_cpus() reads the CGROUP QUOTA, not nproc.
        # cpu_count() reports the NODE's cores (2) while cpu.max grants 0.2 CPU,
        # so this used to spawn 2 threads that drained a 20ms budget in ~10ms and
        # froze the container for the rest of every 100ms period.
        num_workers = min(effective_cpus(), len(words))
        
        # Process words in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Create a partial function with the common arguments
            process_word_partial = partial(
                process_word_with_options,
                words_by_syllable=words_by_syllable,
                total_syllables=total_syllables,
                corpus_by_syllable=corpus_by_syllable
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
    def background_cache_init():
        with app.app_context():
            initialize_cache()
    
    # Start cache initialization in background thread
    cache_thread = threading.Thread(target=background_cache_init, daemon=True)
    cache_thread.start()

