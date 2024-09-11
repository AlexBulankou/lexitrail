import logging
from app import create_app, db

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class TestUtils:
    @staticmethod
    def setup_test_app():
        """
        Creates and configures the Flask app and initializes the in-memory database for testing.
        Returns the Flask test client and the app instance.
        """
        app = create_app()
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'  # Use in-memory SQLite for tests
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        client = app.test_client()

        # Log the SQLAlchemy database URI to ensure it's using SQLite
        logger.debug(f"Database URI used for testing: {app.config['SQLALCHEMY_DATABASE_URI']}")

        # Initialize the database
        with app.app_context():
            logger.debug("Creating all tables...")
            db.create_all()
            logger.debug("Tables created successfully.")

        return client, app

    @staticmethod
    def teardown_test_db(app):
        """
        Drops all database tables after tests are finished.
        """
        with app.app_context():
            logger.debug("Dropping all tables...")
            db.drop_all()
            logger.debug("Tables dropped successfully.")
