from flask import Blueprint, render_template, request, redirect, url_for, flash, session, Response, current_app
from datetime import datetime, timedelta, timezone
import csv
import io
import json

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from models import db, User, CERecord, UserDesignation
from designation_helpers import calculate_designation_requirements, calculate_napfa_requirements

ce_bp = Blueprint('ce_records', __name__)


@ce_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please log in to access your dashboard.', 'error')
        return redirect(url_for('auth.login'))

    user = User.query.get(session['user_id'])
    user_designations = UserDesignation.query.filter_by(user_id=user.id).all()
    filter_category = request.args.get('category', '')

    query = CERecord.query.filter_by(user_id=user.id)
    if filter_category:
        query = query.filter(CERecord.category == filter_category)
    ce_records = query.order_by(CERecord.date_completed.desc()).all()

    all_categories = db.session.query(CERecord.category).filter_by(user_id=user.id).distinct().all()
    categories = [cat[0] for cat in all_categories if cat[0]]
    total_hours = sum(r.hours for r in ce_records)

    napfa_requirements = calculate_napfa_requirements(user) if user.is_napfa_member else None
    show_napfa = session.get('show_napfa_tracking', user.is_napfa_member)
    designation_requirements = calculate_designation_requirements(user, user_designations)

    return render_template('dashboard.html', ce_records=ce_records, total_hours=total_hours,
                           categories=categories, filter_category=filter_category,
                           user_designations=user_designations,
                           napfa_requirements=napfa_requirements,
                           show_napfa=show_napfa,
                           designation_requirements=designation_requirements,
                           user=user)


