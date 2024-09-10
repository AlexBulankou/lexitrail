from flask import Blueprint
from .users import bp as users_bp
from .wordsets import bp as wordsets_bp
from .words import bp as words_bp
from .userwords import bp as userwords_bp

def register_routes(app):
    app.register_blueprint(users_bp)
    app.register_blueprint(wordsets_bp)
    app.register_blueprint(words_bp)
    app.register_blueprint(userwords_bp)

