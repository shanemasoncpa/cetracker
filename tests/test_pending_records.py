"""Tests for pending CE records: review page, approve, reject, dashboard count, PDF extractor."""
import sys
import json
from datetime import date
from unittest.mock import patch, MagicMock

from models import db, PendingCERecord, CERecord, User


# ── Helpers ──────────────────────────────────────────────────────────────────

def _create_pending_record(test_app, user_id, **overrides):
    """Create a PendingCERecord and return its id."""
    defaults = dict(
        user_id=user_id,
        title='Test Course',
        provider='Test Provider',
        hours=2.0,
        date_completed=date(2026, 1, 15),
        category='Ethics',
        description='Test description',
        extraction_confidence='high',
        source_email_subject='Your CE Certificate',
    )
    defaults.update(overrides)

    with test_app.app_context():
        pending = PendingCERecord(**defaults)
        db.session.add(pending)
        db.session.commit()
        return pending.id


def _create_other_user(test_app):
    """Create a second user distinct from the sample_user fixture."""
    from werkzeug.security import generate_password_hash

    with test_app.app_context():
        user = User(
            username='otheruser',
            email='other@example.com',
            password_hash=generate_password_hash('otherpass123'),
        )
        db.session.add(user)
        db.session.commit()
        return {'id': user.id, 'username': 'otheruser', 'password': 'otherpass123'}


# ── Pending records page tests ──────────────────────────────────────────────

def test_pending_records_requires_login(client):
    """GET /pending without login redirects to login."""
    response = client.get('/pending', follow_redirects=True)
    assert response.status_code == 200
    assert b'log in' in response.data.lower()


def test_pending_records_empty(logged_in_client, test_app):
    """GET /pending with no records returns 200 and shows empty state message."""
    response = logged_in_client.get('/pending')
    assert response.status_code == 200
    assert b'No pending records' in response.data or b'No pending' in response.data


def test_pending_records_shows_records(logged_in_client, test_app, sample_user):
    """GET /pending shows the pending record's title when one exists."""
    _create_pending_record(test_app, sample_user['id'], title='Advanced Tax Planning')

    response = logged_in_client.get('/pending')
    assert response.status_code == 200
    assert b'Advanced Tax Planning' in response.data


# ── Approve tests ────────────────────────────────────────────────────────────

