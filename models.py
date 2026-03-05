from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_napfa_member = db.Column(db.Boolean, default=False, nullable=False)
    napfa_join_date = db.Column(db.Date)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    reset_token = db.Column(db.String(100), unique=True, nullable=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)
    ce_records = db.relationship('CERecord', backref='user', lazy=True, cascade='all, delete-orphan')
    designations = db.relationship('UserDesignation', backref='user', lazy=True, cascade='all, delete-orphan')


class CERecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    provider = db.Column(db.String(200))
    hours = db.Column(db.Float, nullable=False)
    date_completed = db.Column(db.Date, nullable=False)
    category = db.Column(db.String(100))
    description = db.Column(db.Text)
    is_napfa_approved = db.Column(db.Boolean, default=False, nullable=False)
    is_ethics_course = db.Column(db.Boolean, default=False, nullable=False)
    napfa_subject_area = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class UserDesignation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    designation = db.Column(db.String(10), nullable=False)
    birth_month = db.Column(db.Integer)
    state = db.Column(db.String(2))
    last_reminder_sent = db.Column(db.DateTime, nullable=True)
    custom_period_end = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint('user_id', 'designation', name='unique_user_designation'),)


class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    target_user_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    admin = db.relationship('User', foreign_keys=[admin_id])


class PendingCERecord(db.Model):
    __tablename__ = 'pending_ce_record'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=True)
    provider = db.Column(db.String(200), nullable=True)
    hours = db.Column(db.Float, nullable=True)
    date_completed = db.Column(db.Date, nullable=True)
    category = db.Column(db.String(100), nullable=True)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending', nullable=False)
    source_email_subject = db.Column(db.String(300), nullable=True)
    source_email_from = db.Column(db.String(200), nullable=True)
    source_filename = db.Column(db.String(300), nullable=True)
    raw_extracted_text = db.Column(db.Text, nullable=True)
    extraction_confidence = db.Column(db.String(20), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    reviewed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref=db.backref('pending_records', lazy=True, cascade='all, delete-orphan'))


class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    feedback_type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
