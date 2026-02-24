from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
import uuid

from models import db, User, UserDesignation
from designation_helpers import DESIGNATION_REQUIREMENTS, ALLOWED_DESIGNATIONS

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('ce_records.dashboard'))
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('ce_records.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        designations = request.form.getlist('designations')
        cfp_birth_month = request.form.get('cfp_birth_month', '')
        cpa_state = request.form.get('cpa_state', '')
        is_napfa_member = request.form.get('is_napfa_member') == 'on'
        napfa_join_date = request.form.get('napfa_join_date', '')

        form_data = {
            'username': username, 'email': email, 'designations': designations,
            'cfp_birth_month': cfp_birth_month, 'cpa_state': cpa_state,
            'is_napfa_member': is_napfa_member, 'napfa_join_date': napfa_join_date
        }

        errors = []
        if not username:
            errors.append('Username is required.')
        if not email:
            errors.append('Email is required.')
        if not password:
            errors.append('Password is required.')
        elif len(password) < 6:
            errors.append('Password must be at least 6 characters long.')
        if password and confirm_password and password != confirm_password:
            errors.append('Passwords do not match.')

        if 'CFP' in designations:
            if not cfp_birth_month:
                errors.append('Birth month is required for CFP designation.')
            else:
                try:
                    bm = int(cfp_birth_month)
                    if bm < 1 or bm > 12:
                        errors.append('Birth month must be between 1 and 12.')
                except ValueError:
                    errors.append('Invalid birth month.')

        if 'CPA' in designations:
            if not cpa_state:
                errors.append('State is required for CPA designation.')
            elif len(cpa_state) != 2 or not cpa_state.isalpha():
                errors.append('Invalid state abbreviation. Please use a 2-letter state code (e.g., CA, NY, TX).')

        napfa_join_date_obj = None
        if is_napfa_member:
            if not napfa_join_date:
                errors.append('NAPFA join date is required if you are a NAPFA member.')
            else:
                try:
                    napfa_join_date_obj = datetime.strptime(napfa_join_date, '%Y-%m-%d').date()
                except ValueError:
                    errors.append('Invalid NAPFA join date format.')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('register.html',
                                   designation_requirements=DESIGNATION_REQUIREMENTS,
                                   form_data=form_data)

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return render_template('register.html',
                                   designation_requirements=DESIGNATION_REQUIREMENTS,
                                   form_data=form_data)

        if User.query.filter_by(email=email).first():
            flash('Email already exists.', 'error')
            return render_template('register.html',
                                   designation_requirements=DESIGNATION_REQUIREMENTS,
                                   form_data=form_data)

        user = User(
            username=username, email=email,
            password_hash=generate_password_hash(password),
            is_napfa_member=is_napfa_member,
            napfa_join_date=napfa_join_date_obj
        )
        db.session.add(user)
        db.session.flush()

        for designation in designations:
            if designation in ALLOWED_DESIGNATIONS:
                ud = UserDesignation(
                    user_id=user.id, designation=designation,
                    birth_month=int(cfp_birth_month) if designation == 'CFP' and cfp_birth_month else None,
                    state=cpa_state.upper() if designation == 'CPA' and cpa_state else None
                )
                db.session.add(ud)

        db.session.commit()
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('register.html', designation_requirements=DESIGNATION_REQUIREMENTS)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('ce_records.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Please enter both username and password.', 'error')
            return render_template('login.html')

        try:
            user = User.query.filter_by(username=username).first()
            if not user:
                flash('User not found. Please check your username or register for a new account.', 'error')
                return render_template('login.html')

            if check_password_hash(user.password_hash, password):
                session['user_id'] = user.id
                session['username'] = user.username
                session['show_napfa_tracking'] = user.is_napfa_member
                flash('Login successful!', 'success')
                return redirect(url_for('ce_records.dashboard'))
            else:
                flash('Invalid password. Please try again.', 'error')
                return render_template('login.html')
        except Exception as e:
            flash('An error occurred during login. Please try again.', 'error')
            print(f"Login error: {e}")
            return render_template('login.html')

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if 'user_id' in session:
        return redirect(url_for('profile.profile'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if not email:
            flash('Please enter your email address.', 'error')
            return render_template('forgot_password.html')

        user = User.query.filter_by(email=email).first()
        if user:
            token = uuid.uuid4().hex
            user.reset_token = token
            user.reset_token_expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
            db.session.commit()
            return redirect(url_for('auth.reset_password', token=token))

        flash('If an account with that email exists, a reset link has been generated.', 'info')
        return render_template('forgot_password.html')

    return render_template('forgot_password.html')


@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()

    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.now(timezone.utc).replace(tzinfo=None):
        flash('This reset link is invalid or has expired.', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not new_password:
            flash('New password is required.', 'error')
            return render_template('reset_password.html', token=token)
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('reset_password.html', token=token)
        if new_password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('reset_password.html', token=token)

        user.password_hash = generate_password_hash(new_password)
        user.reset_token = None
        user.reset_token_expiry = None
        db.session.commit()

        flash('Your password has been reset! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('reset_password.html', token=token)
