from flask import Flask, render_template, request, redirect, url_for, flash, session, Response, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import csv
import io
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())

# Database configuration - use PostgreSQL in production, SQLite for local development
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Render provides DATABASE_URL in format: postgresql://user:pass@host/dbname
    # SQLAlchemy needs postgresql:// (not postgres://)
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Fall back to SQLite for local development
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ce_tracker.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads/certificates'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}

db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    __tablename__ = 'users'  # Use 'users' instead of 'user' to avoid PostgreSQL reserved word conflict
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_napfa_member = db.Column(db.Boolean, default=False, nullable=False)
    napfa_join_date = db.Column(db.Date)  # Date user joined NAPFA
    reset_token = db.Column(db.String(100), unique=True, nullable=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)
    ce_records = db.relationship('CERecord', backref='user', lazy=True, cascade='all, delete-orphan')
    designations = db.relationship('UserDesignation', backref='user', lazy=True, cascade='all, delete-orphan')

class CERecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    provider = db.Column(db.String(200))
    hours = db.Column(db.Float, nullable=False)
    date_completed = db.Column(db.Date, nullable=False)
    category = db.Column(db.String(100))
    description = db.Column(db.Text)
    is_napfa_approved = db.Column(db.Boolean, default=False, nullable=False)  # Marks if CE counts toward NAPFA approved sources requirement
    is_ethics_course = db.Column(db.Boolean, default=False, nullable=False)  # Marks if this is the required 2-CE Ethics course
    napfa_subject_area = db.Column(db.String(100))  # NAPFA subject area for NAPFA-certified advisors
    certificate_filename = db.Column(db.String(255))  # Stores the filename of uploaded PDF certificate
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserDesignation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    designation = db.Column(db.String(10), nullable=False)  # CFP, CFA, CPA, CLE, CLU, EA, ChFC, CIMA, CIMC, CPWA, CRPS, RICP, CDFA, AIF, IAR, CEP
    birth_month = db.Column(db.Integer)  # For CFP only (1-12)
    state = db.Column(db.String(2))  # For CPA only (state abbreviation)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'designation', name='unique_user_designation'),)

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    feedback_type = db.Column(db.String(50), nullable=False)  # bug, feature, general, other
    message = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Optional - if submitted by logged-in user
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Helper Functions
def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def ensure_upload_directory():
    """Ensure upload directory exists"""
    upload_dir = app.config['UPLOAD_FOLDER']
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)

# Helper Functions
def calculate_cfp_requirements(user, user_designation):
    """
    Calculate CFP CE requirements.
    CFP requires 30 hours every 2 years, including 2 hours of Ethics.
    Reporting period is based on birth month.
    """
    if not user_designation or user_designation.designation != 'CFP' or not user_designation.birth_month:
        return None
    
    birth_month = user_designation.birth_month
    current_date = datetime.now().date()
    current_year = current_date.year
    
    # Determine the reporting period based on birth month
    # CFP reporting period is 2 years, starting on the 1st of the birth month
    # If current month is before birth month, we're in a period that started 2 years ago
    # If current month is on or after birth month, we're in a period that started last year
    
    if current_date.month < birth_month:
        # We're before the birth month, so the current period started 2 years ago
        period_start = datetime(current_year - 2, birth_month, 1).date()
        period_end = datetime(current_year, birth_month, 1).date() - timedelta(days=1)
    else:
        # We're on or after the birth month, so the current period started last year
        period_start = datetime(current_year - 1, birth_month, 1).date()
        period_end = datetime(current_year + 1, birth_month, 1).date() - timedelta(days=1)
    
    # Get CE records within the reporting period
    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()
    
    total_hours = sum(record.hours for record in ce_records)
    ethics_hours = sum(record.hours for record in ce_records if 'ethics' in (record.category or '').lower() or 'ethics' in (record.title or '').lower())
    ethics_required = 2.0
    total_required = 30.0
    
    # Calculate percentages for progress bars
    total_percentage = (total_hours / total_required * 100) if total_required > 0 else 0
    ethics_percentage = (ethics_hours / ethics_required * 100) if ethics_required > 0 else 0
    
    return {
        'designation': 'CFP',
        'total_required': total_required,
        'total_earned': total_hours,
        'total_remaining': max(0, total_required - total_hours),
        'total_percentage': min(100, max(0, total_percentage)),  # Clamp between 0 and 100
        'ethics_required': ethics_required,
        'ethics_earned': min(ethics_hours, ethics_required),
        'ethics_remaining': max(0, ethics_required - ethics_hours),
        'ethics_percentage': min(100, max(0, ethics_percentage)),  # Clamp between 0 and 100
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= total_required and ethics_hours >= ethics_required
    }

def calculate_cpa_requirements(user, user_designation):
    """
    Calculate CPA CPE requirements.
    Most states require 40 hours per year, but this varies by state.
    For now, we'll use 40 hours as default, but this can be customized per state later.
    """
    if not user_designation or user_designation.designation != 'CPA':
        return None
    
    # Default to 40 hours per year (most common requirement)
    # This can be customized per state later
    hours_per_year = 40.0
    
    current_date = datetime.now().date()
    current_year = current_date.year
    
    # CPA reporting is typically calendar year (Jan 1 - Dec 31)
    period_start = datetime(current_year, 1, 1).date()
    period_end = datetime(current_year, 12, 31).date()
    
    # Get CE records within the current year
    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()
    
    total_hours = sum(record.hours for record in ce_records)
    
    # Calculate percentage for progress bar
    total_percentage = (total_hours / hours_per_year * 100) if hours_per_year > 0 else 0
    
    return {
        'designation': 'CPA',
        'state': user_designation.state,
        'total_required': hours_per_year,
        'total_earned': total_hours,
        'total_remaining': max(0, hours_per_year - total_hours),
        'total_percentage': min(100, max(0, total_percentage)),  # Clamp between 0 and 100
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= hours_per_year
    }

