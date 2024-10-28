import sys
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from .config import DB_URI
from .validators import validate_local_files, validate_db_connection, validate_gcs_connection
from .wordset_processing import process_wordset_entries, process_word_entries
from .data_loader import load_wordset_data, load_word_data
from .gcs_operations import upload_to_gcs
from .logging_setup import log_info
from app.models import Wordset, Word
from .config import WORDSETS_CSV_PATH, WORDS_CSV_PATH

# Setup SQLAlchemy engine and session
engine = create_engine(DB_URI)
Session = sessionmaker(bind=engine)

def print_wordset_summary(session):
    """Prints a summary of wordsets and their word counts in both the file and database."""
    # Load wordsets to create a mapping of wordset_id to descriptions and a description-based data structure
    wordset_mapping, csv_wordset_data = load_wordset_data(WORDSETS_CSV_PATH)

    # Word count per wordset in CSV file using description-based data
    csv_word_counts = load_word_data(WORDS_CSV_PATH, wordset_mapping)
    log_info("Wordsets and word counts from words.csv:")
    for wordset_desc, words in sorted(csv_word_counts.items()):
        log_info(f" - Wordset: {wordset_desc}, Word Count: {len(words)}")

    # Word count per wordset in database
    db_word_counts = {
        wordset.description.strip(): session.query(Word).filter_by(wordset_id=wordset.wordset_id).count()
        for wordset in session.query(Wordset).all()
    }
    log_info("Wordsets and word counts from database:")
    for wordset_desc, count in sorted(db_word_counts.items()):
        log_info(f" - Wordset: {wordset_desc}, Word Count: {count}")

def load_data(session, csv_path, word_level=False):
    """Load data from CSV and DB into appropriate format based on word_level."""
    if word_level:
        # Load word-level data
        wordset_mapping, _ = load_wordset_data(WORDSETS_CSV_PATH)  # Get mapping from wordset file
        csv_data = load_word_data(csv_path, wordset_mapping)
    else:
        # Load wordset-level data
        _, csv_data = load_wordset_data(csv_path)  # Returns only description-based data

    # Ensure data format for downstream processing
    if not isinstance(csv_data, dict):
        log_info(f"Error: Expected csv_data to be a dictionary, but got {type(csv_data)}")
        raise ValueError("Invalid csv_data format.")

    # Load DB data in expected dictionary format with descriptions as keys
    db_data = {
        wordset.description.strip(): {
            word.word.strip() for word in session.query(Word).filter_by(wordset_id=wordset.wordset_id)
        }
        for wordset in session.query(Wordset).all()
    }
    
    return csv_data, db_data

def sync_and_log_summary(csv_data, db_data, entry_type, session, is_check):
    """Logs and processes the wordsets for dbcheck and dbupdate."""
    log_info(f"Starting {entry_type} sync (is_check={is_check})")
    if entry_type == "wordset":
        wordsets_added, wordsets_deleted = process_wordset_entries(csv_data, db_data, session, is_check)
    else:
        wordsets_added, wordsets_deleted = process_word_entries(csv_data, db_data, session, is_check)

    log_info(f"Total {entry_type}s to add: {wordsets_added}")
    log_info(f"Total {entry_type}s to delete: {wordsets_deleted}")

def dbupdate():
    """Synchronizes the database with the CSV files and uploads to GCS."""
    log_info("Starting dbupdate function")
    session = Session()

    try:
        # Load and sync wordsets
        csv_wordsets, db_wordsets = load_data(session, WORDSETS_CSV_PATH, word_level=False)
        sync_and_log_summary(csv_wordsets, db_wordsets, "wordset", session, is_check=False)

        # Load and sync words
        csv_words, db_words = load_data(session, WORDS_CSV_PATH, word_level=True)
        sync_and_log_summary(csv_words, db_words, "word", session, is_check=False)

        # Commit changes
        session.commit()

    except Exception as e:
        log_info(f"Error during dbupdate in {__file__} at line {e.__traceback__.tb_lineno}: {str(e)}")
        session.rollback()

    try:
        log_info("Starting GCS upload step")
        upload_to_gcs(WORDSETS_CSV_PATH, 'csv/wordsets.csv')
        upload_to_gcs(WORDS_CSV_PATH, 'csv/words.csv')
        log_info("Completed GCS upload step")
    except Exception as e:
        log_info(f"Error uploading to GCS in {__file__} at line {e.__traceback__.tb_lineno}: {str(e)}")

    log_info("Completed dbupdate function")

def dbcheck():
    """Compares the database with CSV files and logs changes that would be applied by dbupdate."""
    log_info("Starting dbcheck function (dry run)")
    session = Session()

    # Print wordset summary
    print_wordset_summary(session)

    try:
        # Load and check wordsets
        csv_wordsets, db_wordsets = load_data(session, WORDSETS_CSV_PATH, word_level=False)
        sync_and_log_summary(csv_wordsets, db_wordsets, "wordset", session, is_check=True)

        # Load and check words
        csv_words, db_words = load_data(session, WORDS_CSV_PATH, word_level=True)
        sync_and_log_summary(csv_words, db_words, "word", session, is_check=True)

    except Exception as e:
        log_info(f"Error during dbcheck in {__file__} at line {e.__traceback__.tb_lineno}: {str(e)}")

    log_info("Completed dbcheck function")

def main():
    """Main entry point for the command line utility."""
    if len(sys.argv) < 2:
        log_info("Error: No function provided. Supported functions: dbupdate, dbcheck")
        sys.exit(1)

    function = sys.argv[1].lower()
    if not validate_local_files() or not validate_db_connection():
        sys.exit(1)

    if function == 'dbupdate':
        if not validate_gcs_connection():
            sys.exit(1)
        dbupdate()
    elif function == 'dbcheck':
        dbcheck()
    else:
        log_info(f"Error: Unsupported function '{function}'. Supported functions: dbupdate, dbcheck")
        sys.exit(1)

if __name__ == "__main__":
    main()