@ce_bp.route('/add_ce', methods=['GET', 'POST'])
def add_ce():
    if 'user_id' not in session:
        flash('Please log in to add CE records.', 'error')
        return redirect(url_for('auth.login'))

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

        if not title or not hours or not date_completed:
            flash('Title, hours, and date completed are required.', 'error')
            return redirect(url_for('ce_records.dashboard'))

        try:
            hours = float(hours)
            date_completed = datetime.strptime(date_completed, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid hours or date format.', 'error')
            return redirect(url_for('ce_records.dashboard'))

        ce_record = CERecord(
            user_id=session['user_id'], title=title, provider=provider or '',
            hours=hours, date_completed=date_completed, category=category or '',
            description=description or '', is_napfa_approved=is_napfa_approved,
            is_ethics_course=is_ethics_course, napfa_subject_area=napfa_subject_area or ''
        )
        db.session.add(ce_record)
        db.session.commit()

        flash('CE record added successfully!', 'success')
        return redirect(url_for('ce_records.dashboard'))

    return render_template('add_ce.html', user=user)


@ce_bp.route('/delete_ce/<int:ce_id>', methods=['POST'])
def delete_ce(ce_id):
    if 'user_id' not in session:
        flash('Please log in.', 'error')
        return redirect(url_for('auth.login'))

    ce_record = CERecord.query.get_or_404(ce_id)
    if ce_record.user_id != session['user_id']:
        flash('You do not have permission to delete this record.', 'error')
        return redirect(url_for('ce_records.dashboard'))

    db.session.delete(ce_record)
    db.session.commit()
    flash('CE record deleted successfully!', 'success')
    return redirect(url_for('ce_records.dashboard'))


@ce_bp.route('/edit_ce/<int:ce_id>', methods=['POST'])
def edit_ce(ce_id):
    if 'user_id' not in session:
        flash('Please log in.', 'error')
        return redirect(url_for('auth.login'))

    ce_record = CERecord.query.get_or_404(ce_id)
    if ce_record.user_id != session['user_id']:
        flash('You do not have permission to edit this record.', 'error')
        return redirect(url_for('ce_records.dashboard'))

    title = request.form.get('title')
    provider = request.form.get('provider')
    hours = request.form.get('hours')
    date_completed = request.form.get('date_completed')
    category = request.form.get('category')
    description = request.form.get('description')
    is_napfa_approved = request.form.get('is_napfa_approved') == 'on'
    is_ethics_course = request.form.get('is_ethics_course') == 'on'
    napfa_subject_area = request.form.get('napfa_subject_area')

    if not title or not hours or not date_completed:
        flash('Title, hours, and date completed are required.', 'error')
        return redirect(url_for('ce_records.dashboard'))

    try:
        hours = float(hours)
        date_completed = datetime.strptime(date_completed, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid hours or date format.', 'error')
        return redirect(url_for('ce_records.dashboard'))

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
    return redirect(url_for('ce_records.dashboard'))


@ce_bp.route('/toggle_napfa_tracking', methods=['POST'])
def toggle_napfa_tracking():
    if 'user_id' not in session:
        flash('Please log in.', 'error')
        return redirect(url_for('auth.login'))
    session['show_napfa_tracking'] = not session.get('show_napfa_tracking', False)
    return redirect(url_for('ce_records.dashboard'))


@ce_bp.route('/import_ce', methods=['POST'])
def import_ce():
    if 'user_id' not in session:
        flash('Please log in.', 'error')
        return redirect(url_for('auth.login'))

    if 'csv_file' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('ce_records.dashboard'))

    file = request.files['csv_file']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('ce_records.dashboard'))

    if not file.filename.lower().endswith('.csv'):
        flash('Please upload a CSV file.', 'error')
        return redirect(url_for('ce_records.dashboard'))

    try:
        content = file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))

        # Normalize header names (strip whitespace, lowercase for matching)
        if not reader.fieldnames:
            flash('CSV file is empty or has no headers.', 'error')
            return redirect(url_for('ce_records.dashboard'))

        field_map = {}
        for f in reader.fieldnames:
            normalized = f.strip().lower().replace('_', ' ')
            if normalized in ('date completed', 'date', 'completion date'):
                field_map['date_completed'] = f
            elif normalized in ('title', 'course title', 'course name', 'name'):
                field_map['title'] = f
            elif normalized in ('provider', 'sponsor', 'source'):
                field_map['provider'] = f
            elif normalized in ('category', 'type', 'subject'):
                field_map['category'] = f
            elif normalized in ('hours', 'credit hours', 'credits', 'ce hours', 'cpe hours'):
                field_map['hours'] = f
            elif normalized in ('description', 'notes', 'details'):
                field_map['description'] = f

        if 'title' not in field_map or 'hours' not in field_map:
            flash('CSV must have at least "Title" and "Hours" columns. Found columns: ' + ', '.join(reader.fieldnames), 'error')
            return redirect(url_for('ce_records.dashboard'))

        imported = 0
        skipped = 0
        errors = []

        for row_num, row in enumerate(reader, start=2):
            title = row.get(field_map.get('title', ''), '').strip()
            hours_str = row.get(field_map.get('hours', ''), '').strip()
            date_str = row.get(field_map.get('date_completed', ''), '').strip()
            provider = row.get(field_map.get('provider', ''), '').strip()
            category = row.get(field_map.get('category', ''), '').strip()
            description = row.get(field_map.get('description', ''), '').strip()

            if not title and not hours_str:
                continue  # skip blank rows

            if not title:
                errors.append(f'Row {row_num}: Missing title')
                skipped += 1
                continue

            try:
                hours = float(hours_str)
                if hours <= 0:
                    errors.append(f'Row {row_num}: Hours must be positive ("{title}")')
                    skipped += 1
                    continue
            except (ValueError, TypeError):
                errors.append(f'Row {row_num}: Invalid hours "{hours_str}" for "{title}"')
                skipped += 1
                continue

            date_completed = None
            if date_str:
                for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%m/%d/%y', '%d/%m/%Y', '%Y/%m/%d'):
                    try:
                        date_completed = datetime.strptime(date_str, fmt).date()
                        break
                    except ValueError:
                        continue
                if not date_completed:
                    errors.append(f'Row {row_num}: Could not parse date "{date_str}" for "{title}", using today')
                    date_completed = datetime.now().date()
            else:
                date_completed = datetime.now().date()

            # Check for duplicates (same title, date, and hours for this user)
            existing = CERecord.query.filter_by(
                user_id=session['user_id'],
                title=title,
                date_completed=date_completed,
                hours=hours
            ).first()

            if existing:
                skipped += 1
                errors.append(f'Row {row_num}: Duplicate skipped ("{title}" on {date_completed})')
                continue

            record = CERecord(
                user_id=session['user_id'],
                title=title,
                provider=provider,
                hours=hours,
                date_completed=date_completed,
                category=category,
                description=description
            )
            db.session.add(record)
            imported += 1

        db.session.commit()

        msg = f'Successfully imported {imported} CE record{"s" if imported != 1 else ""}.'
        if skipped:
            msg += f' {skipped} row{"s" if skipped != 1 else ""} skipped.'
        flash(msg, 'success')

        if errors:
            flash('Import notes: ' + '; '.join(errors[:10]) + ('...' if len(errors) > 10 else ''), 'info')

    except UnicodeDecodeError:
        flash('Could not read the file. Please ensure it is a UTF-8 encoded CSV.', 'error')
    except Exception as e:
        db.session.rollback()
        flash(f'Error importing CSV: {str(e)}', 'error')

    return redirect(url_for('ce_records.dashboard'))


