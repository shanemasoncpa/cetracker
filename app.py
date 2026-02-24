from flask import Flask
from sqlalchemy import text
import os

from models import db, User, CERecord, UserDesignation, Feedback

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Database configuration
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ce_tracker.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Register blueprints
from blueprints.auth import auth_bp
from blueprints.ce_records import ce_bp
from blueprints.admin import admin_bp
from blueprints.designations import designations_bp
from blueprints.profile import profile_bp

app.register_blueprint(auth_bp)
app.register_blueprint(ce_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(designations_bp)
app.register_blueprint(profile_bp)


def update_database_schema():
    """Add missing columns to existing database if they don't exist."""
    with app.app_context():
        is_postgresql = 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI'].lower()
        boolean_default = 'FALSE' if is_postgresql else '0'

        # Add is_admin column to users table
        try:
            db.session.execute(text('SELECT is_admin FROM users LIMIT 1'))
        except Exception:
            try:
                db.session.execute(text(f'ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT {boolean_default} NOT NULL'))
                db.session.commit()
                print("Added is_admin column to users table.")
            except Exception as e:
                db.session.rollback()
                error_msg = str(e).lower()
                if "already exists" not in error_msg and "duplicate" not in error_msg:
                    print(f"Error adding is_admin column: {e}")

        # Add other missing columns (backward compatibility for older databases)
        columns_to_add = [
            ('users', 'is_napfa_member', f'BOOLEAN DEFAULT {boolean_default} NOT NULL'),
            ('users', 'napfa_join_date', 'DATE'),
            ('users', 'reset_token', 'VARCHAR(100)'),
            ('users', 'reset_token_expiry', 'TIMESTAMP' if is_postgresql else 'DATETIME'),
            ('user_designation', 'birth_month', 'INTEGER'),
            ('user_designation', 'state', 'VARCHAR(2)'),
            ('ce_record', 'is_napfa_approved', f'BOOLEAN DEFAULT {boolean_default} NOT NULL'),
            ('ce_record', 'is_ethics_course', f'BOOLEAN DEFAULT {boolean_default} NOT NULL'),
            ('ce_record', 'napfa_subject_area', 'VARCHAR(100)'),
            ('feedback', 'is_read', f'BOOLEAN DEFAULT {boolean_default} NOT NULL'),
        ]

        for table, column, col_type in columns_to_add:
            try:
                db.session.execute(text(f'SELECT {column} FROM {table} LIMIT 1'))
            except Exception:
                try:
                    db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}'))
                    db.session.commit()
                except Exception:
                    db.session.rollback()

        print("Database schema is up to date.")


def init_db():
    with app.app_context():
        print(f"Database URI: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
        db.create_all()
        update_database_schema()
        print("Database initialization complete!")


init_db()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
