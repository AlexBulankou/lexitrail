from flask_sqlalchemy import SQLAlchemy
import logging

# Create a logger for SQL queries
logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)

db = SQLAlchemy()

def init_db(app):
    db.init_app(app)

    # Automatically create tables if they don't exist
    #with app.app_context():
    #    db.create_all()
