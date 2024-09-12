import os
import logging
import pymysql
from app import create_app, db
from google.cloud import storage
from dotenv import load_dotenv
from pathlib import Path
from sqlalchemy import text
import time

# Load .env from the parent directory
env_path = Path('..') / '.env'
load_dotenv(dotenv_path=env_path)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class TestUtils:
    @staticmethod
    def generate_temp_db_name():
        """
        Generates a unique temporary database name using the current timestamp.
        """
        timestamp = int(time.time())
        return f"test_db_{timestamp}"

    @staticmethod
    def download_sql_script():
        """
        Download the SQL schema script from GCP storage.
        """
        logger.debug("Downloading schema SQL script from GCP storage.")
        storage_client = storage.Client()
        bucket_name = os.getenv('MYSQL_FILES_BUCKET')
        bucket = storage_client.get_bucket(bucket_name)
        blob = bucket.blob('schema-tables.sql')
        sql_script_path = '/tmp/schema-tables.sql'
        blob.download_to_filename(sql_script_path)
        logger.debug(f"SQL script downloaded to {sql_script_path}")
        return sql_script_path

    @staticmethod
    def run_sql_script(sql_script_path, db_name):
        """
        Execute the SQL script to create the necessary tables in the specified database.
        """
        logger.debug(f"Connecting to MySQL and executing the SQL script on database: {db_name}")
        
        connection = pymysql.connect(
            host='127.0.0.1',  # Localhost as it's port-forwarded
            port=3306,  # MySQL default port as per your service YAML
            user='root',
            password=os.getenv('DB_ROOT_PASSWORD'),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True  # Ensure autocommit is enabled
        )
        
        with connection.cursor() as cursor:
            # Create the database and switch to it
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name};")
            cursor.execute(f"USE {db_name};")

            # Read the SQL script
            with open(sql_script_path, 'r') as f:
                sql_script = f.read()
            
            # Split the script by semicolons to execute each statement individually
            sql_commands = sql_script.split(';')
            
            # Execute each SQL command individually
            for command in sql_commands:
                if command.strip():  # Skip any empty lines
                    cursor.execute(command.strip())

            connection.commit()

        connection.close()
        logger.debug(f"SQL script executed successfully on database: {db_name}")


    @staticmethod
    def setup_test_app():
        """
        Creates and configures the Flask app and initializes the MySQL database for testing.
        Returns the Flask test client and the app instance.
        """
        app = create_app()
        app.config['TESTING'] = True

        # Generate a temporary test database name
        temp_db_name = TestUtils.generate_temp_db_name()

        # Hardcoded MySQL database URL with the dynamic database name
        app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://root:{os.getenv("DB_ROOT_PASSWORD")}@127.0.0.1:3306/{temp_db_name}'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        client = app.test_client()

        # Log the SQLAlchemy database URI
        logger.debug(f"Database URI used for testing: {app.config['SQLALCHEMY_DATABASE_URI']}")



        # Initialize the database
        with app.app_context():
            logger.debug(f"Creating all tables using the MySQL database: {temp_db_name}")

            # Download and execute the schema file
            sql_script_path = TestUtils.download_sql_script()
            TestUtils.run_sql_script(sql_script_path, temp_db_name)

        return client, app, temp_db_name

    @staticmethod
    def teardown_test_db(app, temp_db_name):
        """
        Drops the temporary database after tests are finished.
        """
        logger.debug(f"Dropping temporary database: {temp_db_name}")
        connection = pymysql.connect(
            host='127.0.0.1',  # Localhost as it's port-forwarded
            port=3306,  # MySQL default port
            user='root',
            password=os.getenv('DB_ROOT_PASSWORD'),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS {temp_db_name};")
            connection.commit()

        connection.close()
        logger.debug(f"Temporary database {temp_db_name} dropped successfully.")
