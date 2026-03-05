import os
import resend

RESEND_API_KEY = os.environ.get('RESEND_API_KEY')
FROM_EMAIL = os.environ.get('FROM_EMAIL', 'noreply@celogbook.com')


def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """Send an email via Resend. Returns True on success, False on failure."""
    if not RESEND_API_KEY:
        print(f"[EMAIL] Resend not configured. Would send to {to_email}: {subject}")
        return False
    try:
        resend.api_key = RESEND_API_KEY
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": [to_email],
            "subject": subject,
            "html": html_content,
        })
        return True
    except Exception as e:
        print(f"[EMAIL] Failed to send to {to_email}: {e}")
        return False
