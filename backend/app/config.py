import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env from the parent directory
env_path = Path('..') / '.env'
load_dotenv(dotenv_path=env_path)

class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
