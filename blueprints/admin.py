from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from sqlalchemy import func

from models import db, User, CERecord, UserDesignation, Feedback, AuditLog

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    """Decorator that checks for admin access via is_admin flag on User model."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Support both new admin role and legacy query-param key during transition
        admin_key = request.args.get('key', '')
        expected_key = os.environ.get('ADMIN_KEY', 'cetracker2025admin')

        if admin_key == expected_key:
            return f(*args, **kwargs)

        if 'user_id' in session:
            user = db.session.get(User, session['user_id'])
            if user and user.is_admin:
                return f(*args, **kwargs)

        flash('Unauthorized access.', 'error')
        return redirect(url_for('auth.login'))
    return decorated_function


def log_admin_action(action: str, target_user_id: int = None, details: str = None):
    """Record an admin action in the audit log."""
    admin_id = session.get('user_id')
    if admin_id:
        entry = AuditLog(
            admin_id=admin_id,
            action=action,
            target_user_id=target_user_id,
            details=details
        )
        db.session.add(entry)


@admin_bp.route('/feedback')
@admin_required
def view_feedback():
    filter_type = request.args.get('type', '')
    filter_read = request.args.get('read', '')

    query = Feedback.query
    if filter_type:
        query = query.filter(Feedback.feedback_type == filter_type)
    if filter_read == 'unread':
        query = query.filter(Feedback.is_read == False)
    elif filter_read == 'read':
        query = query.filter(Feedback.is_read == True)

    feedback_list = query.order_by(Feedback.created_at.desc()).all()
    total_count = Feedback.query.count()
    unread_count = Feedback.query.filter(Feedback.is_read == False).count()

    admin_key = request.args.get('key', '')

    return render_template('admin_feedback.html',
                           feedback_list=feedback_list,
                           total_count=total_count,
                           unread_count=unread_count,
                           filter_type=filter_type,
                           filter_read=filter_read,
                           admin_key=admin_key)


@admin_bp.route('/feedback/<int:feedback_id>/toggle_read', methods=['POST'])
@admin_required
def toggle_feedback_read(feedback_id):
    feedback = db.get_or_404(Feedback, feedback_id)
    feedback.is_read = not feedback.is_read
    db.session.commit()

    admin_key = request.args.get('key', '')
    return redirect(url_for('admin.view_feedback', key=admin_key))


@admin_bp.route('/feedback/<int:feedback_id>/delete', methods=['POST'])
@admin_required
def delete_feedback(feedback_id):
    feedback = db.get_or_404(Feedback, feedback_id)
    db.session.delete(feedback)
    db.session.commit()
    flash('Feedback deleted.', 'success')

    admin_key = request.args.get('key', '')
    return redirect(url_for('admin.view_feedback', key=admin_key))


@admin_bp.route('/dashboard')
@admin_required
def admin_dashboard():
    # Overall stats
    total_users = User.query.count()
    total_records = CERecord.query.count()
    total_hours = db.session.query(func.coalesce(func.sum(CERecord.hours), 0)).scalar()
    thirty_days_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    new_users_30d = User.query.filter(User.created_at >= thirty_days_ago).count()

    # Top 5 most active users by CE record count
    top_users = (
        db.session.query(
            User.username,
            func.count(CERecord.id).label('record_count'),
            func.coalesce(func.sum(CERecord.hours), 0).label('total_hours')
        )
        .join(CERecord, User.id == CERecord.user_id)
        .group_by(User.id, User.username)
        .order_by(func.count(CERecord.id).desc())
        .limit(5)
        .all()
    )

    # Full users list with stats (use subqueries to avoid cross-join inflation)
    ce_stats = (
        db.session.query(
            CERecord.user_id,
            func.count(CERecord.id).label('record_count'),
            func.coalesce(func.sum(CERecord.hours), 0).label('total_hours')
        )
        .group_by(CERecord.user_id)
        .subquery()
    )
    desig_stats = (
        db.session.query(
            UserDesignation.user_id,
            func.count(UserDesignation.id).label('designation_count')
        )
        .group_by(UserDesignation.user_id)
        .subquery()
    )
    users_with_stats = (
        db.session.query(
            User,
            func.coalesce(ce_stats.c.record_count, 0).label('record_count'),
            func.coalesce(ce_stats.c.total_hours, 0).label('total_hours'),
            func.coalesce(desig_stats.c.designation_count, 0).label('designation_count')
        )
        .outerjoin(ce_stats, User.id == ce_stats.c.user_id)
        .outerjoin(desig_stats, User.id == desig_stats.c.user_id)
        .order_by(User.created_at.desc())
        .all()
    )

    return render_template('admin_dashboard.html',
                           total_users=total_users,
                           total_records=total_records,
                           total_hours=total_hours,
                           new_users_30d=new_users_30d,
                           top_users=top_users,
                           users_with_stats=users_with_stats)


@admin_bp.route('/toggle_admin/<int:user_id>', methods=['POST'])
@admin_required
def toggle_admin(user_id):
    target_user = db.session.get(User, user_id)
    if not target_user:
        flash('User not found.', 'error')
        return redirect(url_for('admin.admin_dashboard'))

    # Prevent admin from removing their own admin access
    if 'user_id' in session and target_user.id == session['user_id']:
        flash('You cannot change your own admin status.', 'error')
        return redirect(url_for('admin.admin_dashboard'))

    target_user.is_admin = not target_user.is_admin
    status = 'granted' if target_user.is_admin else 'revoked'
    log_admin_action('toggle_admin', target_user_id=user_id,
                     details=f'Admin access {status} for {target_user.username}')
    db.session.commit()

    flash(f'Admin access {status} for {target_user.username}.', 'success')
    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/toggle_active/<int:user_id>', methods=['POST'])
@admin_required
def toggle_active(user_id):
    target_user = db.session.get(User, user_id)
    if not target_user:
        flash('User not found.', 'error')
        return redirect(url_for('admin.admin_dashboard'))

    # Prevent admin from deactivating themselves
    if 'user_id' in session and target_user.id == session['user_id']:
        flash('You cannot deactivate your own account.', 'error')
        return redirect(url_for('admin.admin_dashboard'))

    target_user.is_active = not target_user.is_active
    status = 'activated' if target_user.is_active else 'deactivated'
    log_admin_action('toggle_active', target_user_id=user_id,
                     details=f'Account {status} for {target_user.username}')
    db.session.commit()

    flash(f'Account {status} for {target_user.username}.', 'success')
    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    target_user = db.session.get(User, user_id)
    if not target_user:
        flash('User not found.', 'error')
        return redirect(url_for('admin.admin_dashboard'))

    # Prevent admin from deleting themselves
    if 'user_id' in session and target_user.id == session['user_id']:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin.admin_dashboard'))

    username = target_user.username
    log_admin_action('delete_user', target_user_id=user_id,
                     details=f'Deleted user {username} (id={user_id}) and all associated data')
    # Cascade handles ce_records and designations via relationship config
    # Manually delete feedback since it doesn't cascade from User
    Feedback.query.filter_by(user_id=user_id).delete()
    db.session.delete(target_user)
    db.session.commit()

    flash(f'User {username} and all associated data have been deleted.', 'success')
    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/send_reminders', methods=['POST'])
@admin_required
def send_reminders():
    from deadline_checker import check_and_send_deadline_reminders
    results = check_and_send_deadline_reminders()
    total_sent = results['approaching_sent'] + results['overdue_sent']
    log_admin_action('send_reminders',
                     details=f"Checked {results['checked']} designations, sent {total_sent} reminders")
    db.session.commit()
    flash(
        f"Reminder check complete: {results['checked']} designations checked, "
        f"{total_sent} reminders sent ({results['approaching_sent']} approaching, "
        f"{results['overdue_sent']} overdue), {results['skipped_cooldown']} skipped (cooldown), "
        f"{results['skipped_complete']} already complete.",
        'success' if results['errors'] == 0 else 'info'
    )
    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/audit_log')
@admin_required
def audit_log():
    logs = (
        AuditLog.query
        .order_by(AuditLog.timestamp.desc())
        .limit(100)
        .all()
    )
    # Resolve admin usernames (admin user may have been deleted, so handle gracefully)
    for log_entry in logs:
        admin = db.session.get(User, log_entry.admin_id)
        log_entry.admin_username = admin.username if admin else f'(deleted user #{log_entry.admin_id})'
    return render_template('admin_audit_log.html', logs=logs)


@admin_bp.route('/user/<int:user_id>/records')
@admin_required
def view_user_records(user_id):
    target_user = db.session.get(User, user_id)
    if not target_user:
        flash('User not found.', 'error')
        return redirect(url_for('admin.admin_dashboard'))

    ce_records = (
        CERecord.query
        .filter_by(user_id=user_id)
        .order_by(CERecord.date_completed.desc())
        .all()
    )
    total_hours = sum(r.hours for r in ce_records)
    designations = UserDesignation.query.filter_by(user_id=user_id).all()

    return render_template('admin_user_records.html',
                           target_user=target_user,
                           ce_records=ce_records,
                           total_hours=total_hours,
                           designations=designations)
