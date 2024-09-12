import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env from the parent directory
env_path = Path('..') / '.env'
load_dotenv(dotenv_path=env_path)

class Config:
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:{}@mysql.{}.svc.cluster.local:3306/{}'.format(
        os.getenv('DB_ROOT_PASSWORD'),
        os.getenv('SQL_NAMESPACE'),
        os.getenv('DATABASE_NAME')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
