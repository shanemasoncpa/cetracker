"""Smoke tests for all routes - verify pages load and auth guards work."""
from datetime import date
import io
import json


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


# ── CSV Import Tests ──────────────────────────────────────────────────────────


def _make_csv(content: str) -> io.BytesIO:
    """Helper: wrap a CSV string into a BytesIO with a .csv filename."""
    data = io.BytesIO(content.encode('utf-8'))
    data.name = 'import.csv'
    return data


def test_import_ce_requires_login(client):
    """Import route redirects to login when not authenticated."""
    csv_data = _make_csv("Title,Hours\nTest,1.0\n")
    response = client.post('/import_ce', data={
        'csv_file': (csv_data, 'import.csv'),
    }, content_type='multipart/form-data')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_import_valid_csv(logged_in_client, test_app):
    """Import a well-formed CSV and verify records are created."""
    csv_content = (
        "Date Completed,Title,Provider,Category,Hours,Description\n"
        "2026-01-15,Ethics Refresher,AICPA,Ethics,2.0,Annual ethics course\n"
        "2026-02-10,Tax Update 2026,CPE Provider,Tax,4.5,Tax law changes\n"
    )
    csv_data = _make_csv(csv_content)
    response = logged_in_client.post('/import_ce', data={
        'csv_file': (csv_data, 'import.csv'),
    }, content_type='multipart/form-data', follow_redirects=True)

    assert b'Successfully imported 2 CE record' in response.data

    from models import CERecord
    with test_app.app_context():
        records = CERecord.query.order_by(CERecord.title).all()
        assert len(records) == 2
        ethics = next(r for r in records if r.title == 'Ethics Refresher')
        assert ethics.hours == 2.0
        assert ethics.provider == 'AICPA'
        assert ethics.category == 'Ethics'
        assert ethics.date_completed == date(2026, 1, 15)

        tax = next(r for r in records if r.title == 'Tax Update 2026')
        assert tax.hours == 4.5


def test_import_flexible_column_names(logged_in_client, test_app):
    """Import recognizes alternate column names (Course Name, Credits, etc.)."""
    csv_content = (
        "Course Name,Credits,Sponsor,Type\n"
        "Retirement Planning,3.0,NAPFA,Financial Planning\n"
    )
    csv_data = _make_csv(csv_content)
    response = logged_in_client.post('/import_ce', data={
        'csv_file': (csv_data, 'import.csv'),
    }, content_type='multipart/form-data', follow_redirects=True)

    assert b'Successfully imported 1 CE record' in response.data

    from models import CERecord
    with test_app.app_context():
        record = CERecord.query.filter_by(title='Retirement Planning').first()
        assert record is not None
        assert record.hours == 3.0
        assert record.provider == 'NAPFA'
        assert record.category == 'Financial Planning'


def test_import_missing_required_columns(logged_in_client):
    """CSV without Title or Hours column is rejected."""
    csv_content = "Date,Provider,Category\n2026-01-01,AICPA,Ethics\n"
    csv_data = _make_csv(csv_content)
    response = logged_in_client.post('/import_ce', data={
        'csv_file': (csv_data, 'import.csv'),
    }, content_type='multipart/form-data', follow_redirects=True)

    assert b'must have at least' in response.data.lower()


def test_import_missing_title_column_only(logged_in_client):
    """CSV with Hours but no Title column is rejected."""
    csv_content = "Hours,Provider\n2.0,AICPA\n"
    csv_data = _make_csv(csv_content)
    response = logged_in_client.post('/import_ce', data={
        'csv_file': (csv_data, 'import.csv'),
    }, content_type='multipart/form-data', follow_redirects=True)

    assert b'must have at least' in response.data.lower()


