from flask import Blueprint, render_template, request, redirect, url_for, flash, session

from models import db, User, UserDesignation
from designation_helpers import DESIGNATION_REQUIREMENTS, ALLOWED_DESIGNATIONS

designations_bp = Blueprint('designations', __name__)


@designations_bp.route('/manage_designations', methods=['GET', 'POST'])
def manage_designations():
    if 'user_id' not in session:
        flash('Please log in to manage your designations.', 'error')
        return redirect(url_for('auth.login'))

    user = User.query.get(session['user_id'])
    user_designations = UserDesignation.query.filter_by(user_id=user.id).all()
    current_designations = {ud.designation: ud for ud in user_designations}

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            designation = request.form.get('designation')
            cfp_birth_month = request.form.get('cfp_birth_month')
            cpa_state = request.form.get('cpa_state')

            if not designation or designation not in ALLOWED_DESIGNATIONS:
                flash('Invalid designation.', 'error')
                return redirect(url_for('designations.manage_designations'))

            if designation in current_designations:
                flash(f'You already have the {designation} designation.', 'error')
                return redirect(url_for('designations.manage_designations'))

            birth_month = None
            if designation == 'CFP':
                if not cfp_birth_month:
                    flash('Birth month is required for CFP designation.', 'error')
                    return redirect(url_for('designations.manage_designations'))
                try:
                    birth_month = int(cfp_birth_month)
                    if birth_month < 1 or birth_month > 12:
                        flash('Birth month must be between 1 and 12.', 'error')
                        return redirect(url_for('designations.manage_designations'))
                except ValueError:
                    flash('Invalid birth month.', 'error')
                    return redirect(url_for('designations.manage_designations'))

            state = None
            if designation == 'CPA':
                if not cpa_state:
                    flash('State is required for CPA designation.', 'error')
                    return redirect(url_for('designations.manage_designations'))
                if len(cpa_state) != 2 or not cpa_state.isalpha():
                    flash('Invalid state abbreviation. Please use a 2-letter state code (e.g., CA, NY, TX).', 'error')
                    return redirect(url_for('designations.manage_designations'))
                state = cpa_state.upper()

            ud = UserDesignation(
                user_id=user.id, designation=designation,
                birth_month=birth_month, state=state
            )
            db.session.add(ud)
            db.session.commit()

            flash(f'{designation} designation added successfully!', 'success')
            return redirect(url_for('designations.manage_designations'))

        elif action == 'remove':
            designation_id = request.form.get('designation_id')
            ud = UserDesignation.query.get_or_404(designation_id)

            if ud.user_id != user.id:
                flash('You do not have permission to remove this designation.', 'error')
                return redirect(url_for('designations.manage_designations'))

            designation_name = ud.designation
            db.session.delete(ud)
            db.session.commit()

            flash(f'{designation_name} designation removed successfully!', 'success')
            return redirect(url_for('designations.manage_designations'))

    return render_template('manage_designations.html',
                           current_designations=current_designations,
                           designation_requirements=DESIGNATION_REQUIREMENTS)
