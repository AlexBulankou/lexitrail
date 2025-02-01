from flask import Flask
from .config import Config
from .database import init_db, db  # Add db import
from .routes import register_routes
from flask_cors import CORS  # Import CORS
import sys
import logging

def create_app(config_class=Config):
    # Configure logging
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    

    # Reconfigure the 'werkzeug' logger so it logs to stdout instead of stderr
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.WARNING)
    
    # Remove any existing handlers (often the default is stderr)...
    # for handler in list(werkzeug_logger.handlers):
    #    werkzeug_logger.removeHandler(handler)
    # ...then add a StreamHandler pointing to stdout
    # handler = logging.StreamHandler(sys.stdout)
    #  handler.setLevel(logging.INFO)
    #  werkzeug_logger.addHandler(handler)
    
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize the database
    init_db(app)
    
    # Register routes
    register_routes(app)
    
    # Enable CORS for all origins
    CORS(app, resources={r"/*": {"origins": "*"}})

    return app

# Expose db so it can be imported from app
__all__ = ['create_app', 'db']
