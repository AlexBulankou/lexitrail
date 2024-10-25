from sqlalchemy.orm import Session
from .logging_setup import log_info
from app.models import Wordset, Word, UserWord, RecallHistory

def add_wordset(session: Session, description: str):
    """Add a new wordset entry to the database."""
    new_wordset = Wordset(description=description)
    session.add(new_wordset)

def delete_wordset(session: Session, description: str):
    """Delete a wordset entry and its dependencies from the database."""
    wordset = session.query(Wordset).filter_by(description=description).first()
    if wordset:
        session.delete(wordset)

def add_word(session: Session, word_entry):
    """Add a new word entry to the database."""
    word, wordset_id = word_entry
    new_word = Word(word=word, wordset_id=wordset_id, def1='def1', def2='def2')
    session.add(new_word)

def delete_word(session: Session, word_entry):
    """Delete a word entry and its dependencies from the database."""
    word, wordset_id = word_entry
    word_record = session.query(Word).filter_by(word=word, wordset_id=wordset_id).first()
    if word_record:
        # Delete dependencies in userwords and recall_history
        session.query(UserWord).filter_by(word_id=word_record.word_id).delete(synchronize_session=False)
        session.query(RecallHistory).filter_by(word_id=word_record.word_id).delete(synchronize_session=False)
        
        # Delete the word itself
        session.delete(word_record)

