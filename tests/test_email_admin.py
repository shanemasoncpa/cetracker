"""Tests for email helpers, admin user management, and audit logging."""
from unittest.mock import patch

ADMIN_KEY = 'cetracker2025admin'


# ── Helpers ──────────────────────────────────────────────────────────────────

def _create_admin_user(test_app):
    """Create an admin user and return their dict."""
    from werkzeug.security import generate_password_hash
    from models import db, User

    with test_app.app_context():
        admin = User(
            username='admin',
            email='admin@example.com',
            password_hash=generate_password_hash('admin123'),
            is_admin=True,
        )
        db.session.add(admin)
        db.session.commit()
        return {'id': admin.id, 'username': 'admin', 'password': 'admin123'}


def _create_regular_user(test_app, username='regularuser', email='regular@example.com'):
    """Create a non-admin user and return their dict."""
    from werkzeug.security import generate_password_hash
    from models import db, User

    with test_app.app_context():
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash('pass123'),
        )
        db.session.add(user)
        db.session.commit()
        return {'id': user.id, 'username': username, 'email': email, 'password': 'pass123'}


def _login(client, username, password):
    """Log in a user via the login form."""
    client.post('/login', data={'username': username, 'password': password})


# ── Email helper tests ───────────────────────────────────────────────────────

def test_send_email_returns_false_without_api_key(test_app):
    """send_email() returns False when RESEND_API_KEY is not set."""
    import email_helper
    original = email_helper.RESEND_API_KEY
    try:
        email_helper.RESEND_API_KEY = None
        result = email_helper.send_email('a@b.com', 'Subject', '<p>body</p>')
        assert result is False
    finally:
        email_helper.RESEND_API_KEY = original


# ── Email template tests ─────────────────────────────────────────────────────

def test_password_reset_email_content():
    """password_reset_email() returns HTML with username and reset URL."""
    from email_templates import password_reset_email
    html = password_reset_email('jdoe', 'https://example.com/reset/abc')
    assert isinstance(html, str)
    assert 'jdoe' in html
    assert 'https://example.com/reset/abc' in html
    assert 'Reset Your Password' in html
    assert '1 hour' in html


def test_welcome_email_content():
    """welcome_email() returns HTML with username and login URL."""
    from email_templates import welcome_email
    html = welcome_email('jdoe', 'https://example.com/login')
    assert isinstance(html, str)
    assert 'jdoe' in html
    assert 'https://example.com/login' in html
    assert 'Welcome to CE Logbook' in html


def test_deadline_reminder_email_content():
    """deadline_reminder_email() returns HTML with designation, hours, and date."""
    from email_templates import deadline_reminder_email
    html = deadline_reminder_email('jdoe', 'CFP', 12.5, 'May 31, 2026')
    assert isinstance(html, str)
    assert 'jdoe' in html
    assert 'CFP' in html
    assert '12.5' in html
    assert 'May 31, 2026' in html
    assert 'Deadline Reminder' in html


# ── Forgot password route ────────────────────────────────────────────────────

def test_forgot_password_existing_email_with_resend(client, sample_user):
    """Forgot password shows generic message when email sends successfully."""
    with patch('blueprints.auth.send_email', return_value=True):
        response = client.post('/forgot_password', data={
            'email': sample_user['email'],
        }, follow_redirects=True)
    assert b'If an account with that email exists' in response.data


def test_forgot_password_existing_email_without_resend(client, sample_user, test_app):
    """Forgot password falls back to direct reset page when Resend is not configured."""
    response = client.post('/forgot_password', data={
        'email': sample_user['email'],
    }, follow_redirects=False)
    # Dev fallback: redirects directly to reset_password page
    assert response.status_code == 302
    assert '/reset_password/' in response.headers['Location']


def test_forgot_password_generic_message_nonexistent_email(client):
    """Forgot password shows same generic message for non-existent email."""
    response = client.post('/forgot_password', data={
        'email': 'nobody@example.com',
    }, follow_redirects=True)
    assert b'If an account with that email exists' in response.data


# ── Admin toggle_active tests ────────────────────────────────────────────────