def calculate_ea_requirements(user, user_designation):
    """
    Calculate EA CE requirements.
    EA requires 72 hours every 3 years, with minimum 16 hours per year, including 2 hours of ethics.
    """
    if not user_designation or user_designation.designation != 'EA':
        return None
    
    current_date = datetime.now().date()
    current_year = current_date.year
    
    # EA reporting is typically calendar year based, 3-year cycle
    # For simplicity, we'll track the current 3-year period
    cycle_start_year = (current_year // 3) * 3  # Rounds down to nearest multiple of 3
    period_start = datetime(cycle_start_year, 1, 1).date()
    period_end = datetime(cycle_start_year + 2, 12, 31).date()
    
    # Get CE records within the 3-year period
    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()
    
    # Also check current year for minimum requirement
    current_year_start = datetime(current_year, 1, 1).date()
    current_year_end = datetime(current_year, 12, 31).date()
    current_year_records = [r for r in ce_records if current_year_start <= r.date_completed <= current_year_end]
    
    total_hours = sum(record.hours for record in ce_records)
    current_year_hours = sum(record.hours for record in current_year_records)
    ethics_hours = sum(record.hours for record in ce_records if 'ethics' in (record.category or '').lower() or 'ethics' in (record.title or '').lower())
    
    total_required = 72.0
    yearly_minimum = 16.0
    ethics_required = 2.0
    
    # Calculate percentages for progress bars
    total_percentage = (total_hours / total_required * 100) if total_required > 0 else 0
    ethics_percentage = (ethics_hours / ethics_required * 100) if ethics_required > 0 else 0
    yearly_percentage = (current_year_hours / yearly_minimum * 100) if yearly_minimum > 0 else 0
    
    return {
        'designation': 'EA',
        'total_required': total_required,
        'total_earned': total_hours,
        'total_remaining': max(0, total_required - total_hours),
        'total_percentage': min(100, max(0, total_percentage)),  # Clamp between 0 and 100
        'yearly_minimum': yearly_minimum,
        'current_year_hours': current_year_hours,
        'yearly_percentage': min(100, max(0, yearly_percentage)),  # Clamp between 0 and 100
        'ethics_required': ethics_required,
        'ethics_earned': min(ethics_hours, ethics_required),
        'ethics_remaining': max(0, ethics_required - ethics_hours),
        'ethics_percentage': min(100, max(0, ethics_percentage)),  # Clamp between 0 and 100
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= total_required and current_year_hours >= yearly_minimum and ethics_hours >= ethics_required
    }

def calculate_eca_requirements(user, user_designation):
    """
    Calculate ECA CE requirements.
    ECA (Equity Compensation Associate) requires 30 hours every 2 years.
    Administrative fee: $250 (waived after 15 hours of volunteer work).
    The ECA is the first level in the CEP certification process from CEPI.
    Based on CEPI requirements: https://www.scu.edu/execed/cepi/continuing-education/
    """
    if not user_designation or user_designation.designation != 'ECA':
        return None
    
    current_date = datetime.now().date()
    
    # ECA reporting period is 2 years from when the designation was added
    # Use the created_at date of the designation as the start of the first period
    designation_date = user_designation.created_at.date() if user_designation.created_at else current_date
    
    # Calculate which 2-year period we're currently in
    years_since_designation = (current_date - designation_date).days / 365.25
    period_number = int(years_since_designation // 2)
    
    # Calculate the start and end of the current 2-year period
    period_start = datetime(
        designation_date.year + (period_number * 2),
        designation_date.month,
        designation_date.day
    ).date()
    
    period_end = datetime(
        designation_date.year + ((period_number + 1) * 2),
        designation_date.month,
        designation_date.day
    ).date() - timedelta(days=1)
    
    # Ensure period_end doesn't exceed current date (for the current period)
    if period_end > current_date:
        period_end = current_date
    
    # Get CE records within the current 2-year period
    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()
    
    total_hours = sum(record.hours for record in ce_records)
    total_required = 30.0
    
    # Calculate percentage for progress bar
    total_percentage = (total_hours / total_required * 100) if total_required > 0 else 0
    
    return {
        'designation': 'ECA',
        'total_required': total_required,
        'total_earned': total_hours,
        'total_remaining': max(0, total_required - total_hours),
        'total_percentage': min(100, max(0, total_percentage)),  # Clamp between 0 and 100
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= total_required,
        'admin_fee': 250.0,  # $250 administrative fee
        'volunteer_hours_required': 15.0  # Hours of volunteer work to waive fee
    }

def calculate_cep_requirements(user, user_designation):
    """
    Calculate CEP CE requirements.
    CEP requires 30 hours every 2 years.
    Administrative fee: $250 (waived after 15 hours of volunteer work).
    Based on CEPI requirements: https://www.scu.edu/execed/cepi/continuing-education/
    """
    if not user_designation or user_designation.designation != 'CEP':
        return None
    
    current_date = datetime.now().date()
    
    # CEP reporting period is 2 years from when the designation was added
    # Use the created_at date of the designation as the start of the first period
    designation_date = user_designation.created_at.date() if user_designation.created_at else current_date
    
    # Calculate which 2-year period we're currently in
    years_since_designation = (current_date - designation_date).days / 365.25
    period_number = int(years_since_designation // 2)
    
    # Calculate the start and end of the current 2-year period
    period_start = datetime(
        designation_date.year + (period_number * 2),
        designation_date.month,
        designation_date.day
    ).date()
    
    period_end = datetime(
        designation_date.year + ((period_number + 1) * 2),
        designation_date.month,
        designation_date.day
    ).date() - timedelta(days=1)
    
    # Ensure period_end doesn't exceed current date (for the current period)
    if period_end > current_date:
        period_end = current_date
    
    # Get CE records within the current 2-year period
    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()
    
    total_hours = sum(record.hours for record in ce_records)
    total_required = 30.0
    
    # Calculate percentage for progress bar
    total_percentage = (total_hours / total_required * 100) if total_required > 0 else 0
    
    return {
        'designation': 'CEP',
        'total_required': total_required,
        'total_earned': total_hours,
        'total_remaining': max(0, total_required - total_hours),
        'total_percentage': min(100, max(0, total_percentage)),  # Clamp between 0 and 100
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= total_required,
        'admin_fee': 250.0,  # $250 administrative fee
        'volunteer_hours_required': 15.0  # Hours of volunteer work to waive fee
    }

def calculate_designation_requirements(user, user_designations):
    """
    Calculate requirements for all user designations.
    """
    requirements = []
    
    for user_designation in user_designations:
        if user_designation.designation == 'CFP':
            req = calculate_cfp_requirements(user, user_designation)
            if req:
                requirements.append(req)
        elif user_designation.designation == 'CPA':
            req = calculate_cpa_requirements(user, user_designation)
            if req:
                requirements.append(req)
        elif user_designation.designation == 'EA':
            req = calculate_ea_requirements(user, user_designation)
            if req:
                requirements.append(req)
        elif user_designation.designation == 'CEP':
            req = calculate_cep_requirements(user, user_designation)
            if req:
                requirements.append(req)
        elif user_designation.designation == 'ECA':
            req = calculate_eca_requirements(user, user_designation)
            if req:
                requirements.append(req)
        # Add other designations as needed (CFA, CPWA, CLU)
    
    return requirements

def calculate_napfa_requirements(user):
    """
    Calculate NAPFA CE requirements based on join date.
    Based on NAPFA CE Guidelines: https://www.napfa.org/member-resources/ce-guidelines
    Cycles run in 2-year periods: even year to odd year (e.g., 2024-2025, 2026-2027, etc.)
    """
    if not user.is_napfa_member or not user.napfa_join_date:
        return None

    # Dynamically calculate current 2-year cycle based on current year
    current_year = datetime.now().year
    if current_year % 2 == 0:
        # Even year: cycle is current_year to current_year+1
        cycle_start_year = current_year
    else:
        # Odd year: cycle is current_year-1 to current_year
        cycle_start_year = current_year - 1
    cycle_end_year = cycle_start_year + 1

    cycle_start = datetime(cycle_start_year, 1, 1).date()
    cycle_end = datetime(cycle_end_year, 12, 31).date()

    join_date = user.napfa_join_date

    # Determine requirements based on join date relative to current cycle
    # Thresholds are relative to the cycle start/end years
    if join_date <= datetime(cycle_start_year, 6, 30).date():
        # Joined on or before June 30 of the cycle start year
        total_required = 60
        napfa_approved_required = 30
    elif join_date <= datetime(cycle_start_year, 12, 31).date():
        # Joined July - December of the cycle start year
        total_required = 45
        napfa_approved_required = 30
    elif join_date <= datetime(cycle_end_year, 6, 30).date():
        # Joined January - June of the cycle end year
        total_required = 30
        napfa_approved_required = 30
    else:
        # Joined July - December of the cycle end year
        total_required = 15
        napfa_approved_required = 15
    
    # Get all CE records within the current cycle
    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= cycle_start,
        CERecord.date_completed <= cycle_end
    ).all()
    
    # Calculate totals
    total_hours = sum(record.hours for record in ce_records)
    napfa_approved_hours = sum(record.hours for record in ce_records if record.is_napfa_approved)
    ethics_completed = any(record.is_ethics_course for record in ce_records)
    
    # Calculate percentages for progress bars
    total_percentage = (total_hours / total_required * 100) if total_required > 0 else 0
    napfa_approved_percentage = (napfa_approved_hours / napfa_approved_required * 100) if napfa_approved_required > 0 else 0
    
    return {
        'total_required': total_required,
        'total_earned': total_hours,
        'total_remaining': max(0, total_required - total_hours),
        'total_percentage': min(100, max(0, total_percentage)),  # Clamp between 0 and 100
        'napfa_approved_required': napfa_approved_required,
        'napfa_approved_earned': napfa_approved_hours,
        'napfa_approved_remaining': max(0, napfa_approved_required - napfa_approved_hours),
        'napfa_approved_percentage': min(100, max(0, napfa_approved_percentage)),  # Clamp between 0 and 100
        'ethics_required': True,
        'ethics_completed': ethics_completed,
        'cycle_start': cycle_start,
        'cycle_end': cycle_end,
        'is_complete': (total_hours >= total_required and 
                       napfa_approved_hours >= napfa_approved_required and 
                       ethics_completed)
    }

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    # Designation requirements for tooltips
    designation_requirements = {
        'CFP': 'CFP® professionals must complete 30 hours of continuing education (CE) every two years, which includes 2 hours of CFP Board-approved Ethics CE and 28 hours in one or more of the CFP Board\'s Principal Topics. The CE requirement begins immediately upon initial certification or 12 months after passing the exam if experience and/or degree requirements are not yet met. Excess CE hours cannot be carried over to the next reporting period.',
        'CFA': 'CFA charterholders must complete continuing education (CE) requirements through the CFA Institute. Requirements include professional learning activities and may vary based on membership status.',
        'CPA': 'CPAs must complete continuing professional education (CPE) requirements that vary by state. Most states require 40 hours of CPE per year, with specific requirements for ethics courses. Check your state board for exact requirements.',
        'CLE': 'Continuing Legal Education (CLE) requirements vary by state and jurisdiction. Most states require attorneys to complete a certain number of CLE hours annually or biennially, with specific requirements for ethics courses.',
        'CLU': 'CLU professionals must complete continuing education requirements as specified by The American College. Requirements typically include ethics and other professional development courses.',
        'EA': 'Enrolled Agents (EAs) must complete 72 hours of continuing education (CE) every three years, with a minimum of 16 hours per year. At least 2 hours must be on ethics.',
        'ChFC': 'ChFC® (Chartered Financial Consultant) professionals must complete continuing education requirements as specified by The American College. Requirements typically include ethics and financial planning topics.',
        'CIMA': 'CIMA® (Certified Investment Management Analyst) professionals must complete continuing education requirements as specified by the Investments & Wealth Institute. Requirements include ethics and investment management topics.',
        'CIMC': 'CIMC® (Certified Investment Management Consultant) professionals must complete continuing education requirements as specified by the Investments & Wealth Institute.',
        'CPWA': 'CPWA professionals must complete continuing education requirements as specified by the Investments & Wealth Institute. Check with the Institute for current requirements.',
        'CRPS': 'CRPS® (Chartered Retirement Plans Specialist) professionals must complete continuing education requirements as specified by The College for Financial Planning. Requirements focus on retirement planning and employee benefits.',
        'RICP': 'RICP® (Retirement Income Certified Professional) professionals must complete continuing education requirements as specified by The American College. Requirements focus on retirement income planning.',
        'CDFA': 'CDFA® (Certified Divorce Financial Analyst) professionals must complete continuing education requirements as specified by the Institute for Divorce Financial Analysts. Requirements focus on divorce financial planning.',
        'AIF': 'AIF® (Accredited Investment Fiduciary) professionals must complete continuing education requirements as specified by Fi360. Requirements focus on fiduciary responsibility and investment management.',
        'IAR': 'Investment Adviser Representatives (IARs) must complete continuing education requirements that vary by state. Requirements typically include ethics and investment advisory topics. Check your state securities regulator for exact requirements.',
        'CEP': 'Certified Equity Professional (CEP) designation requires 30 hours of continuing education every two years. Maintaining the CEP certification requires completing at least 30 hours of required continuing education every two years. There is a $250 administrative fee (waived after 15 hours of volunteer work). Continuing education can include conferences, courses, exams, and other industry events. Track your CE online via CEPI Connect. Based on CEPI requirements: https://www.scu.edu/execed/cepi/continuing-education/',
        'ECA': 'Equity Compensation Associate (ECA) designation requires 30 hours of continuing education every two years. The ECA is the first level in the Certified Equity Professional (CEP) certification process. Passing the ECA exam demonstrates foundational knowledge of the equity compensation field. There is a $250 administrative fee (waived after 15 hours of volunteer work). Continuing education can include conferences, courses, exams, and other industry events. Track your CE online via CEPI Connect. Based on CEPI requirements: https://www.scu.edu/execed/cepi/continuing-education/'
    }
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        designations = request.form.getlist('designations')  # Get list of selected designations
        cfp_birth_month = request.form.get('cfp_birth_month', '')
        cpa_state = request.form.get('cpa_state', '')
        is_napfa_member = request.form.get('is_napfa_member') == 'on'
        napfa_join_date = request.form.get('napfa_join_date', '')
        
        # Prepare form data to preserve on error
        form_data = {
            'username': username,
            'email': email,
            'designations': designations,
            'cfp_birth_month': cfp_birth_month,
            'cpa_state': cpa_state,
            'is_napfa_member': is_napfa_member,
            'napfa_join_date': napfa_join_date
        }
        
        # Validation
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
        
        # Validate CFP birth month if CFP is selected
        if 'CFP' in designations:
            if not cfp_birth_month:
                errors.append('Birth month is required for CFP designation.')
            else:
                try:
                    birth_month = int(cfp_birth_month)
                    if birth_month < 1 or birth_month > 12:
                        errors.append('Birth month must be between 1 and 12.')
                except ValueError:
                    errors.append('Invalid birth month.')
        
        # Validate CPA state if CPA is selected
        if 'CPA' in designations:
            if not cpa_state:
                errors.append('State is required for CPA designation.')
            elif len(cpa_state) != 2 or not cpa_state.isalpha():
                errors.append('Invalid state abbreviation. Please use a 2-letter state code (e.g., CA, NY, TX).')
        
        # Validate NAPFA join date if NAPFA member
        napfa_join_date_obj = None
        if is_napfa_member:
            if not napfa_join_date:
                errors.append('NAPFA join date is required if you are a NAPFA member.')
            else:
                try:
                    napfa_join_date_obj = datetime.strptime(napfa_join_date, '%Y-%m-%d').date()
                except ValueError:
                    errors.append('Invalid NAPFA join date format.')
        
        # If there are validation errors, return with form data preserved
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('register.html', 
                                 designation_requirements=designation_requirements,
                                 form_data=form_data)
        
        # Check if user exists (only after basic validation passes)
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return render_template('register.html', 
                                 designation_requirements=designation_requirements,
                                 form_data=form_data)
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists.', 'error')
            return render_template('register.html', 
                                 designation_requirements=designation_requirements,
                                 form_data=form_data)
        
        # Create new user
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            is_napfa_member=is_napfa_member,
            napfa_join_date=napfa_join_date_obj
        )
        db.session.add(user)
        db.session.flush()  # Get user ID
        
        # Add designations
        # Allowed designations
        allowed_designations = ['CFP', 'CFA', 'CPA', 'CLE', 'CLU', 'EA', 'ChFC', 'CIMA', 'CIMC', 'CPWA', 'CRPS', 'RICP', 'CDFA', 'AIF', 'IAR', 'CEP', 'ECA']
        for designation in designations:
            if designation in allowed_designations:
                user_designation = UserDesignation(
                    user_id=user.id,
                    designation=designation,
                    birth_month=int(cfp_birth_month) if designation == 'CFP' and cfp_birth_month else None,
                    state=cpa_state.upper() if designation == 'CPA' and cpa_state else None
                )
                db.session.add(user_designation)
        
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html', designation_requirements=designation_requirements)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
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
                session['show_napfa_tracking'] = user.is_napfa_member  # Default to showing if NAPFA member
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid password. Please try again.', 'error')
                return render_template('login.html')
        except Exception as e:
            flash('An error occurred during login. Please try again.', 'error')
            print(f"Login error: {e}")  # Log the error for debugging
            return render_template('login.html')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if 'user_id' in session:
        return redirect(url_for('profile'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()

        if not email:
            flash('Please enter your email address.', 'error')
            return render_template('forgot_password.html')

        user = User.query.filter_by(email=email).first()

        if user:
            # Generate a unique reset token
            token = uuid.uuid4().hex
            user.reset_token = token
            user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            # In production, this token would be emailed. For now, redirect directly.
            return redirect(url_for('reset_password', token=token))

        # Don't reveal whether the email exists
        flash('If an account with that email exists, a reset link has been generated.', 'info')
        return render_template('forgot_password.html')

    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()

    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.utcnow():
        flash('This reset link is invalid or has expired.', 'error')
        return redirect(url_for('forgot_password'))

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
        return redirect(url_for('login'))

    return render_template('reset_password.html', token=token)

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        flash('Please log in to access your profile.', 'error')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_email':
            new_email = request.form.get('email', '').strip()

            if not new_email:
                flash('Email is required.', 'error')
                return redirect(url_for('profile'))

            if '@' not in new_email or '.' not in new_email:
                flash('Please enter a valid email address.', 'error')
                return redirect(url_for('profile'))

            # Check if email is already taken by another user
            existing_user = User.query.filter_by(email=new_email).first()
            if existing_user and existing_user.id != user.id:
                flash('That email is already in use by another account.', 'error')
                return redirect(url_for('profile'))

            if new_email == user.email:
                flash('That is already your current email.', 'error')
                return redirect(url_for('profile'))

            user.email = new_email
            db.session.commit()
            flash('Email updated successfully!', 'success')
            return redirect(url_for('profile'))

        elif action == 'change_password':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')

            if not current_password:
                flash('Current password is required.', 'error')
                return redirect(url_for('profile'))

            if not check_password_hash(user.password_hash, current_password):
                flash('Current password is incorrect.', 'error')
                return redirect(url_for('profile'))

            if not new_password:
                flash('New password is required.', 'error')
                return redirect(url_for('profile'))

            if len(new_password) < 6:
                flash('New password must be at least 6 characters long.', 'error')
                return redirect(url_for('profile'))

            if new_password != confirm_password:
                flash('New passwords do not match.', 'error')
                return redirect(url_for('profile'))

            user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('profile'))

    # Get designation count for account info
    designation_count = UserDesignation.query.filter_by(user_id=user.id).count()

    return render_template('profile.html', user=user, designation_count=designation_count)


@app.route('/add_ce', methods=['GET', 'POST'])
def add_ce():
    if 'user_id' not in session:
        flash('Please log in to add CE records.', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        title = request.form.get('title')
        provider = request.form.get('provider')
        hours = request.form.get('hours')
        date_completed = request.form.get('date_completed')
        category = request.form.get('category')
        description = request.form.get('description')
        is_napfa_approved = request.form.get('is_napfa_approved') == 'on'
        is_ethics_course = request.form.get('is_ethics_course') == 'on'
        napfa_subject_area = request.form.get('napfa_subject_area')
        
        # Validation
        if not title or not hours or not date_completed:
            flash('Title, hours, and date completed are required.', 'error')
            return redirect(url_for('dashboard'))
        
        try:
            hours = float(hours)
            date_completed = datetime.strptime(date_completed, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid hours or date format.', 'error')
            return redirect(url_for('dashboard'))
        
        # Handle file upload
        certificate_filename = None
        if 'certificate' in request.files:
            file = request.files['certificate']
            if file and file.filename != '':
                if allowed_file(file.filename):
                    ensure_upload_directory()
                    # Generate unique filename to avoid conflicts
                    original_filename = secure_filename(file.filename)
                    file_ext = original_filename.rsplit('.', 1)[1].lower()
                    unique_filename = f"{uuid.uuid4().hex}.{file_ext}"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    file.save(file_path)
                    certificate_filename = unique_filename
                else:
                    flash('Only PDF files are allowed for certificates.', 'error')
                    return redirect(url_for('dashboard'))
        
        # Create CE record
        ce_record = CERecord(
            user_id=session['user_id'],
            title=title,
            provider=provider or '',
            hours=hours,
            date_completed=date_completed,
            category=category or '',
            description=description or '',
            is_napfa_approved=is_napfa_approved,
            is_ethics_course=is_ethics_course,
            napfa_subject_area=napfa_subject_area or '',
            certificate_filename=certificate_filename
        )
        
        db.session.add(ce_record)
        db.session.commit()
        
        flash('CE record added successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('add_ce.html', user=user)

@app.route('/certificate/<int:ce_id>')
def download_certificate(ce_id):
    """Download/view certificate PDF"""
    if 'user_id' not in session:
        flash('Please log in.', 'error')
        return redirect(url_for('login'))
    
    ce_record = CERecord.query.get_or_404(ce_id)
    
    if ce_record.user_id != session['user_id']:
        flash('You do not have permission to access this certificate.', 'error')
        return redirect(url_for('dashboard'))
    
    if not ce_record.certificate_filename:
        flash('No certificate available for this CE record.', 'error')
        return redirect(url_for('dashboard'))
    
    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        ce_record.certificate_filename,
        as_attachment=True
    )

@app.route('/delete_ce/<int:ce_id>', methods=['POST'])
def delete_ce(ce_id):
    if 'user_id' not in session:
        flash('Please log in.', 'error')
        return redirect(url_for('login'))
    
    ce_record = CERecord.query.get_or_404(ce_id)
    
    if ce_record.user_id != session['user_id']:
        flash('You do not have permission to delete this record.', 'error')
        return redirect(url_for('dashboard'))
    
    # Delete associated certificate file if it exists
    if ce_record.certificate_filename:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], ce_record.certificate_filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass  # File might already be deleted
    
    db.session.delete(ce_record)
    db.session.commit()
    
    flash('CE record deleted successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/edit_ce/<int:ce_id>', methods=['POST'])
def edit_ce(ce_id):
    if 'user_id' not in session:
        flash('Please log in.', 'error')
        return redirect(url_for('login'))

    ce_record = CERecord.query.get_or_404(ce_id)

    if ce_record.user_id != session['user_id']:
        flash('You do not have permission to edit this record.', 'error')
        return redirect(url_for('dashboard'))

    title = request.form.get('title')
    provider = request.form.get('provider')
    hours = request.form.get('hours')
    date_completed = request.form.get('date_completed')
    category = request.form.get('category')
    description = request.form.get('description')
    is_napfa_approved = request.form.get('is_napfa_approved') == 'on'
    is_ethics_course = request.form.get('is_ethics_course') == 'on'
    napfa_subject_area = request.form.get('napfa_subject_area')

    # Validation
    if not title or not hours or not date_completed:
        flash('Title, hours, and date completed are required.', 'error')
        return redirect(url_for('dashboard'))

    try:
        hours = float(hours)
        date_completed = datetime.strptime(date_completed, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid hours or date format.', 'error')
        return redirect(url_for('dashboard'))

    # Handle certificate file upload replacement
    if 'certificate' in request.files:
        file = request.files['certificate']
        if file and file.filename != '':
            if allowed_file(file.filename):
                ensure_upload_directory()
                # Delete old certificate file if it exists
                if ce_record.certificate_filename:
                    old_file_path = os.path.join(app.config['UPLOAD_FOLDER'], ce_record.certificate_filename)
                    if os.path.exists(old_file_path):
                        try:
                            os.remove(old_file_path)
                        except OSError:
                            pass  # File might already be deleted
                # Save new certificate file
                original_filename = secure_filename(file.filename)
                file_ext = original_filename.rsplit('.', 1)[1].lower()
                unique_filename = f"{uuid.uuid4().hex}.{file_ext}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)
                ce_record.certificate_filename = unique_filename
            else:
                flash('Only PDF files are allowed for certificates.', 'error')
                return redirect(url_for('dashboard'))

    # Update fields
    ce_record.title = title
    ce_record.provider = provider or ''
    ce_record.hours = hours
    ce_record.date_completed = date_completed
    ce_record.category = category or ''
    ce_record.description = description or ''
    ce_record.is_napfa_approved = is_napfa_approved
    ce_record.is_ethics_course = is_ethics_course
    ce_record.napfa_subject_area = napfa_subject_area or ''

    db.session.commit()

    flash('CE record updated successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/toggle_napfa_tracking', methods=['POST'])
def toggle_napfa_tracking():
    if 'user_id' not in session:
        flash('Please log in.', 'error')
        return redirect(url_for('login'))
    
    # Toggle NAPFA tracking visibility
    current_state = session.get('show_napfa_tracking', False)
    session['show_napfa_tracking'] = not current_state
    
    return redirect(url_for('dashboard'))

## something something

@app.route('/export_ce')
def export_ce():
    if 'user_id' not in session:
        flash('Please log in.', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    
    # Get filter category from query parameter (same as dashboard)
    filter_category = request.args.get('category', '')
    
    # Base query
    query = CERecord.query.filter_by(user_id=user.id)
    
    # Apply category filter if provided
    if filter_category:
        query = query.filter(CERecord.category == filter_category)
    
    ce_records = query.order_by(CERecord.date_completed.desc()).all()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Date Completed', 'Title', 'Provider', 'Category', 'Hours', 'Description'])
    
    # Write data
    for record in ce_records:
        writer.writerow([
            record.date_completed.strftime('%Y-%m-%d'),
            record.title,
            record.provider or '',
            record.category or '',
            record.hours,
            record.description or ''
        ])
    
    # Create response
    filename = f'ce_records_{datetime.now().strftime("%Y%m%d")}.csv'
    if filter_category:
        filename = f'ce_records_{filter_category.replace(" ", "_")}_{datetime.now().strftime("%Y%m%d")}.csv'
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/manage_designations', methods=['GET', 'POST'])
def manage_designations():
    if 'user_id' not in session:
        flash('Please log in to manage your designations.', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    
    # Designation requirements for tooltips
    designation_requirements = {
        'CFP': 'CFP® professionals must complete 30 hours of continuing education (CE) every two years, which includes 2 hours of CFP Board-approved Ethics CE and 28 hours in one or more of the CFP Board\'s Principal Topics. The CE requirement begins immediately upon initial certification or 12 months after passing the exam if experience and/or degree requirements are not yet met. Excess CE hours cannot be carried over to the next reporting period.',
        'CFA': 'CFA charterholders must complete continuing education (CE) requirements through the CFA Institute. Requirements include professional learning activities and may vary based on membership status.',
        'CPA': 'CPAs must complete continuing professional education (CPE) requirements that vary by state. Most states require 40 hours of CPE per year, with specific requirements for ethics courses. Check your state board for exact requirements.',
        'CLE': 'Continuing Legal Education (CLE) requirements vary by state and jurisdiction. Most states require attorneys to complete a certain number of CLE hours annually or biennially, with specific requirements for ethics courses.',
        'CLU': 'CLU professionals must complete continuing education requirements as specified by The American College. Requirements typically include ethics and other professional development courses.',
        'EA': 'Enrolled Agents (EAs) must complete 72 hours of continuing education (CE) every three years, with a minimum of 16 hours per year. At least 2 hours must be on ethics.',
        'ChFC': 'ChFC® (Chartered Financial Consultant) professionals must complete continuing education requirements as specified by The American College. Requirements typically include ethics and financial planning topics.',
        'CIMA': 'CIMA® (Certified Investment Management Analyst) professionals must complete continuing education requirements as specified by the Investments & Wealth Institute. Requirements include ethics and investment management topics.',
        'CIMC': 'CIMC® (Certified Investment Management Consultant) professionals must complete continuing education requirements as specified by the Investments & Wealth Institute.',
        'CPWA': 'CPWA professionals must complete continuing education requirements as specified by the Investments & Wealth Institute. Check with the Institute for current requirements.',
        'CRPS': 'CRPS® (Chartered Retirement Plans Specialist) professionals must complete continuing education requirements as specified by The College for Financial Planning. Requirements focus on retirement planning and employee benefits.',
        'RICP': 'RICP® (Retirement Income Certified Professional) professionals must complete continuing education requirements as specified by The American College. Requirements focus on retirement income planning.',
        'CDFA': 'CDFA® (Certified Divorce Financial Analyst) professionals must complete continuing education requirements as specified by the Institute for Divorce Financial Analysts. Requirements focus on divorce financial planning.',
        'AIF': 'AIF® (Accredited Investment Fiduciary) professionals must complete continuing education requirements as specified by Fi360. Requirements focus on fiduciary responsibility and investment management.',
        'IAR': 'Investment Adviser Representatives (IARs) must complete continuing education requirements that vary by state. Requirements typically include ethics and investment advisory topics. Check your state securities regulator for exact requirements.',
        'CEP': 'Certified Equity Professional (CEP) designation requires 30 hours of continuing education every two years. Maintaining the CEP certification requires completing at least 30 hours of required continuing education every two years. There is a $250 administrative fee (waived after 15 hours of volunteer work). Continuing education can include conferences, courses, exams, and other industry events. Track your CE online via CEPI Connect. Based on CEPI requirements: https://www.scu.edu/execed/cepi/continuing-education/',
        'ECA': 'Equity Compensation Associate (ECA) designation requires 30 hours of continuing education every two years. The ECA is the first level in the Certified Equity Professional (CEP) certification process. Passing the ECA exam demonstrates foundational knowledge of the equity compensation field. There is a $250 administrative fee (waived after 15 hours of volunteer work). Continuing education can include conferences, courses, exams, and other industry events. Track your CE online via CEPI Connect. Based on CEPI requirements: https://www.scu.edu/execed/cepi/continuing-education/'
    }
    
    # Get user's current designations
    user_designations = UserDesignation.query.filter_by(user_id=user.id).all()
    current_designations = {ud.designation: ud for ud in user_designations}
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            designation = request.form.get('designation')
            cfp_birth_month = request.form.get('cfp_birth_month')
            cpa_state = request.form.get('cpa_state')
            
            allowed_designations = ['CFP', 'CFA', 'CPA', 'CLE', 'CLU', 'EA', 'ChFC', 'CIMA', 'CIMC', 'CPWA', 'CRPS', 'RICP', 'CDFA', 'AIF', 'IAR', 'CEP', 'ECA']
            if not designation or designation not in allowed_designations:
                flash('Invalid designation.', 'error')
                return redirect(url_for('manage_designations'))
            
            # Check if already has this designation
            if designation in current_designations:
                flash(f'You already have the {designation} designation.', 'error')
                return redirect(url_for('manage_designations'))
            
            # Validate CFP birth month
            birth_month = None
            if designation == 'CFP':
                if not cfp_birth_month:
                    flash('Birth month is required for CFP designation.', 'error')
                    return redirect(url_for('manage_designations'))
                try:
                    birth_month = int(cfp_birth_month)
                    if birth_month < 1 or birth_month > 12:
                        flash('Birth month must be between 1 and 12.', 'error')
                        return redirect(url_for('manage_designations'))
                except ValueError:
                    flash('Invalid birth month.', 'error')
                    return redirect(url_for('manage_designations'))
            
            # Validate CPA state
            state = None
            if designation == 'CPA':
                if not cpa_state:
                    flash('State is required for CPA designation.', 'error')
                    return redirect(url_for('manage_designations'))
                # Validate state abbreviation (2 letters)
                if len(cpa_state) != 2 or not cpa_state.isalpha():
                    flash('Invalid state abbreviation. Please use a 2-letter state code (e.g., CA, NY, TX).', 'error')
                    return redirect(url_for('manage_designations'))
                state = cpa_state.upper()
            
            # Add designation
            user_designation = UserDesignation(
                user_id=user.id,
                designation=designation,
                birth_month=birth_month,
                state=state
            )
            db.session.add(user_designation)
            db.session.commit()
            
            flash(f'{designation} designation added successfully!', 'success')
            return redirect(url_for('manage_designations'))
        
        elif action == 'remove':
            designation_id = request.form.get('designation_id')
            user_designation = UserDesignation.query.get_or_404(designation_id)
            
            if user_designation.user_id != user.id:
                flash('You do not have permission to remove this designation.', 'error')
                return redirect(url_for('manage_designations'))
            
            designation_name = user_designation.designation
            db.session.delete(user_designation)
            db.session.commit()
            
            flash(f'{designation_name} designation removed successfully!', 'success')
            return redirect(url_for('manage_designations'))
    
    return render_template('manage_designations.html', 
                         current_designations=current_designations,
                         designation_requirements=designation_requirements)

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    """Handle feedback submission from the modal"""
    name = request.form.get('feedback_name', '').strip()
    email = request.form.get('feedback_email', '').strip()
    feedback_type = request.form.get('feedback_type', '').strip()
    message = request.form.get('feedback_message', '').strip()
    
    # Validation
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
        return redirect(request.referrer or url_for('dashboard'))
    
    # Create feedback record
    feedback = Feedback(
        name=name,
        email=email,
        feedback_type=feedback_type,
        message=message,
        user_id=session.get('user_id')  # Will be None if not logged in
    )
    
    db.session.add(feedback)
    db.session.commit()
    
    flash('Thank you for your feedback! We appreciate you taking the time to help us improve.', 'success')
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/admin/feedback')
def view_feedback():
    """View all feedback submissions - protected by admin key"""
    # Simple protection: require an admin key in the URL
    admin_key = request.args.get('key', '')
    expected_key = os.environ.get('ADMIN_KEY', 'cetracker2025admin')
    
    if admin_key != expected_key:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('login'))
    
    # Get filter parameters
    filter_type = request.args.get('type', '')
    filter_read = request.args.get('read', '')
    
    # Build query
    query = Feedback.query
    
    if filter_type:
        query = query.filter(Feedback.feedback_type == filter_type)
    if filter_read == 'unread':
        query = query.filter(Feedback.is_read == False)
    elif filter_read == 'read':
        query = query.filter(Feedback.is_read == True)
    
    feedback_list = query.order_by(Feedback.created_at.desc()).all()
    
    # Count stats
    total_count = Feedback.query.count()
    unread_count = Feedback.query.filter(Feedback.is_read == False).count()
    
    return render_template('admin_feedback.html', 
                         feedback_list=feedback_list,
                         total_count=total_count,
                         unread_count=unread_count,
                         filter_type=filter_type,
                         filter_read=filter_read,
                         admin_key=admin_key)

@app.route('/admin/feedback/<int:feedback_id>/toggle_read', methods=['POST'])
def toggle_feedback_read(feedback_id):
    """Toggle the read status of a feedback item"""
    admin_key = request.args.get('key', '')
    expected_key = os.environ.get('ADMIN_KEY', 'cetracker2025admin')
    
    if admin_key != expected_key:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('login'))
    
    feedback = Feedback.query.get_or_404(feedback_id)
    feedback.is_read = not feedback.is_read
    db.session.commit()
    
    return redirect(url_for('view_feedback', key=admin_key))

@app.route('/admin/feedback/<int:feedback_id>/delete', methods=['POST'])
def delete_feedback(feedback_id):
    """Delete a feedback item"""
    admin_key = request.args.get('key', '')
    expected_key = os.environ.get('ADMIN_KEY', 'cetracker2025admin')
    
    if admin_key != expected_key:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('login'))
    
    feedback = Feedback.query.get_or_404(feedback_id)
    db.session.delete(feedback)
    db.session.commit()
    
    flash('Feedback deleted.', 'success')
    return redirect(url_for('view_feedback', key=admin_key))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please log in to access your dashboard.', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    
    # Get user's designations
    user_designations = UserDesignation.query.filter_by(user_id=user.id).all()
    
    # Get filter category from query parameter
    filter_category = request.args.get('category', '')
    
    # Base query
    query = CERecord.query.filter_by(user_id=user.id)
    
    # Apply category filter if provided
    if filter_category:
        query = query.filter(CERecord.category == filter_category)
    
    ce_records = query.order_by(CERecord.date_completed.desc()).all()
    
    # Get all unique categories for the filter dropdown
    all_categories = db.session.query(CERecord.category).filter_by(user_id=user.id).distinct().all()
    categories = [cat[0] for cat in all_categories if cat[0]]  # Filter out None/empty categories
    
    total_hours = sum(record.hours for record in ce_records)
    
    # Calculate NAPFA requirements if user is a NAPFA member
    napfa_requirements = calculate_napfa_requirements(user) if user.is_napfa_member else None
    
    # Get NAPFA toggle preference from session (default to True if NAPFA member)
    show_napfa = session.get('show_napfa_tracking', user.is_napfa_member)
    
    # Calculate designation requirements
    designation_requirements = calculate_designation_requirements(user, user_designations)
    
    return render_template('dashboard.html', ce_records=ce_records, total_hours=total_hours, 
                         categories=categories, filter_category=filter_category,
                         user_designations=user_designations,
                         napfa_requirements=napfa_requirements,
                         show_napfa=show_napfa,
                         designation_requirements=designation_requirements,
                         user=user)

def update_database_schema():
    """Add missing columns to existing database if they don't exist"""
    with app.app_context():
        # Detect database type
        is_postgresql = 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI'].lower()
        boolean_default = 'FALSE' if is_postgresql else '0'
        table_user = 'users'  # Use 'users' table name (changed from 'user' to avoid PostgreSQL reserved word)
        
        schema_updated = False
        
        # Update users table
        try:
            # Try to query the columns to see if they exist
            db.session.execute(text(f'SELECT is_napfa_member, napfa_join_date FROM {table_user} LIMIT 1'))
        except Exception:
            # Columns don't exist, add them
            try:
                print("Updating users table schema...")
                # Add is_napfa_member column
                try:
                    db.session.execute(text(f'ALTER TABLE {table_user} ADD COLUMN is_napfa_member BOOLEAN DEFAULT {boolean_default} NOT NULL'))
                    schema_updated = True
                except Exception as e:
                    error_msg = str(e).lower()
                    if "duplicate column" not in error_msg and "already exists" not in error_msg and "column" not in error_msg:
                        raise
                    print("Column is_napfa_member already exists.")
                
                # Add napfa_join_date column
                try:
                    db.session.execute(text(f'ALTER TABLE {table_user} ADD COLUMN napfa_join_date DATE'))
                    schema_updated = True
                except Exception as e:
                    error_msg = str(e).lower()
                    if "duplicate column" not in error_msg and "already exists" not in error_msg and "column" not in error_msg:
                        raise
                    print("Column napfa_join_date already exists.")

                # Add reset_token column
                try:
                    db.session.execute(text(f'ALTER TABLE {table_user} ADD COLUMN reset_token VARCHAR(100)'))
                    schema_updated = True
                except Exception as e:
                    error_msg = str(e).lower()
                    if "duplicate column" not in error_msg and "already exists" not in error_msg and "column" not in error_msg:
                        raise
                    print("Column reset_token already exists.")

                # Add reset_token_expiry column
                try:
                    db.session.execute(text(f'ALTER TABLE {table_user} ADD COLUMN reset_token_expiry DATETIME'))
                    schema_updated = True
                except Exception as e:
                    error_msg = str(e).lower()
                    if "duplicate column" not in error_msg and "already exists" not in error_msg and "column" not in error_msg:
                        raise
                    print("Column reset_token_expiry already exists.")

                if schema_updated:
                    db.session.commit()
                    print("Users table schema updated successfully!")
            except Exception as e:
                db.session.rollback()
                print(f"Error updating users table schema: {e}")
        
        # Update user_designation table
        schema_updated = False
        try:
            # Try to query the columns to see if they exist
            db.session.execute(text("SELECT birth_month, state FROM user_designation LIMIT 1"))
        except Exception:
            # Columns don't exist, add them
            try:
                print("Updating user_designation table schema...")
                # Add birth_month column
                try:
                    db.session.execute(text("ALTER TABLE user_designation ADD COLUMN birth_month INTEGER"))
                    schema_updated = True
                except Exception as e:
                    error_msg = str(e).lower()
                    if "duplicate column" not in error_msg and "already exists" not in error_msg and "column" not in error_msg:
                        raise
                    print("Column birth_month already exists.")
                
                # Add state column
                try:
                    db.session.execute(text("ALTER TABLE user_designation ADD COLUMN state VARCHAR(2)"))
                    schema_updated = True
                except Exception as e:
                    error_msg = str(e).lower()
                    if "duplicate column" not in error_msg and "already exists" not in error_msg and "column" not in error_msg:
                        raise
                    print("Column state already exists.")
                
                if schema_updated:
                    db.session.commit()
                    print("User_designation table schema updated successfully!")
            except Exception as e:
                db.session.rollback()
                print(f"Error updating user_designation table schema: {e}")
        
        # Update ce_record table
        ce_record_schema_updated = False
        try:
            print("Updating ce_record table schema...")
            # Add is_napfa_approved column
            try:
                db.session.execute(text(f"ALTER TABLE ce_record ADD COLUMN is_napfa_approved BOOLEAN DEFAULT {boolean_default} NOT NULL"))
                ce_record_schema_updated = True
                print("Added is_napfa_approved column.")
            except Exception as e:
                error_msg = str(e).lower()
                if "duplicate column" not in error_msg and "already exists" not in error_msg and "column" not in error_msg:
                    raise
                print("Column is_napfa_approved already exists.")
            
            # Add is_ethics_course column
            try:
                db.session.execute(text(f"ALTER TABLE ce_record ADD COLUMN is_ethics_course BOOLEAN DEFAULT {boolean_default} NOT NULL"))
                ce_record_schema_updated = True
                print("Added is_ethics_course column.")
            except Exception as e:
                error_msg = str(e).lower()
                if "duplicate column" not in error_msg and "already exists" not in error_msg and "column" not in error_msg:
                    raise
                print("Column is_ethics_course already exists.")
            
            # Add certificate_filename column
            try:
                db.session.execute(text("ALTER TABLE ce_record ADD COLUMN certificate_filename VARCHAR(255)"))
                ce_record_schema_updated = True
                print("Added certificate_filename column.")
            except Exception as e:
                error_msg = str(e).lower()
                if "duplicate column" not in error_msg and "already exists" not in error_msg and "column" not in error_msg:
                    raise
                print("Column certificate_filename already exists.")
            
            # Add napfa_subject_area column
            try:
                db.session.execute(text("ALTER TABLE ce_record ADD COLUMN napfa_subject_area VARCHAR(100)"))
                ce_record_schema_updated = True
                print("Added napfa_subject_area column.")
            except Exception as e:
                error_msg = str(e).lower()
                if "duplicate column" not in error_msg and "already exists" not in error_msg and "column" not in error_msg:
                    raise
                print("Column napfa_subject_area already exists.")
            
            if ce_record_schema_updated:
                db.session.commit()
                print("Ce_record table schema updated successfully!")
        except Exception as e:
            db.session.rollback()
            print(f"Error updating ce_record table schema: {e}")
        
        # Final check message
        try:
            db.session.execute(text(f'SELECT is_napfa_member, napfa_join_date FROM {table_user} LIMIT 1'))
            db.session.execute(text("SELECT birth_month, state FROM user_designation LIMIT 1"))
            db.session.execute(text("SELECT is_napfa_approved, is_ethics_course, certificate_filename, napfa_subject_area FROM ce_record LIMIT 1"))
            print("Database schema is up to date.")
        except Exception:
            pass  # Some columns still missing, but we tried to add them

# Initialize database on startup
def init_db():
    """Initialize database tables"""
    with app.app_context():
        print(f"Database URI: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")  # Log first 50 chars for debugging
        print(f"Creating database tables...")
        db.create_all()
        print(f"User table name: {User.__tablename__}")  # Verify table name
        update_database_schema()
        ensure_upload_directory()
        print("Database initialization complete!")

# Initialize on import (for Gunicorn)
init_db()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