def test_approve_pending_record(logged_in_client, test_app, sample_user):
    """Approving a pending record creates a CERecord and updates status."""
    record_id = _create_pending_record(test_app, sample_user['id'])

    response = logged_in_client.post(f'/pending/{record_id}/approve', data={
        'title': 'Approved Course',
        'provider': 'AICPA',
        'hours': '3.0',
        'date_completed': '2026-01-15',
        'category': 'Ethics',
        'description': 'Approved description',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'approved' in response.data.lower()

    with test_app.app_context():
        pending = db.session.get(PendingCERecord, record_id)
        assert pending.status == 'approved'
        assert pending.reviewed_at is not None

        ce = CERecord.query.filter_by(title='Approved Course').first()
        assert ce is not None
        assert ce.hours == 3.0
        assert ce.provider == 'AICPA'
        assert ce.category == 'Ethics'
        assert ce.user_id == sample_user['id']


def test_approve_requires_all_fields(logged_in_client, test_app, sample_user):
    """Approving with missing title flashes an error and creates no CERecord."""
    record_id = _create_pending_record(test_app, sample_user['id'])

    response = logged_in_client.post(f'/pending/{record_id}/approve', data={
        'title': '',
        'provider': 'AICPA',
        'hours': '3.0',
        'date_completed': '2026-01-15',
        'category': 'Ethics',
        'description': '',
    }, follow_redirects=True)
    assert response.status_code == 200
    # Should flash an error about required fields
    assert b'required' in response.data.lower() or b'error' in response.data.lower()

    with test_app.app_context():
        count = CERecord.query.filter_by(user_id=sample_user['id']).count()
        assert count == 0


def test_approve_wrong_user(client, test_app, sample_user):
    """A user cannot approve another user's pending record."""
    # Create a pending record for sample_user
    record_id = _create_pending_record(test_app, sample_user['id'])

    # Create and log in as a different user
    other = _create_other_user(test_app)
    client.post('/login', data={
        'username': other['username'],
        'password': other['password'],
    })

    response = client.post(f'/pending/{record_id}/approve', data={
        'title': 'Stolen Course',
        'provider': 'Evil Provider',
        'hours': '99.0',
        'date_completed': '2026-01-15',
        'category': 'Ethics',
        'description': '',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'permission' in response.data.lower()

    # Verify no CERecord was created
    with test_app.app_context():
        ce = CERecord.query.filter_by(title='Stolen Course').first()
        assert ce is None


# ── Reject tests ─────────────────────────────────────────────────────────────

def test_reject_pending_record(logged_in_client, test_app, sample_user):
    """Rejecting a pending record sets status to 'rejected' and reviewed_at."""
    record_id = _create_pending_record(test_app, sample_user['id'])

    response = logged_in_client.post(f'/pending/{record_id}/reject', follow_redirects=True)
    assert response.status_code == 200
    assert b'rejected' in response.data.lower() or b'Rejected' in response.data

    with test_app.app_context():
        pending = db.session.get(PendingCERecord, record_id)
        assert pending.status == 'rejected'
        assert pending.reviewed_at is not None


def test_reject_wrong_user(client, test_app, sample_user):
    """A user cannot reject another user's pending record."""
    record_id = _create_pending_record(test_app, sample_user['id'])

    other = _create_other_user(test_app)
    client.post('/login', data={
        'username': other['username'],
        'password': other['password'],
    })

    response = client.post(f'/pending/{record_id}/reject', follow_redirects=True)
    assert response.status_code == 200
    assert b'permission' in response.data.lower()

    # Status should remain 'pending'
    with test_app.app_context():
        pending = db.session.get(PendingCERecord, record_id)
        assert pending.status == 'pending'


# ── Dashboard pending count test ─────────────────────────────────────────────

def test_dashboard_shows_pending_count(logged_in_client, test_app, sample_user):
    """Dashboard shows the count of pending records when they exist."""
    _create_pending_record(test_app, sample_user['id'], title='Pending One')
    _create_pending_record(test_app, sample_user['id'], title='Pending Two')

    response = logged_in_client.get('/dashboard')
    assert response.status_code == 200
    assert b'2' in response.data
    assert b'pending' in response.data.lower()


# ── PDF extractor tests ──────────────────────────────────────────────────────
#
# pdfplumber and anthropic may not be installed in the test environment,
# so we mock them at the sys.modules level before importing pdf_extractor.
#

def _get_pdf_extractor():
    """Import pdf_extractor with pdfplumber mocked if it's not installed."""
    # Remove cached module so we get a fresh import with mocks active
    sys.modules.pop('pdf_extractor', None)

    needs_pdfplumber_mock = 'pdfplumber' not in sys.modules
    if needs_pdfplumber_mock:
        mock_pdfplumber = MagicMock()
        # Make pdfplumber.open() raise on invalid bytes (mimics real behavior)
        mock_pdfplumber.open.side_effect = Exception('Invalid PDF')
        sys.modules['pdfplumber'] = mock_pdfplumber

    import pdf_extractor
    return pdf_extractor


def test_extract_text_from_pdf_empty_bytes():
    """extract_text_from_pdf returns empty string for invalid bytes."""
    pdf_extractor = _get_pdf_extractor()
    result = pdf_extractor.extract_text_from_pdf(b'this is not a valid pdf')
    assert result == ''


def test_extract_ce_data_without_api_key(test_app):
    """extract_ce_data_from_text returns error when ANTHROPIC_API_KEY is not set."""
    pdf_extractor = _get_pdf_extractor()

    original = pdf_extractor.ANTHROPIC_API_KEY
    try:
        pdf_extractor.ANTHROPIC_API_KEY = None
        result = pdf_extractor.extract_ce_data_from_text('Some CE certificate text')
        assert isinstance(result, dict)
        assert result['error_message'] is not None
        assert 'not configured' in result['error_message'].lower()
        assert result['title'] is None
    finally:
        pdf_extractor.ANTHROPIC_API_KEY = original


def test_extract_ce_data_with_mocked_api(test_app):
    """extract_ce_data_from_text returns parsed fields when the API responds."""
    pdf_extractor = _get_pdf_extractor()

    mock_response_json = {
        'title': 'Ethics in Financial Planning',
        'provider': 'CFP Board',
        'hours': 2.0,
        'date_completed': '2026-01-15',
        'category': 'Ethics',
        'description': 'A course on ethics in financial planning.',
        'confidence': 'high',
    }

    # Build a mock that mimics anthropic.Anthropic().messages.create()
    mock_content_block = MagicMock()
    mock_content_block.text = '```json\n' + json.dumps(mock_response_json) + '\n```'

    mock_response = MagicMock()
    mock_response.content = [mock_content_block]

    mock_client_instance = MagicMock()
    mock_client_instance.messages.create.return_value = mock_response

    mock_anthropic_class = MagicMock(return_value=mock_client_instance)

    # Mock the anthropic module at sys.modules level so the local import works
    mock_anthropic_module = MagicMock()
    mock_anthropic_module.Anthropic = mock_anthropic_class

    original_key = pdf_extractor.ANTHROPIC_API_KEY
    try:
        pdf_extractor.ANTHROPIC_API_KEY = 'fake-key-for-testing'

        with patch.dict('sys.modules', {'anthropic': mock_anthropic_module}):
            result = pdf_extractor.extract_ce_data_from_text(
                'Certificate of Completion - Ethics in Financial Planning',
                email_subject='Your CE Certificate',
            )

        assert isinstance(result, dict)
        assert result['title'] == 'Ethics in Financial Planning'
        assert result['provider'] == 'CFP Board'
        assert result['hours'] == 2.0
        assert result['date_completed'] == '2026-01-15'
        assert result['category'] == 'Ethics'
        assert result['confidence'] == 'high'
        assert result['error_message'] is None
    finally:
        pdf_extractor.ANTHROPIC_API_KEY = original_key


# ── /extract_pdf endpoint tests ─────────────────────────────────────────────

def test_extract_pdf_requires_login(client):
    """/extract_pdf returns 401 when not logged in."""
    response = client.post('/extract_pdf')
    assert response.status_code == 401
    data = response.get_json()
    assert 'error' in data


def test_extract_pdf_requires_file(logged_in_client):
    """/extract_pdf returns 400 when no file is provided."""
    with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'fake-key'}):
        response = logged_in_client.post('/extract_pdf')
        data = response.get_json()
        assert response.status_code == 400
        assert 'No file' in data['error']


def test_extract_pdf_rejects_invalid_type(logged_in_client):
    """/extract_pdf rejects non-PDF/image files."""
    import io
    data = {'file': (io.BytesIO(b'hello'), 'test.txt')}
    with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'fake-key'}):
        response = logged_in_client.post('/extract_pdf', data=data, content_type='multipart/form-data')
    assert response.status_code == 400
    assert 'PDF or image' in response.get_json()['error']