def test_toggle_active_deactivates_user(client, test_app):
    """POST /admin/toggle_active/<id> deactivates an active user."""
    admin = _create_admin_user(test_app)
    target = _create_regular_user(test_app)
    _login(client, admin['username'], admin['password'])

    response = client.post(
        f'/admin/toggle_active/{target["id"]}',
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b'deactivated' in response.data

    from models import db, User
    with test_app.app_context():
        user = db.session.get(User, target['id'])
        assert user.is_active is False


def test_toggle_active_reactivates_user(client, test_app):
    """Toggling twice re-activates the user."""
    admin = _create_admin_user(test_app)
    target = _create_regular_user(test_app)
    _login(client, admin['username'], admin['password'])

    # Deactivate
    client.post(f'/admin/toggle_active/{target["id"]}')
    # Reactivate
    response = client.post(
        f'/admin/toggle_active/{target["id"]}',
        follow_redirects=True,
    )
    assert b'activated' in response.data

    from models import db, User
    with test_app.app_context():
        user = db.session.get(User, target['id'])
        assert user.is_active is True


def test_toggle_active_prevents_self_deactivation(client, test_app):
    """Admin cannot deactivate their own account."""
    admin = _create_admin_user(test_app)
    _login(client, admin['username'], admin['password'])

    response = client.post(
        f'/admin/toggle_active/{admin["id"]}',
        follow_redirects=True,
    )
    assert b'cannot deactivate your own' in response.data

    from models import db, User
    with test_app.app_context():
        user = db.session.get(User, admin['id'])
        assert user.is_active is True


# ── Admin delete_user tests ──────────────────────────────────────────────────

def test_delete_user_removes_user_and_records(client, test_app):
    """POST /admin/delete_user/<id> deletes user and their CE records."""
    from models import db, User, CERecord
    from datetime import date

    admin = _create_admin_user(test_app)
    target = _create_regular_user(test_app)
    _login(client, admin['username'], admin['password'])

    # Add a CE record for the target user
    with test_app.app_context():
        record = CERecord(
            user_id=target['id'],
            title='Test CE',
            hours=2.0,
            date_completed=date(2026, 1, 15),
        )
        db.session.add(record)
        db.session.commit()

    response = client.post(
        f'/admin/delete_user/{target["id"]}',
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b'deleted' in response.data

    with test_app.app_context():
        assert db.session.get(User, target['id']) is None
        assert CERecord.query.filter_by(user_id=target['id']).count() == 0


def test_delete_user_prevents_self_deletion(client, test_app):
    """Admin cannot delete their own account."""
    admin = _create_admin_user(test_app)
    _login(client, admin['username'], admin['password'])

    response = client.post(
        f'/admin/delete_user/{admin["id"]}',
        follow_redirects=True,
    )
    assert b'cannot delete your own' in response.data

    from models import db, User
    with test_app.app_context():
        assert db.session.get(User, admin['id']) is not None


# ── Deactivated user cannot log in ───────────────────────────────────────────

def test_deactivated_user_cannot_login(client, test_app):
    """A user with is_active=False is blocked at login."""
    from models import db, User

    target = _create_regular_user(test_app)

    # Deactivate the user directly in the DB
    with test_app.app_context():
        user = db.session.get(User, target['id'])
        user.is_active = False
        db.session.commit()

    response = client.post('/login', data={
        'username': target['username'],
        'password': target['password'],
    }, follow_redirects=True)
    assert b'deactivated' in response.data


# ── Admin send_reminders test ────────────────────────────────────────────────

def test_send_reminders_returns_success(client, test_app):
    """POST /admin/send_reminders works and shows result flash."""
    admin = _create_admin_user(test_app)
    _login(client, admin['username'], admin['password'])

    with patch('deadline_checker.send_email', return_value=False):
        response = client.post(
            '/admin/send_reminders',
            follow_redirects=True,
        )
    assert response.status_code == 200
    assert b'Reminder check complete' in response.data


# ── Audit log tests ──────────────────────────────────────────────────────────

def test_admin_actions_create_audit_log_entries(client, test_app):
    """Admin actions (toggle_active, delete_user) create AuditLog entries."""
    from models import db, AuditLog

    admin = _create_admin_user(test_app)
    target = _create_regular_user(test_app)
    _login(client, admin['username'], admin['password'])

    # toggle_active should create an audit entry
    client.post(f'/admin/toggle_active/{target["id"]}')

    with test_app.app_context():
        logs = AuditLog.query.filter_by(action='toggle_active').all()
        assert len(logs) == 1
        assert logs[0].admin_id == admin['id']
        assert logs[0].target_user_id == target['id']
        assert 'deactivated' in logs[0].details

    # delete_user should create an audit entry
    client.post(f'/admin/delete_user/{target["id"]}')

    with test_app.app_context():
        logs = AuditLog.query.filter_by(action='delete_user').all()
        assert len(logs) == 1
        assert logs[0].admin_id == admin['id']
        assert logs[0].target_user_id == target['id']


def test_audit_log_page_loads_for_admin(client, test_app):
    """GET /admin/audit_log returns 200 for admin users."""
    admin = _create_admin_user(test_app)
    _login(client, admin['username'], admin['password'])

    response = client.get('/admin/audit_log')
    assert response.status_code == 200


def test_audit_log_page_rejects_non_admin(client, test_app):
    """GET /admin/audit_log redirects non-admin users."""
    target = _create_regular_user(test_app)
    _login(client, target['username'], target['password'])

    response = client.get('/admin/audit_log', follow_redirects=True)
    assert b'Unauthorized' in response.data
