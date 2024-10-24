import csv
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, exc, and_
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import text
from google.cloud import storage
from dotenv import load_dotenv

# Import models from the app directory
from app.models import User, Wordset, Word, UserWord, RecallHistory
import logging
from datetime import datetime



# Load environment variables from .env file located in the parent directory of 'scripts'
env_path = Path('..') / '.env'
load_dotenv(dotenv_path=env_path)

# Environment variables
DB_ROOT_PASSWORD = os.getenv('DB_ROOT_PASSWORD', 'default_password')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'test_db')
MYSQL_FILES_BUCKET = os.getenv('MYSQL_FILES_BUCKET', 'your-bucket-name')  # Bucket name comes from .env

# Configurations (Hardcoded paths)
WORDSETS_CSV_PATH = '../terraform/csv/wordsets.csv'  # Updated path to terraform directory
WORDS_CSV_PATH = '../terraform/csv/words.csv'  # Updated path to terraform directory

# Construct DB_URI using environment variables (note the 127.0.0.1:3306 for port-forwarding)
DB_URI = f"mysql+pymysql://root:{DB_ROOT_PASSWORD}@127.0.0.1:3306/{DATABASE_NAME}"


# Setup SQLAlchemy engine and session
engine = create_engine(DB_URI)
Session = sessionmaker(bind=engine)

# Setup logging to log both to console and with timestamps
logger = logging.getLogger('lexitrailcmd')
logger.setLevel(logging.INFO)

# Disable propagation to the root logger to prevent duplicate log entries
logger.propagate = False

# Remove any existing handlers
if logger.hasHandlers():
    logger.handlers.clear()

# Create console handler and set level to info
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create a formatter with timestamps
formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
console_handler.setFormatter(formatter)

# Add the handler to the logger
logger.addHandler(console_handler)

def log_info(message):
    """Helper function to log with a timestamp."""
    logger.info(message)

