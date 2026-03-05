"""Tests for the inbound email webhook and pending record email template."""
import json
from unittest.mock import patch, MagicMock

from models import db, PendingCERecord


# ── Email template test ─────────────────────────────────────────────────────

def test_pending_record_email_content():
    """pending_record_email() returns HTML with username, course title, Review, and heading."""
    from email_templates import pending_record_email

    html = pending_record_email('jdoe', 'Ethics 101')
    assert isinstance(html, str)
    assert 'jdoe' in html
    assert 'Ethics 101' in html
    assert 'Review' in html
    assert 'New CE Record' in html


# ── Webhook endpoint tests ──────────────────────────────────────────────────

def test_webhook_rejects_invalid_json(client):
    """POST /inbound/webhook with non-JSON body returns 400."""
    response = client.post(
        '/inbound/webhook',
        data='this is not json',
        content_type='application/json',
    )
    assert response.status_code == 400
    data = response.get_json()
    assert 'error' in data


def test_webhook_ignores_non_email_received(client):
    """POST with a non-email.received event type returns 200 with 'ignored'."""
    with patch('blueprints.inbound.RESEND_WEBHOOK_SECRET', None):
        response = client.post('/inbound/webhook', json={
            'type': 'email.sent',
        })
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'ignored'


def test_webhook_rejects_missing_email_id(client):
    """POST with email.received but no email_id in data returns 400."""
    with patch('blueprints.inbound.RESEND_WEBHOOK_SECRET', None):
        response = client.post('/inbound/webhook', json={
            'type': 'email.received',
            'data': {},
        })
    assert response.status_code == 400
    data = response.get_json()
    assert 'Missing email_id' in data['error']


def test_webhook_no_matching_user(client, test_app, sample_user):
    """Webhook returns 'No matching user' when sender email is not in the database."""
    mock_email_data = {
        'from': 'unknown@nobody.com',
        'subject': 'CE Certificate',
        'text': 'You completed a course',
        'html': '',
        'attachments': [],
    }

    with patch('blueprints.inbound.RESEND_WEBHOOK_SECRET', None), \
         patch('blueprints.inbound.os.environ.get', return_value='fake-api-key'), \
         patch('blueprints.inbound.resend.Emails.Receiving.get', return_value=mock_email_data):

        response = client.post('/inbound/webhook', json={
            'type': 'email.received',
            'data': {'email_id': 'email_123'},
        })

    assert response.status_code == 200
    data = response.get_json()
    assert 'No matching user' in data['error']


def test_webhook_creates_pending_record(client, test_app, sample_user):
    """Full happy path: webhook creates a PendingCERecord with correct fields."""
    mock_email_data = {
        'from': 'test@example.com',
        'subject': 'Your CFP CE Certificate',
        'text': 'You completed Ethics 101 on Jan 15, 2026.',
        'html': '',
        'attachments': [],
    }

    mock_extraction = {
        'title': 'Ethics 101',
        'provider': 'CFP Board',
        'hours': 2.0,
        'date_completed': '2026-01-15',
        'category': 'Ethics',
        'description': 'Ethics course',
        'confidence': 'high',
        'error_message': None,
    }

    with patch('blueprints.inbound.RESEND_WEBHOOK_SECRET', None), \
         patch('blueprints.inbound.os.environ.get', return_value='fake-api-key'), \
         patch('blueprints.inbound.resend.Emails.Receiving.get', return_value=mock_email_data), \
         patch('blueprints.inbound.extract_ce_data_from_text', return_value=mock_extraction), \
         patch('blueprints.inbound.send_email', return_value=True, create=True) as mock_send, \
         patch.dict('sys.modules', {}):

        # Patch the lazy imports inside _process_email
        with patch('email_helper.send_email', return_value=True), \
             patch('email_templates.pending_record_email', return_value='<p>mock</p>'):

            response = client.post('/inbound/webhook', json={
                'type': 'email.received',
                'data': {'email_id': 'email_456'},
            })

    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'created'
    assert data['confidence'] == 'high'

    # Verify PendingCERecord was created in DB
    with test_app.app_context():
        pending = PendingCERecord.query.filter_by(user_id=sample_user['id']).first()
        assert pending is not None
        assert pending.title == 'Ethics 101'
        assert pending.provider == 'CFP Board'
        assert pending.hours == 2.0
        assert pending.category == 'Ethics'
        assert pending.extraction_confidence == 'high'
        assert pending.source_email_subject == 'Your CFP CE Certificate'
        assert pending.source_email_from == 'test@example.com'
        assert pending.status == 'pending'


