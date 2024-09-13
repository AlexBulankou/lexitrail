from flask import Flask
from .config import Config
from .database import init_db, db  # Add db import
from .routes import register_routes

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize the database
    init_db(app)
    
    # Register routes
    register_routes(app)

    return app

# Expose db so it can be imported from app
__all__ = ['create_app', 'db']