def test_extract_pdf_no_api_key(logged_in_client):
    """/extract_pdf returns 503 when ANTHROPIC_API_KEY is not set."""
    import io
    data = {'file': (io.BytesIO(b'%PDF-1.4 fake'), 'cert.pdf')}
    with patch.dict('os.environ', {}, clear=False):
        # Ensure ANTHROPIC_API_KEY is not set
        import os
        original = os.environ.pop('ANTHROPIC_API_KEY', None)
        try:
            response = logged_in_client.post('/extract_pdf', data=data, content_type='multipart/form-data')
            resp_data = response.get_json()
            assert response.status_code == 503
            assert 'ANTHROPIC_API_KEY' in resp_data['error']
        finally:
            if original is not None:
                os.environ['ANTHROPIC_API_KEY'] = original


def test_extract_pdf_success(logged_in_client):
    """/extract_pdf returns extracted CE data on success."""
    import io

    mock_response_json = {
        'title': 'Tax Planning Webinar',
        'provider': 'IRS',
        'hours': 1.5,
        'date_completed': '2026-02-10',
        'category': 'Taxation',
        'description': 'Annual tax update',
        'confidence': 'high',
    }

    mock_content_block = MagicMock()
    mock_content_block.text = json.dumps(mock_response_json)

    mock_response = MagicMock()
    mock_response.content = [mock_content_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client

    data = {'file': (io.BytesIO(b'%PDF-1.4 fake pdf content'), 'certificate.pdf')}

    with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'fake-key'}):
        with patch.dict('sys.modules', {'anthropic': mock_anthropic}):
            response = logged_in_client.post('/extract_pdf', data=data, content_type='multipart/form-data')

    assert response.status_code == 200
    result = response.get_json()
    assert result['title'] == 'Tax Planning Webinar'
    assert result['provider'] == 'IRS'
    assert result['hours'] == 1.5
    assert result['confidence'] == 'high'
