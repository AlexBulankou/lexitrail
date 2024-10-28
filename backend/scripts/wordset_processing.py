from app.models import Word, Wordset
from sqlalchemy.orm import Session
from .db_operations import add_word, delete_word, add_wordset, delete_wordset
from .logging_setup import log_info

def process_wordset_entries(csv_data, db_data, session: Session, is_check=False):
    """Compare wordset data, log discrepancies, and handle updates."""
    add_count, delete_count = 0, 0

    # Verify data formats
    if not isinstance(csv_data, dict) or not isinstance(db_data, dict):
        log_info("Error: csv_data or db_data is not in expected dictionary format.")
        log_info(f"csv_data type: {type(csv_data)}, db_data type: {type(db_data)}")
        return add_count, delete_count

    for wordset_desc, csv_words in csv_data.items():
        db_words = db_data.get(wordset_desc, set())  # Retrieve words from DB for this wordset

        # Check if wordset exists in the database
        if wordset_desc not in db_data:
            log_info(f"Wordset '{wordset_desc}' is missing in the database. It will be added.")
            if not is_check:
                add_wordset(session, wordset_desc)
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
                log_info(f"Wordset '{wordset_desc}': {len(missing_words)} words will be added, {len(extra_words)} words will be deleted.")

                # Perform additions and deletions
                for word in missing_words:
                    add_word(session, (word, wordset_desc))
                    add_count += 1
                for word in extra_words:
                    delete_word(session, (word, wordset_desc))
                    delete_count += 1

    return add_count, delete_count

def process_word_entries(csv_data, db_data, session: Session, is_check=False):
    """Compare word entries, log discrepancies, and handle updates."""
    add_count, delete_count = 0, 0

    # Verify data formats
    if not isinstance(csv_data, dict) or not isinstance(db_data, dict):
        log_info("Error: csv_data or db_data is not in expected dictionary format.")
        log_info(f"csv_data type: {type(csv_data)}, db_data type: {type(db_data)}")
        return add_count, delete_count

    # Flatten csv_data into a single set of entries
    csv_word_entries = {entry for entries in csv_data.values() for entry in entries}
    db_word_entries = {entry for entries in db_data.values() for entry in entries}

    # Determine new and obsolete entries
    new_entries = csv_word_entries - db_word_entries
    obsolete_entries = db_word_entries - csv_word_entries

    # Log results
    log_info(f"Total new words to add: {len(new_entries)}, total obsolete words to delete: {len(obsolete_entries)}")

    if not is_check:
        for entry in new_entries:
            add_word(session, entry)
            add_count += 1
        for entry in obsolete_entries:
            delete_word(session, entry)
            delete_count += 1

    return add_count, delete_count

def process_entries(csv_data, db_data, entry_type, session: Session, is_check=False):
    """Main entry point for processing entries."""
    if entry_type == "wordset":
        return process_wordset_entries(csv_data, db_data, session, is_check)
    elif entry_type == "word":
        return process_word_entries(csv_data, db_data, session, is_check)
    else:
        raise ValueError(f"Unsupported entry type: {entry_type}")
