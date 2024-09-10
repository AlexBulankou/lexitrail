from .database import db
from datetime import datetime

class User(db.Model):
    __tablename__ = 'users'
    email = db.Column(db.String(320), primary_key=True)

class Wordset(db.Model):
    __tablename__ = 'wordsets'
    wordset_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    description = db.Column(db.String(1024), nullable=False)
    words = db.relationship('Word', backref='wordset', lazy=True)

class Word(db.Model):
    __tablename__ = 'words'
    word_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    word = db.Column(db.String(256), nullable=False)
    wordset_id = db.Column(db.Integer, db.ForeignKey('wordsets.wordset_id'), nullable=False)
    def1 = db.Column(db.String(1024), nullable=False)
    def2 = db.Column(db.String(1024), nullable=False)
    userwords = db.relationship('UserWord', backref='word', lazy=True)
    recall_histories = db.relationship('RecallHistory', backref='word', lazy=True)

class UserWord(db.Model):
    __tablename__ = 'userwords'
    user_id = db.Column(db.String(320), db.ForeignKey('users.email'), primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('words.word_id'), primary_key=True)
    is_included = db.Column(db.Boolean, nullable=False)
    recall_state = db.Column(db.Integer, nullable=False)
    last_recall = db.Column(db.DateTime, nullable=True)
    last_recall_time = db.Column(db.DateTime, nullable=True)
    recall_histories = db.relationship('RecallHistory', backref='userword', lazy=True)

class RecallHistory(db.Model):
    __tablename__ = 'recall_history'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.String(320), db.ForeignKey('users.email'), nullable=False)
    word_id = db.Column(db.Integer, db.ForeignKey('words.word_id'), nullable=False)
    recall = db.Column(db.Boolean, nullable=False)
    recall_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    new_recall_state = db.Column(db.Integer, nullable=False)
    old_recall_state = db.Column(db.Integer, nullable=True)
