from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import os
from functools import wraps

from models import db, User, Feedback

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
            user = User.query.get(session['user_id'])
            if user and user.is_admin:
                return f(*args, **kwargs)

        flash('Unauthorized access.', 'error')
        return redirect(url_for('auth.login'))
    return decorated_function


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
    feedback = Feedback.query.get_or_404(feedback_id)
    feedback.is_read = not feedback.is_read
    db.session.commit()

    admin_key = request.args.get('key', '')
    return redirect(url_for('admin.view_feedback', key=admin_key))


@admin_bp.route('/feedback/<int:feedback_id>/delete', methods=['POST'])
@admin_required
def delete_feedback(feedback_id):
    feedback = Feedback.query.get_or_404(feedback_id)
    db.session.delete(feedback)
    db.session.commit()
    flash('Feedback deleted.', 'success')

    admin_key = request.args.get('key', '')
    return redirect(url_for('admin.view_feedback', key=admin_key))