@ce_bp.route('/export_ce')
def export_ce():
    if 'user_id' not in session:
        flash('Please log in.', 'error')
        return redirect(url_for('auth.login'))

    user = User.query.get(session['user_id'])
    filter_category = request.args.get('category', '')

    query = CERecord.query.filter_by(user_id=user.id)
    if filter_category:
        query = query.filter(CERecord.category == filter_category)
    ce_records = query.order_by(CERecord.date_completed.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date Completed', 'Title', 'Provider', 'Category', 'Hours', 'Description'])
    for record in ce_records:
        writer.writerow([
            record.date_completed.strftime('%Y-%m-%d'),
            record.title, record.provider or '', record.category or '',
            record.hours, record.description or ''
        ])

    filename = f'ce_records_{datetime.now().strftime("%Y%m%d")}.csv'
    if filter_category:
        filename = f'ce_records_{filter_category.replace(" ", "_")}_{datetime.now().strftime("%Y%m%d")}.csv'

    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})


@ce_bp.route('/export_pdf')
def export_pdf():
    if 'user_id' not in session:
        flash('Please log in.', 'error')
        return redirect(url_for('auth.login'))

    user = User.query.get(session['user_id'])
    filter_category = request.args.get('category', '')

    query = CERecord.query.filter_by(user_id=user.id)
    if filter_category:
        query = query.filter(CERecord.category == filter_category)
    ce_records = query.order_by(CERecord.date_completed.desc()).all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter),
                            topMargin=0.5 * inch, bottomMargin=0.5 * inch,
                            leftMargin=0.5 * inch, rightMargin=0.5 * inch)
    styles = getSampleStyleSheet()
    elements = []

    title_text = 'CE Records'
    if filter_category:
        title_text += f' — {filter_category}'
    elements.append(Paragraph(f'<b>{title_text}</b>', styles['Title']))
    elements.append(Paragraph(f'{user.username} | Exported {datetime.now().strftime("%B %d, %Y")}', styles['Normal']))
    elements.append(Spacer(1, 0.25 * inch))

    total_hours = sum(r.hours for r in ce_records)
    elements.append(Paragraph(f'Total Records: {len(ce_records)} | Total Hours: {total_hours:.1f}', styles['Normal']))
    elements.append(Spacer(1, 0.25 * inch))

    header = ['Date', 'Title', 'Provider', 'Category', 'Hours', 'Description']
    data = [header]
    for record in ce_records:
        data.append([
            record.date_completed.strftime('%Y-%m-%d'),
            Paragraph(record.title[:60], styles['Normal']),
            Paragraph((record.provider or '')[:40], styles['Normal']),
            record.category or '',
            str(record.hours),
            Paragraph((record.description or '')[:80], styles['Normal']),
        ])

    col_widths = [0.9 * inch, 2.5 * inch, 1.8 * inch, 1.5 * inch, 0.7 * inch, 2.6 * inch]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (4, 0), (4, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)

    filename = f'ce_records_{datetime.now().strftime("%Y%m%d")}.pdf'
    if filter_category:
        filename = f'ce_records_{filter_category.replace(" ", "_")}_{datetime.now().strftime("%Y%m%d")}.pdf'

    return Response(buffer.getvalue(), mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})


