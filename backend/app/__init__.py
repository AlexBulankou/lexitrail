from flask import Flask
from .config import Config
from .database import init_db, db
from .routes import register_routes, wordsets
from flask_cors import CORS
from flask_compress import Compress
import sys
import logging
from .utils import ColorTruncatingFormatter
from .errors import register_error_handlers

def create_app(config_class=Config):
    # Configure logging for the entire application
    handler = logging.StreamHandler(sys.stdout)
    formatter = ColorTruncatingFormatter(
        fmt='[%(levelname)s][%(asctime)s][%(name)s]%(message)s',
        max_length=100
    )
    handler.setFormatter(formatter)
    
    logging.basicConfig(
        level=logging.INFO,
        force=True,
        handlers=[handler]
    )

    # Create logger for this module
    logger = logging.getLogger(__name__)
    logger.info("Hello from logging!")

    # Configure the werkzeug logger specifically
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.WARNING)
    
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize the database
    init_db(app)
    
    # Register routes (this already registers the wordsets blueprint)
    register_routes(app)

    # lexitrail#180: a 500 from an uncaught exception emitted NOTHING -- error_response() is a
    # helper routes must call, and the access log only ever sees `GET /`. So every 500
    # investigation here started from an undercount with nothing saying so.
    register_error_handlers(app)
    
    # lexitrail#266: compress responses. The word payloads are large and highly
    # repetitive JSON -- measured 688,345 -> 180,730 B (3.8x) on HSK6, the biggest
    # wordset, which is the one the "slow to load" report is about.
    #
    # Registered BEFORE CORS on purpose: both wrap the response, and Flask-Compress
    # must see the final body. It also sets `Vary: Accept-Encoding`, which is the
    # part a hand-rolled hook usually omits -- and omitting it lets a shared cache
    # serve a gzipped body to a client that did not ask for one.
    #
    # Fails OPEN by construction: a client that does not send Accept-Encoding gets
    # the identical uncompressed bytes it gets today, so the worst case of this
    # change is the current behaviour.
    Compress(app)

    # Enable CORS for all origins
    CORS(app, resources={r"/*": {"origins": "*"}})
    
    # Initialize cache
    wordsets.init_app(app)

    return app

# Expose db so it can be imported from app
__all__ = ['create_app', 'db']
