from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User, UserDesignation, Feedback

profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        flash('Please log in to access your profile.', 'error')
        return redirect(url_for('auth.login'))

    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_email':
            new_email = request.form.get('email', '').strip()
            if not new_email:
                flash('Email is required.', 'error')
                return redirect(url_for('profile.profile'))
            if '@' not in new_email or '.' not in new_email:
                flash('Please enter a valid email address.', 'error')
                return redirect(url_for('profile.profile'))

            existing = User.query.filter_by(email=new_email).first()
            if existing and existing.id != user.id:
                flash('That email is already in use by another account.', 'error')
                return redirect(url_for('profile.profile'))
            if new_email == user.email:
                flash('That is already your current email.', 'error')
                return redirect(url_for('profile.profile'))

            user.email = new_email
            db.session.commit()
            flash('Email updated successfully!', 'success')
            return redirect(url_for('profile.profile'))

        elif action == 'change_password':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')

            if not current_password:
                flash('Current password is required.', 'error')
                return redirect(url_for('profile.profile'))
            if not check_password_hash(user.password_hash, current_password):
                flash('Current password is incorrect.', 'error')
                return redirect(url_for('profile.profile'))
            if not new_password:
                flash('New password is required.', 'error')
                return redirect(url_for('profile.profile'))
            if len(new_password) < 6:
                flash('New password must be at least 6 characters long.', 'error')
                return redirect(url_for('profile.profile'))
            if new_password != confirm_password:
                flash('New passwords do not match.', 'error')
                return redirect(url_for('profile.profile'))

            user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('profile.profile'))

    designation_count = UserDesignation.query.filter_by(user_id=user.id).count()
    return render_template('profile.html', user=user, designation_count=designation_count)


@profile_bp.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    name = request.form.get('feedback_name', '').strip()
    email = request.form.get('feedback_email', '').strip()
    feedback_type = request.form.get('feedback_type', '').strip()
    message = request.form.get('feedback_message', '').strip()

    errors = []
    if not name:
        errors.append('Name is required.')
    if not email:
        errors.append('Email is required.')
    elif '@' not in email or '.' not in email:
        errors.append('Please enter a valid email address.')
    if not feedback_type:
        errors.append('Please select a feedback type.')
    if not message:
        errors.append('Message is required.')
    elif len(message) < 10:
        errors.append('Please provide more detail in your message (at least 10 characters).')

    if errors:
        for error in errors:
            flash(error, 'error')
        return redirect(request.referrer or url_for('ce_records.dashboard'))

    feedback = Feedback(
        name=name, email=email, feedback_type=feedback_type,
        message=message, user_id=session.get('user_id')
    )
    db.session.add(feedback)
    db.session.commit()

    flash('Thank you for your feedback! We appreciate you taking the time to help us improve.', 'success')
    return redirect(request.referrer or url_for('ce_records.dashboard'))