@ce_bp.route('/export_backup')
def export_backup():
    if 'user_id' not in session:
        flash('Please log in.', 'error')
        return redirect(url_for('auth.login'))

    user = User.query.get(session['user_id'])
    ce_records = CERecord.query.filter_by(user_id=user.id).order_by(CERecord.date_completed.desc()).all()
    designations = UserDesignation.query.filter_by(user_id=user.id).all()

    backup = {
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'user': {
            'username': user.username,
            'email': user.email,
            'is_napfa_member': user.is_napfa_member,
            'napfa_join_date': user.napfa_join_date.isoformat() if user.napfa_join_date else None,
        },
        'designations': [
            {
                'designation': d.designation,
                'birth_month': d.birth_month,
                'state': d.state,
            }
            for d in designations
        ],
        'ce_records': [
            {
                'title': r.title,
                'provider': r.provider or '',
                'hours': r.hours,
                'date_completed': r.date_completed.isoformat(),
                'category': r.category or '',
                'description': r.description or '',
                'is_napfa_approved': r.is_napfa_approved,
                'is_ethics_course': r.is_ethics_course,
                'napfa_subject_area': r.napfa_subject_area or '',
            }
            for r in ce_records
        ],
    }

    output = json.dumps(backup, indent=2)
    filename = f'ce_tracker_backup_{datetime.now().strftime("%Y%m%d")}.json'

    return Response(output, mimetype='application/json',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})


