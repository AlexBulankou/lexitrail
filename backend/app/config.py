# /app/config.py

import os
from dotenv import load_dotenv
from pathlib import Path

class Config:
    if not os.getenv('KUBERNETES_SERVICE_HOST'):
        env_path = Path('..') / '.env'
        load_dotenv(dotenv_path=env_path)
    
    DB_ROOT_PASSWORD = os.getenv('DB_ROOT_PASSWORD', 'default_password')
    DATABASE_NAME = os.getenv('DATABASE_NAME', 'test_db')
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', 'default-client-id')
    # Guest ("try without sign-in") sessions mint UNAUTH_USER tokens whose email
    # must live under this domain. Enforced server-side so a guest token cannot
    # impersonate a real member. See AuthContext.tryWithoutSignin (frontend).
    DEMO_EMAIL_DOMAIN = os.getenv('DEMO_EMAIL_DOMAIN', 'lexitrail.demo')

    PROJECT_ID = os.getenv('PROJECT_ID', 'your-default-project-id')
    LOCATION = os.getenv('LOCATION', 'us-central1')
    PARALLELISM_LIMIT = int(os.getenv('PARALLELISM_LIMIT', 5))  # Default to 5

    if os.getenv('KUBERNETES_SERVICE_HOST'):
        SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:{}@mysql.{}.svc.cluster.local:3306/{}'.format(
            DB_ROOT_PASSWORD,
            os.getenv('SQL_NAMESPACE'),
            DATABASE_NAME
        )
    else:
        SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:{}@localhost:3306/{}'.format(
            DB_ROOT_PASSWORD,
            DATABASE_NAME
        )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # lexitrail#179: every prod 500 in a 14d window was a pooled connection the
    # server had already dropped, handed to a request as if live. The default
    # pool never validates a connection before checkout, so an idle connection
    # sitting past the server's wait_timeout comes back as (2006)/(2013).
    #
    # wait_timeout measured directly against mysql-0 (`SHOW VARIABLES LIKE
    # 'wait_timeout'`) on 2026-08-27: 28800s (8h, the MySQL default — the app
    # sets no server-side override). pool_recycle must stay comfortably under
    # that so SQLAlchemy retires a connection before the server does; 1800s
    # (30min) leaves a wide margin against a value that could itself drift.
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 1800,
    }


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = ''
    GOOGLE_CLIENT_ID = 'test-client-id'