def load_csv_data(file_path, key_field):
    """Load CSV data and return a set of the values for the specified key field."""
    with open(file_path, mode='r', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        data = {row[key_field] for row in csv_reader}
    return data

def update_entries(csv_data, existing_data, add_func, delete_func, entry_type):
    """Process CSV and existing DB data, adding and deleting entries as necessary."""
    updated_count = 0

    # Add new entries
    new_entries = csv_data - existing_data
    for entry in new_entries:
        add_func(entry)
        updated_count += 1
        log_info(f"Added new {entry_type}: {entry}")

    # Delete obsolete entries
    obsolete_entries = existing_data - csv_data
    for entry in obsolete_entries:
        delete_func(entry)
        updated_count += 1
        log_info(f"Deleted obsolete {entry_type} and its dependencies: {entry}")

    return updated_count

def add_wordset(session, description):
    """Add a new wordset entry to the database."""
    new_wordset = Wordset(description=description)
    session.add(new_wordset)

def delete_wordset(session, description):
    """Delete a wordset entry and its dependencies from the database."""
    wordset = session.query(Wordset).filter_by(description=description).first()
    if wordset:
        session.delete(wordset)

def add_word(session, word_entry):
    """Add a new word entry to the database."""
    word, wordset_id = word_entry
    new_word = Word(word=word, wordset_id=wordset_id, def1='def1', def2='def2')
    session.add(new_word)

def delete_word(session, word_entry):
    """Delete a word entry and its dependencies from the database."""
    word, wordset_id = word_entry
    word_record = session.query(Word).filter_by(word=word, wordset_id=wordset_id).first()
    if word_record:
        session.delete(word_record)

def upload_to_gcs(local_file_path, gcs_file_path):
    """Uploads a local file to Google Cloud Storage."""
    try:
        client = storage.Client()
        bucket = client.bucket(MYSQL_FILES_BUCKET)
        blob = bucket.blob(gcs_file_path)
        blob.upload_from_filename(local_file_path)
        log_info(f"Uploaded {local_file_path} to {gcs_file_path} in bucket {MYSQL_FILES_BUCKET}")
    except Exception as e:
        log_info(f"Failed to upload {local_file_path} to GCS: {str(e)}")


def validate_local_files():
    """Validates that the required local CSV files and .env file are present."""
    env_file_path = Path('..') / '.env'
    if not env_file_path.exists():
        log_info(f"Missing required file: {env_file_path}")
        return False
    if not os.path.exists(WORDSETS_CSV_PATH):
        log_info(f"Missing required file: {WORDSETS_CSV_PATH}")
        return False
    if not os.path.exists(WORDS_CSV_PATH):
        log_info(f"Missing required file: {WORDS_CSV_PATH}")
        return False
    log_info("All required local files are present.")
    return True


def validate_db_connection():
    """Validates connection to the MySQL database by first executing SHOW DATABASES, 
    and then executing SELECT 1 FROM wordsets after connecting to the specified database."""
    
    # Log the full connection string including the password
    log_info(f"Attempting to connect to MySQL server with connection string: {DB_URI}")
    
    # First, connect to MySQL server without specifying a database and run SHOW DATABASES
    try:
        # Create a connection without specifying a database
        engine_no_db = create_engine(f"mysql+pymysql://root:{DB_ROOT_PASSWORD}@127.0.0.1:3306")
        with engine_no_db.connect() as conn:
            result = conn.execute(text('SHOW DATABASES'))
            log_info("Successfully connected to MySQL server and retrieved the list of databases:")
            for row in result:
                log_info(f" - {row[0]}")
    except Exception as e:
        log_info(f"Failed to execute SHOW DATABASES on MySQL server: {str(e)}")
        return False

    # Now connect to the specified database and execute SELECT 1 FROM wordsets
    try:
        with engine.connect() as conn:
            result = conn.execute(text('SELECT 1 FROM wordsets LIMIT 1'))
            log_info("Successfully connected to the specified database and executed SELECT 1 FROM wordsets.")
        return True
    except Exception as e:
        log_info(f"Failed to connect to the MySQL database or execute SELECT 1 FROM wordsets: {str(e)}")
        return False




def validate_gcs_connection():
    """Validates connection to the Google Cloud Storage bucket."""
    try:
        client = storage.Client()
        bucket = client.get_bucket(MYSQL_FILES_BUCKET)
        # Try to list objects to check if the bucket is accessible
        blobs = bucket.list_blobs()
        log_info(f"Successfully connected to Google Cloud Storage bucket: {MYSQL_FILES_BUCKET}")
        return True
    except Exception as e:
        log_info(f"Failed to connect to Google Cloud Storage bucket: {str(e)}")
        return False


def dbupdate():
    """Synchronizes the database with the CSV files and uploads to GCS."""
    log_info("Starting dbupdate function")
    session = Session()

    # Process wordsets.csv
    try:
        wordset_data = load_csv_data(WORDSETS_CSV_PATH, 'description')
        existing_wordsets = {wordset.description for wordset in session.query(Wordset).all()}

        wordsets_updated = update_entries(
            wordset_data, existing_wordsets,
            lambda entry: add_wordset(session, entry),
            lambda entry: delete_wordset(session, entry),
            "wordset"
        )

        # Commit wordset changes
        session.commit()

        if wordsets_updated == 0:
            log_info("No wordsets were updated.")
        else:
            log_info(f"Total wordsets updated: {wordsets_updated}")

    except Exception as e:
        log_info(f"Error processing wordsets.csv: {str(e)}")
        session.rollback()

    # Process words.csv
    try:
        word_data = load_csv_data(WORDS_CSV_PATH, 'word')
        existing_words = {(word.word, word.wordset_id) for word in session.query(Word).all()}

        words_updated = update_entries(
            word_data, existing_words,
            lambda entry: add_word(session, entry),
            lambda entry: delete_word(session, entry),
            "word"
        )

        # Commit word changes
        session.commit()

        if words_updated == 0:
            log_info("No words were updated.")
        else:
            log_info(f"Total words updated: {words_updated}")

    except Exception as e:
        log_info(f"Error processing words.csv: {str(e)}")
        session.rollback()

    # Post-processing step to upload files to GCS
    try:
        log_info("Starting GCS upload step")
        upload_to_gcs(WORDSETS_CSV_PATH, 'csv/wordsets.csv')
        upload_to_gcs(WORDS_CSV_PATH, 'csv/words.csv')
        log_info("Completed GCS upload step")
    except Exception as e:
        log_info(f"Error uploading to GCS: {str(e)}")

    log_info("Completed dbupdate function")


def main():
    """Main entry point for the command line utility."""
    if len(sys.argv) < 2:
        log_info("Error: No function provided. Supported functions: dbupdate")
        sys.exit(1)

    function = sys.argv[1].lower()
    if function == 'dbupdate':
        if not validate_local_files():
            sys.exit(1)
        if not validate_db_connection():
            sys.exit(1)
        if not validate_gcs_connection():
            sys.exit(1)
        dbupdate()
    else:
        log_info(f"Error: Unsupported function '{function}'. Supported functions: dbupdate")
        sys.exit(1)

if __name__ == "__main__":
    main()