def test_webhook_with_display_name_email(client, test_app, sample_user):
    """Webhook correctly strips display name from 'Name <email>' format."""
    mock_email_data = {
        'from': 'John Doe <test@example.com>',
        'subject': 'CE Certificate',
        'text': 'Course completion certificate.',
        'html': '',
        'attachments': [],
    }

    mock_extraction = {
        'title': 'Ethics 101',
        'provider': 'CFP Board',
        'hours': 2.0,
        'date_completed': '2026-01-15',
        'category': 'Ethics',
        'description': 'Ethics course',
        'confidence': 'high',
        'error_message': None,
    }

    with patch('blueprints.inbound.RESEND_WEBHOOK_SECRET', None), \
         patch('blueprints.inbound.os.environ.get', return_value='fake-api-key'), \
         patch('blueprints.inbound.resend.Emails.Receiving.get', return_value=mock_email_data), \
         patch('blueprints.inbound.extract_ce_data_from_text', return_value=mock_extraction), \
         patch('email_helper.send_email', return_value=True), \
         patch('email_templates.pending_record_email', return_value='<p>mock</p>'):

        response = client.post('/inbound/webhook', json={
            'type': 'email.received',
            'data': {'email_id': 'email_789'},
        })

    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'created'

    # Verify the record was matched to sample_user despite display name
    with test_app.app_context():
        pending = PendingCERecord.query.filter_by(user_id=sample_user['id']).first()
        assert pending is not None
        assert pending.title == 'Ethics 101'
        assert pending.source_email_from == 'John Doe <test@example.com>'


def test_webhook_handles_pdf_attachment(client, test_app, sample_user):
    """Webhook downloads PDF attachment, extracts text, and creates PendingCERecord."""
    mock_email_data = {
        'from': 'test@example.com',
        'subject': 'Your Certificate',
        'text': '',
        'html': '',
        'attachments': [
            {
                'id': 'att_1',
                'filename': 'cert.pdf',
                'content_type': 'application/pdf',
            },
        ],
    }

    mock_att_details = {
        'download_url': 'https://example.com/cert.pdf',
    }

    mock_pdf_response = MagicMock()
    mock_pdf_response.content = b'%PDF-1.4 fake pdf bytes'
    mock_pdf_response.raise_for_status = MagicMock()

    mock_extraction = {
        'title': 'Advanced Tax Planning',
        'provider': 'AICPA',
        'hours': 3.5,
        'date_completed': '2026-02-10',
        'category': 'Income Tax Planning',
        'description': 'Advanced tax strategies',
        'confidence': 'medium',
        'error_message': None,
    }

    with patch('blueprints.inbound.RESEND_WEBHOOK_SECRET', None), \
         patch('blueprints.inbound.os.environ.get', return_value='fake-api-key'), \
         patch('blueprints.inbound.resend.Emails.Receiving.get', return_value=mock_email_data), \
         patch('blueprints.inbound.resend.Emails.Receiving.Attachments.get', return_value=mock_att_details) as mock_att_get, \
         patch('blueprints.inbound.http_requests.get', return_value=mock_pdf_response) as mock_http_get, \
         patch('blueprints.inbound.extract_text_from_pdf', return_value='Certificate of Completion - Advanced Tax Planning') as mock_extract_pdf, \
         patch('blueprints.inbound.extract_ce_data_from_text', return_value=mock_extraction), \
         patch('email_helper.send_email', return_value=True), \
         patch('email_templates.pending_record_email', return_value='<p>mock</p>'):

        response = client.post('/inbound/webhook', json={
            'type': 'email.received',
            'data': {'email_id': 'email_pdf_1'},
        })

    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'created'
    assert data['confidence'] == 'medium'

    # Verify attachment processing was called correctly
    mock_att_get.assert_called_once_with('email_pdf_1', 'att_1')
    mock_http_get.assert_called_once_with('https://example.com/cert.pdf', timeout=30)
    mock_extract_pdf.assert_called_once_with(b'%PDF-1.4 fake pdf bytes')

    # Verify PendingCERecord has source_filename containing cert.pdf
    with test_app.app_context():
        pending = PendingCERecord.query.filter_by(user_id=sample_user['id']).first()
        assert pending is not None
        assert pending.title == 'Advanced Tax Planning'
        assert pending.source_filename is not None
        assert 'cert.pdf' in pending.source_filename
        assert pending.extraction_confidence == 'medium'
