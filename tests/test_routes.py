"""Smoke tests for all routes - verify pages load and auth guards work."""
from datetime import date


def test_index_redirects(client):
    response = client.get('/')
    assert response.status_code == 302


def test_dashboard_loads_when_logged_in(logged_in_client):
    response = logged_in_client.get('/dashboard')
    assert response.status_code == 200
    assert b'CE Records' in response.data


def test_add_ce_page_loads(logged_in_client):
    response = logged_in_client.get('/add_ce')
    assert response.status_code == 200


def test_add_ce_creates_record(logged_in_client, test_app):
    response = logged_in_client.post('/add_ce', data={
        'title': 'Test CE Course',
        'provider': 'Test Provider',
        'hours': '2.0',
        'date_completed': '2026-01-15',
        'category': 'Financial Planning',
        'description': 'A test course',
    }, follow_redirects=True)
    assert b'CE record added successfully' in response.data

    from models import CERecord
    with test_app.app_context():
        record = CERecord.query.filter_by(title='Test CE Course').first()
        assert record is not None
        assert record.hours == 2.0


def test_delete_ce_record(logged_in_client, test_app, sample_user):
    # Create a record first
    from models import CERecord, db
    with test_app.app_context():
        record = CERecord(
            user_id=sample_user['id'],
            title='To Delete',
            hours=1.0,
            date_completed=date(2026, 1, 1),
        )
        db.session.add(record)
        db.session.commit()
        record_id = record.id

    response = logged_in_client.post(f'/delete_ce/{record_id}', follow_redirects=True)
    assert b'deleted successfully' in response.data


def test_edit_ce_record(logged_in_client, test_app, sample_user):
    from models import CERecord, db
    with test_app.app_context():
        record = CERecord(
            user_id=sample_user['id'],
            title='Original Title',
            hours=1.0,
            date_completed=date(2026, 1, 1),
        )
        db.session.add(record)
        db.session.commit()
        record_id = record.id

    response = logged_in_client.post(f'/edit_ce/{record_id}', data={
        'title': 'Updated Title',
        'provider': 'Updated Provider',
        'hours': '3.0',
        'date_completed': '2026-02-01',
        'category': 'Ethics',
        'description': 'Updated description',
    }, follow_redirects=True)
    assert b'updated successfully' in response.data


def test_export_csv(logged_in_client, test_app, sample_user):
    from models import CERecord, db
    with test_app.app_context():
        record = CERecord(
            user_id=sample_user['id'],
            title='Export Test',
            hours=2.0,
            date_completed=date(2026, 1, 1),
            category='Ethics',
        )
        db.session.add(record)
        db.session.commit()

    response = logged_in_client.get('/export_ce')
    assert response.status_code == 200
    assert response.content_type == 'text/csv; charset=utf-8'
    assert b'Export Test' in response.data


def test_export_csv_with_filter(logged_in_client, test_app, sample_user):
    response = logged_in_client.get('/export_ce?category=Ethics')
    assert response.status_code == 200


def test_manage_designations_page_loads(logged_in_client):
    response = logged_in_client.get('/manage_designations')
    assert response.status_code == 200


def test_add_designation(logged_in_client):
    response = logged_in_client.post('/manage_designations', data={
        'action': 'add',
        'designation': 'EA',
    }, follow_redirects=True)
    assert b'added successfully' in response.data


def test_profile_page_loads(logged_in_client):
    response = logged_in_client.get('/profile')
    assert response.status_code == 200


def test_update_email(logged_in_client):
    response = logged_in_client.post('/profile', data={
        'action': 'update_email',
        'email': 'newemail@example.com',
    }, follow_redirects=True)
    assert b'Email updated' in response.data


def test_change_password(logged_in_client, sample_user):
    response = logged_in_client.post('/profile', data={
        'action': 'change_password',
        'current_password': sample_user['password'],
        'new_password': 'newpass123',
        'confirm_password': 'newpass123',
    }, follow_redirects=True)
    assert b'Password changed' in response.data


def test_submit_feedback(logged_in_client):
    response = logged_in_client.post('/submit_feedback', data={
        'feedback_name': 'Test User',
        'feedback_email': 'test@example.com',
        'feedback_type': 'general',
        'feedback_message': 'This is a test feedback message.',
    }, follow_redirects=True)
    assert b'Thank you for your feedback' in response.data


def test_admin_feedback_requires_key(client):
    response = client.get('/admin/feedback', follow_redirects=True)
    assert b'Unauthorized' in response.data


def test_admin_feedback_with_key(client):
    response = client.get('/admin/feedback?key=cetracker2025admin')
    assert response.status_code == 200


def test_cannot_delete_other_users_record(logged_in_client, test_app):
    from models import User, CERecord, db
    from werkzeug.security import generate_password_hash

    with test_app.app_context():
        other_user = User(
            username='otheruser',
            email='other@example.com',
            password_hash=generate_password_hash('password123'),
        )
        db.session.add(other_user)
        db.session.commit()

        record = CERecord(
            user_id=other_user.id,
            title='Other Record',
            hours=1.0,
            date_completed=date(2026, 1, 1),
        )
        db.session.add(record)
        db.session.commit()
        record_id = record.id

    response = logged_in_client.post(f'/delete_ce/{record_id}', follow_redirects=True)
    assert b'permission' in response.data.lower()
