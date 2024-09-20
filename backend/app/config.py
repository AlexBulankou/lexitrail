import os
from dotenv import load_dotenv
from pathlib import Path

class Config:
    # Load environment variables from the .env file in local development
    if not os.getenv('KUBERNETES_SERVICE_HOST'):
        env_path = Path('..') / '.env'
        load_dotenv(dotenv_path=env_path)
    
    DB_ROOT_PASSWORD = os.getenv('DB_ROOT_PASSWORD', 'default_password')  # Default for testing
    DATABASE_NAME = os.getenv('DATABASE_NAME', 'test_db')  # Default for testing
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', 'default-client-id')  # Default value if not provided
    
    # Database URI for the actual app (used in production or Kubernetes)
    if os.getenv('KUBERNETES_SERVICE_HOST'):
        # Kubernetes environment, use Kubernetes DNS
        SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:{}@mysql.{}.svc.cluster.local:3306/{}'.format(
            DB_ROOT_PASSWORD,
            os.getenv('SQL_NAMESPACE'),
            DATABASE_NAME
        )
    else:
        # Local development, use localhost
        SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:{}@localhost:3306/{}'.format(
            DB_ROOT_PASSWORD,
            DATABASE_NAME
        )
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class TestConfig(Config):
    TESTING = True
    # Database URI dynamically set for each test
    SQLALCHEMY_DATABASE_URI = ''  # To be set dynamically in test utils
    GOOGLE_CLIENT_ID = 'test-client-id'  # Set a dummy client ID for testing
