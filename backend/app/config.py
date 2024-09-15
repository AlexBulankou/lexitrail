import os
from dotenv import load_dotenv
from pathlib import Path

# Check if the app is running in Kubernetes by checking for the 'KUBERNETES_SERVICE_HOST' environment variable
if not os.getenv('KUBERNETES_SERVICE_HOST'):
    # Load .env from the parent directory when not running in Kubernetes
    env_path = Path('..') / '.env'
    load_dotenv(dotenv_path=env_path)

class Config:
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:{}@mysql.{}.svc.cluster.local:3306/{}'.format(
        os.getenv('DB_ROOT_PASSWORD'),
        os.getenv('SQL_NAMESPACE'),
        os.getenv('DATABASE_NAME')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