def test_import_skips_duplicates(logged_in_client, test_app, sample_user):
    """Rows matching an existing record (title + date + hours) are skipped."""
    from models import CERecord, db
    with test_app.app_context():
        existing = CERecord(
            user_id=sample_user['id'],
            title='Already Exists',
            hours=2.0,
            date_completed=date(2026, 1, 15),
            description='',
        )
        db.session.add(existing)
        db.session.commit()

    csv_content = (
        "Title,Hours,Date Completed\n"
        "Already Exists,2.0,2026-01-15\n"
        "New Course,3.0,2026-03-01\n"
    )
    csv_data = _make_csv(csv_content)
    response = logged_in_client.post('/import_ce', data={
        'csv_file': (csv_data, 'import.csv'),
    }, content_type='multipart/form-data', follow_redirects=True)

    assert b'Successfully imported 1 CE record' in response.data
    assert b'1 row skipped' in response.data

    from models import CERecord as CR
    with test_app.app_context():
        total = CR.query.filter_by(user_id=sample_user['id']).count()
        assert total == 2  # 1 existing + 1 new


def test_import_bad_date_falls_back_to_today(logged_in_client, test_app):
    """Unparseable dates fall back to today with a warning."""
    csv_content = (
        "Title,Hours,Date Completed\n"
        "Bad Date Course,1.5,not-a-date\n"
    )
    csv_data = _make_csv(csv_content)
    response = logged_in_client.post('/import_ce', data={
        'csv_file': (csv_data, 'import.csv'),
    }, content_type='multipart/form-data', follow_redirects=True)

    assert b'Successfully imported 1 CE record' in response.data
    assert b'Could not parse date' in response.data

    from models import CERecord
    from datetime import date as dt_date
    with test_app.app_context():
        record = CERecord.query.filter_by(title='Bad Date Course').first()
        assert record is not None
        assert record.date_completed == dt_date.today()


def test_import_various_date_formats(logged_in_client, test_app):
    """Import handles multiple date formats (MM/DD/YYYY, MM-DD-YYYY, etc.)."""
    csv_content = (
        "Title,Hours,Date Completed\n"
        "Course A,1.0,01/15/2026\n"
        "Course B,1.0,01-15-2026\n"
        "Course C,1.0,2026/01/15\n"
    )
    csv_data = _make_csv(csv_content)
    response = logged_in_client.post('/import_ce', data={
        'csv_file': (csv_data, 'import.csv'),
    }, content_type='multipart/form-data', follow_redirects=True)

    assert b'Successfully imported 3 CE record' in response.data

    from models import CERecord
    with test_app.app_context():
        records = CERecord.query.order_by(CERecord.title).all()
        assert len(records) == 3
        # All three should parse to Jan 15, 2026
        for r in records:
            assert r.date_completed == date(2026, 1, 15)


def test_import_skips_blank_rows(logged_in_client, test_app):
    """Rows where both title and hours are empty are silently skipped."""
    csv_content = (
        "Title,Hours,Date Completed\n"
        "Real Course,2.0,2026-01-15\n"
        ",,\n"
        " , , \n"
        "Another Course,1.5,2026-02-01\n"
    )
    csv_data = _make_csv(csv_content)
    response = logged_in_client.post('/import_ce', data={
        'csv_file': (csv_data, 'import.csv'),
    }, content_type='multipart/form-data', follow_redirects=True)

    assert b'Successfully imported 2 CE record' in response.data

    from models import CERecord
    with test_app.app_context():
        assert CERecord.query.count() == 2


def test_import_row_missing_title(logged_in_client, test_app):
    """A row with hours but no title is skipped with an error note."""
    csv_content = (
        "Title,Hours,Date Completed\n"
        ",3.0,2026-01-15\n"
        "Valid Course,1.0,2026-02-01\n"
    )
    csv_data = _make_csv(csv_content)
    response = logged_in_client.post('/import_ce', data={
        'csv_file': (csv_data, 'import.csv'),
    }, content_type='multipart/form-data', follow_redirects=True)

    assert b'Successfully imported 1 CE record' in response.data
    assert b'1 row skipped' in response.data
    assert b'Missing title' in response.data


def test_import_invalid_hours(logged_in_client, test_app):
    """A row with non-numeric hours is skipped with an error note."""
    csv_content = (
        "Title,Hours\n"
        "Good Course,2.0\n"
        "Bad Course,abc\n"
        "Zero Course,0\n"
    )
    csv_data = _make_csv(csv_content)
    response = logged_in_client.post('/import_ce', data={
        'csv_file': (csv_data, 'import.csv'),
    }, content_type='multipart/form-data', follow_redirects=True)

    assert b'Successfully imported 1 CE record' in response.data
    assert b'2 rows skipped' in response.data

    from models import CERecord
    with test_app.app_context():
        assert CERecord.query.count() == 1
        assert CERecord.query.first().title == 'Good Course'


