"""Resend inbound email webhook — receives forwarded CE certificates and extracts data."""
import os

import requests as http_requests
import resend
from flask import Blueprint, request, jsonify

from models import db, User, PendingCERecord
from pdf_extractor import extract_text_from_pdf, extract_ce_data_from_text

inbound_bp = Blueprint('inbound', __name__, url_prefix='/inbound')

RESEND_WEBHOOK_SECRET = os.environ.get('RESEND_WEBHOOK_SECRET')


def _verify_webhook(payload: str, headers: dict) -> bool:
    """Verify Resend webhook signature. Returns True if valid or if secret not configured."""
    if not RESEND_WEBHOOK_SECRET:
        print("[INBOUND] RESEND_WEBHOOK_SECRET not set — skipping verification")
        return True
    try:
        resend.Webhooks.verify({
            "payload": payload,
            "headers": {
                "id": headers.get("svix-id", ""),
                "timestamp": headers.get("svix-timestamp", ""),
                "signature": headers.get("svix-signature", ""),
            },
            "webhook_secret": RESEND_WEBHOOK_SECRET,
        })
        return True
    except ValueError as e:
        print(f"[INBOUND] Webhook verification failed: {e}")
        return False


def _find_user_by_email(from_address: str) -> User | None:
    """Look up a user by their registered email address."""
    if not from_address:
        return None
    # Resend may include display name: "Name <email@example.com>"
    if '<' in from_address and '>' in from_address:
        from_address = from_address.split('<')[1].split('>')[0]
    return User.query.filter_by(email=from_address.strip().lower()).first()


def _process_email(email_id: str) -> dict:
    """Fetch full email + attachments from Resend, extract CE data, create PendingCERecord.

    Returns a dict with processing results.
    """
    resend.api_key = os.environ.get('RESEND_API_KEY')
    if not resend.api_key:
        return {"error": "RESEND_API_KEY not configured"}

    # Fetch full email content
    try:
        email_data = resend.Emails.Receiving.get(email_id)
    except Exception as e:
        return {"error": f"Failed to fetch email: {e}"}

    from_address = email_data.get("from", "")
    subject = email_data.get("subject", "")
    html_body = email_data.get("html", "")
    text_body = email_data.get("text", "")
    attachments = email_data.get("attachments", [])

    # Match sender to a user
    user = _find_user_by_email(from_address)
    if not user:
        print(f"[INBOUND] No user found for sender: {from_address}")
        return {"error": "No matching user", "from": from_address}

    # Collect PDF attachments
    pdf_texts = []
    pdf_filenames = []
    for att in attachments:
        content_type = att.get("content_type", "")
        filename = att.get("filename", "")
        if "pdf" not in content_type.lower() and not filename.lower().endswith(".pdf"):
            continue

        try:
            att_details = resend.Emails.Receiving.Attachments.get(email_id, att["id"])
            download_url = att_details.get("download_url")
            if download_url:
                resp = http_requests.get(download_url, timeout=30)
                resp.raise_for_status()
                pdf_text = extract_text_from_pdf(resp.content)
                if pdf_text:
                    pdf_texts.append(pdf_text)
                    pdf_filenames.append(filename)
        except Exception as e:
            print(f"[INBOUND] Failed to process attachment {filename}: {e}")

    # Use the best available text for extraction
    combined_text = "\n\n".join(pdf_texts) if pdf_texts else ""
    email_body_text = text_body or html_body or ""

    if not combined_text and not email_body_text:
        # Nothing to extract from
        pending = PendingCERecord(
            user_id=user.id,
            status='pending',
            source_email_subject=subject[:300] if subject else None,
            source_email_from=from_address[:200] if from_address else None,
            error_message="No extractable content found in email or attachments",
        )
        db.session.add(pending)
        db.session.commit()
        return {"status": "created", "record_id": pending.id, "confidence": None}

    # Extract CE data using Claude
    extracted = extract_ce_data_from_text(
        text=combined_text,
        email_subject=subject,
        email_body=email_body_text[:2000],
    )

    # Parse date if present
    date_completed = None
    if extracted.get("date_completed"):
        try:
            from datetime import datetime
            date_completed = datetime.strptime(extracted["date_completed"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass

    pending = PendingCERecord(
        user_id=user.id,
        title=extracted.get("title"),
        provider=extracted.get("provider"),
        hours=extracted.get("hours"),
        date_completed=date_completed,
        category=extracted.get("category"),
        description=extracted.get("description"),
        status='pending',
        source_email_subject=subject[:300] if subject else None,
        source_email_from=from_address[:200] if from_address else None,
        source_filename=", ".join(pdf_filenames)[:300] if pdf_filenames else None,
        raw_extracted_text=(combined_text or email_body_text)[:5000],
        extraction_confidence=extracted.get("confidence"),
        error_message=extracted.get("error_message"),
    )
    db.session.add(pending)
    db.session.commit()

    # Send notification email to user
    try:
        from email_helper import send_email
        from email_templates import pending_record_email
        send_email(
            user.email,
            "CE Logbook — New CE Record Ready for Review",
            pending_record_email(user.username, extracted.get("title") or "(untitled)"),
        )
    except Exception as e:
        print(f"[INBOUND] Failed to send notification to {user.email}: {e}")

    return {
        "status": "created",
        "record_id": pending.id,
        "confidence": extracted.get("confidence"),
    }


@inbound_bp.route('/webhook', methods=['POST'])
def resend_webhook():
    """Handle Resend inbound email webhook (email.received events)."""
    raw_payload = request.get_data(as_text=True)

    if not _verify_webhook(raw_payload, dict(request.headers)):
        return jsonify({"error": "Invalid signature"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    event_type = data.get("type")
    if event_type != "email.received":
        # Acknowledge but ignore non-inbound events
        return jsonify({"status": "ignored", "type": event_type}), 200

    email_id = data.get("data", {}).get("email_id")
    if not email_id:
        return jsonify({"error": "Missing email_id"}), 400

    result = _process_email(email_id)

    if "error" in result:
        print(f"[INBOUND] Processing error: {result['error']}")
        # Still return 200 so Resend doesn't retry
        return jsonify(result), 200

    return jsonify(result), 200
