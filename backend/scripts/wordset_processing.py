from app.models import Word, Wordset
from sqlalchemy.orm import Session
from .db_operations import add_word, delete_word, add_wordset, delete_wordset  # Ensure add/delete functions for wordsets exist
from .logging_setup import log_info

def process_entries(csv_data, db_data, entry_type, session: Session, is_check=False):
    """Compare CSV and DB data, log discrepancies, and handle updates for wordsets and words."""
    add_count, delete_count = 0, 0

    # Verify data formats
    if not isinstance(csv_data, dict) or not isinstance(db_data, dict):
        log_info("Error: csv_data or db_data is not in expected dictionary format.")
        log_info(f"csv_data type: {type(csv_data)}, db_data type: {type(db_data)}")
        return add_count, delete_count

    # Log initial data samples for verification
    log_info("Debugging data at start of process_entries:")
    log_info(f"CSV Data Sample (wordset): {list(csv_data.items())[:1]}")
    log_info(f"DB Data Sample (wordset): {list(db_data.items())[:1]}")

    if entry_type == "wordset":
        # Processing wordsets
        for wordset_desc, csv_words in csv_data.items():
            db_words = db_data.get(wordset_desc, set())  # Retrieve words from DB for this wordset

            # Check if wordset exists in the database
            if not db_data.get(wordset_desc):
                log_info(f"Wordset '{wordset_desc}' is missing in the database. It will be added.")
                if not is_check:
                    add_wordset(session, wordset_desc)  # Assuming you have an add_wordset function
                    add_count += 1
                    db_words = set()  # Set to empty to prepare for missing words check

            # Identify discrepancies in word counts
            missing_words = csv_words - db_words
            extra_words = db_words - csv_words

            if missing_words or extra_words:
                log_info(f"Discrepancy in wordset '{wordset_desc}':")
                log_info(f" - CSV word count = {len(csv_words)}, DB word count = {len(db_words)}")
                log_info(f" - Missing words: {missing_words}")
                log_info(f" - Extra words: {extra_words}")

                if not is_check:
                    # Summary logging instead of listing each word
                    log_info(f"Wordset '{wordset_desc}': {len(missing_words)} words will be added, {len(extra_words)} words will be deleted.")

                    # Perform additions and deletions
                    for word in missing_words:
                        add_word(session, (word, wordset_desc))
                        add_count += 1
                    for word in extra_words:
                        delete_word(session, (word, wordset_desc))
                        delete_count += 1

    elif entry_type == "word":
        # Processing words directly by individual entries
        csv_word_entries = {entry for entries in csv_data.values() for entry in entries}
        db_word_entries = {entry for entries in db_data.values() for entry in entries}

        new_entries = csv_word_entries - db_word_entries
        obsolete_entries = db_word_entries - csv_word_entries

        # Summarized logging
        log_info(f"Total new words to add: {len(new_entries)}, total obsolete words to delete: {len(obsolete_entries)}")

        if not is_check:
            for entry in new_entries:
                add_word(session, entry)
                add_count += 1
            for entry in obsolete_entries:
                delete_word(session, entry)
                delete_count += 1

    log_info(f"Completed processing with {add_count} additions and {delete_count} deletions.")
    return add_count, delete_count