def test_import_no_file_selected(logged_in_client):
    """Posting to import with no file flashes an error."""
    response = logged_in_client.post('/import_ce', data={},
                                     content_type='multipart/form-data',
                                     follow_redirects=True)
    assert b'No file selected' in response.data


def test_import_non_csv_file(logged_in_client):
    """Uploading a non-CSV file is rejected."""
    data = io.BytesIO(b"not a csv")
    response = logged_in_client.post('/import_ce', data={
        'csv_file': (data, 'report.xlsx'),
    }, content_type='multipart/form-data', follow_redirects=True)

    assert b'Please upload a CSV file' in response.data


def test_import_empty_csv(logged_in_client):
    """A CSV file with no data rows (only headers) imports 0 records."""
    csv_content = "Title,Hours,Date Completed\n"
    csv_data = _make_csv(csv_content)
    response = logged_in_client.post('/import_ce', data={
        'csv_file': (csv_data, 'import.csv'),
    }, content_type='multipart/form-data', follow_redirects=True)

    assert b'Successfully imported 0 CE records' in response.data


# ── JSON Backup Export Tests ──────────────────────────────────────────────────


def test_export_backup_requires_login(client):
    """Backup route redirects to login when not authenticated."""
    response = client.get('/export_backup')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_export_backup_returns_json(logged_in_client):
    """Backup returns valid JSON with correct headers."""
    response = logged_in_client.get('/export_backup')
    assert response.status_code == 200
    assert response.content_type == 'application/json'
    assert 'attachment' in response.headers['Content-Disposition']
    assert 'ce_tracker_backup_' in response.headers['Content-Disposition']
    assert response.headers['Content-Disposition'].endswith('.json')

    data = json.loads(response.data)
    assert 'exported_at' in data


def test_export_backup_contains_user_info(logged_in_client, sample_user):
    """Backup JSON includes correct user details."""
    response = logged_in_client.get('/export_backup')
    data = json.loads(response.data)

    assert 'user' in data
    assert data['user']['username'] == sample_user['username']
    assert data['user']['email'] == sample_user['email']
    assert data['user']['is_napfa_member'] is False
    assert data['user']['napfa_join_date'] is None


def test_export_backup_contains_designations(logged_in_client, test_app, sample_user):
    """Backup JSON includes user designations."""
    from models import UserDesignation, db
    with test_app.app_context():
        desig = UserDesignation(
            user_id=sample_user['id'],
            designation='EA',
        )
        db.session.add(desig)
        db.session.commit()

    response = logged_in_client.get('/export_backup')
    data = json.loads(response.data)

    assert 'designations' in data
    assert len(data['designations']) == 1
    assert data['designations'][0]['designation'] == 'EA'
    assert data['designations'][0]['birth_month'] is None
    assert data['designations'][0]['state'] is None


def test_export_backup_contains_ce_records(logged_in_client, test_app, sample_user):
    """Backup JSON includes CE records with all expected fields."""
    from models import CERecord, db
    with test_app.app_context():
        record = CERecord(
            user_id=sample_user['id'],
            title='Ethics Annual',
            provider='AICPA',
            hours=2.0,
            date_completed=date(2026, 1, 15),
            category='Ethics',
            description='Annual ethics refresher',
            is_napfa_approved=True,
            is_ethics_course=True,
            napfa_subject_area='Ethics',
        )
        db.session.add(record)
        db.session.commit()

    response = logged_in_client.get('/export_backup')
    data = json.loads(response.data)

    assert 'ce_records' in data
    assert len(data['ce_records']) == 1

    rec = data['ce_records'][0]
    assert rec['title'] == 'Ethics Annual'
    assert rec['provider'] == 'AICPA'
    assert rec['hours'] == 2.0
    assert rec['date_completed'] == '2026-01-15'
    assert rec['category'] == 'Ethics'
    assert rec['description'] == 'Annual ethics refresher'
    assert rec['is_napfa_approved'] is True
    assert rec['is_ethics_course'] is True
    assert rec['napfa_subject_area'] == 'Ethics'
