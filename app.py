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
    certificate_filename = db.Column(db.String(255))  # Stores the filename of uploaded PDF certificate
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserDesignation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    designation = db.Column(db.String(10), nullable=False)  # CFP, CPA, EA, CFA, CPWA, CLU
    birth_month = db.Column(db.Integer)  # For CFP only (1-12)
    state = db.Column(db.String(2))  # For CPA only (state abbreviation)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'designation', name='unique_user_designation'),)

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
    
    return {
        'designation': 'CFP',
        'total_required': total_required,
        'total_earned': total_hours,
        'total_remaining': max(0, total_required - total_hours),
        'ethics_required': ethics_required,
        'ethics_earned': min(ethics_hours, ethics_required),
        'ethics_remaining': max(0, ethics_required - ethics_hours),
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
    
    return {
        'designation': 'CPA',
        'state': user_designation.state,
        'total_required': hours_per_year,
        'total_earned': total_hours,
        'total_remaining': max(0, hours_per_year - total_hours),
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
    
    return {
        'designation': 'EA',
        'total_required': total_required,
        'total_earned': total_hours,
        'total_remaining': max(0, total_required - total_hours),
        'yearly_minimum': yearly_minimum,
        'current_year_hours': current_year_hours,
        'ethics_required': ethics_required,
        'ethics_earned': min(ethics_hours, ethics_required),
        'ethics_remaining': max(0, ethics_required - ethics_hours),
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= total_required and current_year_hours >= yearly_minimum and ethics_hours >= ethics_required
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
        # Add other designations as needed (CFA, CPWA, CLU)
    
    return requirements

def calculate_napfa_requirements(user):
    """
    Calculate NAPFA CE requirements based on join date.
    Based on NAPFA CE Guidelines: https://www.napfa.org/member-resources/ce-guidelines
    Current cycle: 2024-2025 (Jan 1, 2024 - Dec 31, 2025)
    """
    if not user.is_napfa_member or not user.napfa_join_date:
        return None
    
    # Current cycle dates
    cycle_start = datetime(2024, 1, 1).date()
    cycle_end = datetime(2025, 12, 31).date()
    
    join_date = user.napfa_join_date
    
    # Determine requirements based on join date
    if join_date <= datetime(2024, 6, 30).date():
        # Joined on or before June 30, 2024
        total_required = 60
        napfa_approved_required = 30
    elif join_date <= datetime(2024, 12, 31).date():
        # Joined July - December 2024
        total_required = 45
        napfa_approved_required = 30
    elif join_date <= datetime(2025, 6, 30).date():
        # Joined January - June 2025
        total_required = 30
        napfa_approved_required = 30
    else:
        # Joined July - December 2025
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
    
    return {
        'total_required': total_required,
        'total_earned': total_hours,
        'total_remaining': max(0, total_required - total_hours),
        'napfa_approved_required': napfa_approved_required,
        'napfa_approved_earned': napfa_approved_hours,
        'napfa_approved_remaining': max(0, napfa_approved_required - napfa_approved_hours),
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
        'CPA': 'CPAs must complete continuing professional education (CPE) requirements that vary by state. Most states require 40 hours of CPE per year, with specific requirements for ethics courses. Check your state board for exact requirements.',
        'EA': 'Enrolled Agents (EAs) must complete 72 hours of continuing education (CE) every three years, with a minimum of 16 hours per year. At least 2 hours must be on ethics.',
        'CFA': 'CFA charterholders must complete continuing education (CE) requirements through the CFA Institute. Requirements include professional learning activities and may vary based on membership status.',
        'CPWA': 'CPWA professionals must complete continuing education requirements as specified by the Investments & Wealth Institute. Check with the Institute for current requirements.',
        'CLU': 'CLU professionals must complete continuing education requirements as specified by The American College. Requirements typically include ethics and other professional development courses.'
    }
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        designations = request.form.getlist('designations')  # Get list of selected designations
        cfp_birth_month = request.form.get('cfp_birth_month')
        cpa_state = request.form.get('cpa_state')
        is_napfa_member = request.form.get('is_napfa_member') == 'on'
        napfa_join_date = request.form.get('napfa_join_date')
        
        # Validation
        if not username or not email or not password:
            flash('All fields are required.', 'error')
            return render_template('register.html', designation_requirements=designation_requirements)
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('register.html', designation_requirements=designation_requirements)
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('register.html', designation_requirements=designation_requirements)
        
        # Validate CFP birth month if CFP is selected
        if 'CFP' in designations:
            if not cfp_birth_month:
                flash('Birth month is required for CFP designation.', 'error')
                return render_template('register.html', designation_requirements=designation_requirements)
            try:
                birth_month = int(cfp_birth_month)
                if birth_month < 1 or birth_month > 12:
                    flash('Birth month must be between 1 and 12.', 'error')
                    return render_template('register.html', designation_requirements=designation_requirements)
            except ValueError:
                flash('Invalid birth month.', 'error')
                return render_template('register.html', designation_requirements=designation_requirements)
        
        # Validate CPA state if CPA is selected
        if 'CPA' in designations:
            if not cpa_state:
                flash('State is required for CPA designation.', 'error')
                return render_template('register.html', designation_requirements=designation_requirements)
            # Validate state abbreviation (2 letters)
            if len(cpa_state) != 2 or not cpa_state.isalpha():
                flash('Invalid state abbreviation. Please use a 2-letter state code (e.g., CA, NY, TX).', 'error')
                return render_template('register.html', designation_requirements=designation_requirements)
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return render_template('register.html', designation_requirements=designation_requirements)
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists.', 'error')
            return render_template('register.html', designation_requirements=designation_requirements)
        
        # Validate NAPFA join date if NAPFA member
        napfa_join_date_obj = None
        if is_napfa_member:
            if not napfa_join_date:
                flash('NAPFA join date is required if you are a NAPFA member.', 'error')
                return render_template('register.html', designation_requirements=designation_requirements)
            try:
                napfa_join_date_obj = datetime.strptime(napfa_join_date, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid NAPFA join date format.', 'error')
                return render_template('register.html', designation_requirements=designation_requirements)
        
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
        for designation in designations:
            if designation in ['CFP', 'CPA', 'EA', 'CFA', 'CPWA', 'CLU']:
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
        'CPA': 'CPAs must complete continuing professional education (CPE) requirements that vary by state. Most states require 40 hours of CPE per year, with specific requirements for ethics courses. Check your state board for exact requirements.',
        'EA': 'Enrolled Agents (EAs) must complete 72 hours of continuing education (CE) every three years, with a minimum of 16 hours per year. At least 2 hours must be on ethics.',
        'CFA': 'CFA charterholders must complete continuing education (CE) requirements through the CFA Institute. Requirements include professional learning activities and may vary based on membership status.',
        'CPWA': 'CPWA professionals must complete continuing education requirements as specified by the Investments & Wealth Institute. Check with the Institute for current requirements.',
        'CLU': 'CLU professionals must complete continuing education requirements as specified by The American College. Requirements typically include ethics and other professional development courses.'
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
            
            if not designation or designation not in ['CFP', 'CPA', 'EA', 'CFA', 'CPWA', 'CLU']:
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
            db.session.execute(text("SELECT is_napfa_approved, is_ethics_course, certificate_filename FROM ce_record LIMIT 1"))
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