@ce_bp.route('/import_backup', methods=['POST'])
def import_backup():
    if 'user_id' not in session:
        flash('Please log in.', 'error')
        return redirect(url_for('auth.login'))

    if 'backup_file' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('ce_records.dashboard'))

    file = request.files['backup_file']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('ce_records.dashboard'))

    if not file.filename.lower().endswith('.json'):
        flash('Please upload a JSON file.', 'error')
        return redirect(url_for('ce_records.dashboard'))

    try:
        content = file.read().decode('utf-8')
        data = json.loads(content)

        if not isinstance(data, dict) or 'ce_records' not in data:
            flash('Invalid backup file: missing "ce_records" key.', 'error')
            return redirect(url_for('ce_records.dashboard'))

        records = data['ce_records']
        if not isinstance(records, list):
            flash('Invalid backup file: "ce_records" must be an array.', 'error')
            return redirect(url_for('ce_records.dashboard'))

        imported = 0
        skipped = 0
        errors = []

        for i, entry in enumerate(records):
            if not isinstance(entry, dict):
                errors.append(f'Record {i + 1}: not a valid object')
                skipped += 1
                continue

            title = str(entry.get('title', '')).strip()
            hours_raw = entry.get('hours')
            date_str = str(entry.get('date_completed', '')).strip()

            if not title:
                errors.append(f'Record {i + 1}: missing title')
                skipped += 1
                continue

            try:
                hours = float(hours_raw)
                if hours <= 0:
                    errors.append(f'Record {i + 1}: hours must be positive ("{title}")')
                    skipped += 1
                    continue
            except (ValueError, TypeError):
                errors.append(f'Record {i + 1}: invalid hours for "{title}"')
                skipped += 1
                continue

            date_completed = None
            if date_str:
                try:
                    date_completed = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    errors.append(f'Record {i + 1}: invalid date "{date_str}" for "{title}", using today')
                    date_completed = datetime.now().date()
            else:
                date_completed = datetime.now().date()

            # Duplicate detection: same title + date + hours
            existing = CERecord.query.filter_by(
                user_id=session['user_id'],
                title=title,
                date_completed=date_completed,
                hours=hours
            ).first()

            if existing:
                skipped += 1
                continue

            record = CERecord(
                user_id=session['user_id'],
                title=title,
                provider=str(entry.get('provider', '')).strip(),
                hours=hours,
                date_completed=date_completed,
                category=str(entry.get('category', '')).strip(),
                description=str(entry.get('description', '')).strip(),
                is_napfa_approved=bool(entry.get('is_napfa_approved', False)),
                is_ethics_course=bool(entry.get('is_ethics_course', False)),
                napfa_subject_area=str(entry.get('napfa_subject_area', '')).strip(),
            )
            db.session.add(record)
            imported += 1

        db.session.commit()

        msg = f'Successfully restored {imported} CE record{"s" if imported != 1 else ""}.'
        if skipped:
            msg += f' {skipped} skipped (duplicates or errors).'
        flash(msg, 'success')

        if errors:
            flash('Import notes: ' + '; '.join(errors[:10]) + ('...' if len(errors) > 10 else ''), 'info')

    except json.JSONDecodeError:
        flash('Invalid JSON file. Please upload a valid backup file.', 'error')
    except UnicodeDecodeError:
        flash('Could not read the file. Please ensure it is a UTF-8 encoded JSON file.', 'error')
    except Exception as e:
        db.session.rollback()
        flash(f'Error restoring backup: {str(e)}', 'error')

    return redirect(url_for('ce_records.dashboard'))


@ce_bp.route('/analytics')
def analytics():
    if 'user_id' not in session:
        flash('Please log in to view analytics.', 'error')
        return redirect(url_for('auth.login'))

    user = User.query.get(session['user_id'])
    ce_records = CERecord.query.filter_by(user_id=user.id).order_by(CERecord.date_completed.desc()).all()

    category_hours = {}
    for r in ce_records:
        cat = r.category or 'Uncategorized'
        category_hours[cat] = category_hours.get(cat, 0) + r.hours

    monthly_hours = {}
    now = datetime.now()
    for i in range(11, -1, -1):
        month_date = datetime(now.year, now.month, 1) - timedelta(days=i * 30)
        key = month_date.strftime('%Y-%m')
        monthly_hours[key] = 0
    for r in ce_records:
        key = r.date_completed.strftime('%Y-%m')
        if key in monthly_hours:
            monthly_hours[key] += r.hours

    provider_hours = {}
    for r in ce_records:
        prov = r.provider or 'Unknown'
        if prov:
            provider_hours[prov] = provider_hours.get(prov, 0) + r.hours
    top_providers = sorted(provider_hours.items(), key=lambda x: x[1], reverse=True)[:10]

    total_hours = sum(r.hours for r in ce_records)
    total_records = len(ce_records)
    avg_hours = total_hours / total_records if total_records else 0
    categories_count = len(category_hours)

    yearly_hours = {}
    for r in ce_records:
        year = str(r.date_completed.year)
        yearly_hours[year] = yearly_hours.get(year, 0) + r.hours

    return render_template('analytics.html', user=user,
                           category_hours=category_hours,
                           monthly_hours=monthly_hours,
                           top_providers=top_providers,
                           yearly_hours=yearly_hours,
                           total_hours=total_hours,
                           total_records=total_records,
                           avg_hours=avg_hours,
                           categories_count=categories_count)
