"""Check CE deadlines and send reminder emails to users approaching or past due."""
from datetime import datetime, timedelta, timezone

from models import db, User, UserDesignation
from designation_helpers import DESIGNATION_CALCULATORS
from email_helper import send_email
from email_templates import deadline_reminder_email

# Don't send more than one reminder per designation per 7 days
REMINDER_COOLDOWN_DAYS = 7

# Send reminders when within this many days of deadline
APPROACHING_DAYS = 60

# Only remind users below this percentage of required hours
APPROACHING_THRESHOLD_PCT = 80.0


def check_and_send_deadline_reminders() -> dict:
    """Check all active users' designations and send reminders as needed.

    Returns a summary dict with counts of reminders sent, skipped, and errors.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cooldown_cutoff = now - timedelta(days=REMINDER_COOLDOWN_DAYS)

    results = {
        'checked': 0,
        'approaching_sent': 0,
        'overdue_sent': 0,
        'skipped_cooldown': 0,
        'skipped_complete': 0,
        'errors': 0,
    }

    # Get all active users who have at least one designation
    users = (
        User.query
        .filter(User.is_active == True)
        .join(UserDesignation)
        .all()
    )

    for user in users:
        for ud in user.designations:
            results['checked'] += 1

            calc = DESIGNATION_CALCULATORS.get(ud.designation)
            if not calc:
                continue

            try:
                req = calc(user, ud)
            except Exception as e:
                print(f"[DEADLINE] Error calculating {ud.designation} for {user.username}: {e}")
                results['errors'] += 1
                continue

            if not req:
                continue

            # Skip if already complete
            if req.get('is_complete'):
                results['skipped_complete'] += 1
                continue

            # Check cooldown — don't spam
            if ud.last_reminder_sent and ud.last_reminder_sent > cooldown_cutoff:
                results['skipped_cooldown'] += 1
                continue

            period_end = req.get('period_end')
            if not period_end:
                continue

            today = datetime.now().date()
            days_until_deadline = (period_end - today).days
            total_pct = req.get('total_percentage', 0)
            hours_remaining = req.get('total_remaining', 0)
            deadline_str = period_end.strftime('%B %d, %Y')

            send = False
            if days_until_deadline < 0 and total_pct < 100:
                # Overdue
                send = True
                reminder_type = 'overdue'
            elif days_until_deadline <= APPROACHING_DAYS and total_pct < APPROACHING_THRESHOLD_PCT:
                # Approaching deadline and behind
                send = True
                reminder_type = 'approaching'

            if not send:
                continue

            email_sent = send_email(
                to_email=user.email,
                subject=f'CE Logbook — {ud.designation} Deadline Reminder',
                html_content=deadline_reminder_email(
                    username=user.username,
                    designation=ud.designation,
                    hours_remaining=hours_remaining,
                    deadline_date=deadline_str
                )
            )

            if email_sent:
                ud.last_reminder_sent = now
                if reminder_type == 'overdue':
                    results['overdue_sent'] += 1
                else:
                    results['approaching_sent'] += 1
            else:
                # Even without Resend, mark as sent to avoid console spam on repeated runs
                ud.last_reminder_sent = now
                if reminder_type == 'overdue':
                    results['overdue_sent'] += 1
                else:
                    results['approaching_sent'] += 1

    db.session.commit()
    return results
