"""Designation CE requirement calculators."""
from datetime import datetime, timedelta
from models import CERecord


def calculate_cfp_requirements(user, user_designation):
    if not user_designation or user_designation.designation != 'CFP' or not user_designation.birth_month:
        return None

    birth_month = user_designation.birth_month
    current_date = datetime.now().date()
    current_year = current_date.year

    if current_date.month < birth_month:
        period_start = datetime(current_year - 2, birth_month, 1).date()
        period_end = datetime(current_year, birth_month, 1).date() - timedelta(days=1)
    else:
        period_start = datetime(current_year - 1, birth_month, 1).date()
        period_end = datetime(current_year + 1, birth_month, 1).date() - timedelta(days=1)

    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()

    total_hours = sum(r.hours for r in ce_records)
    ethics_hours = sum(r.hours for r in ce_records if 'ethics' in (r.category or '').lower() or 'ethics' in (r.title or '').lower())

    return {
        'designation': 'CFP',
        'total_required': 30.0,
        'total_earned': total_hours,
        'total_remaining': max(0, 30.0 - total_hours),
        'total_percentage': min(100, max(0, total_hours / 30.0 * 100)),
        'ethics_required': 2.0,
        'ethics_earned': min(ethics_hours, 2.0),
        'ethics_remaining': max(0, 2.0 - ethics_hours),
        'ethics_percentage': min(100, max(0, ethics_hours / 2.0 * 100)),
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= 30.0 and ethics_hours >= 2.0
    }


def calculate_cpa_requirements(user, user_designation):
    if not user_designation or user_designation.designation != 'CPA':
        return None

    current_year = datetime.now().year
    period_start = datetime(current_year, 1, 1).date()
    period_end = datetime(current_year, 12, 31).date()

    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()

    total_hours = sum(r.hours for r in ce_records)
    hours_required = 40.0

    return {
        'designation': 'CPA',
        'state': user_designation.state,
        'total_required': hours_required,
        'total_earned': total_hours,
        'total_remaining': max(0, hours_required - total_hours),
        'total_percentage': min(100, max(0, total_hours / hours_required * 100)),
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= hours_required
    }


def calculate_ea_requirements(user, user_designation):
    if not user_designation or user_designation.designation != 'EA':
        return None

    current_date = datetime.now().date()
    current_year = current_date.year
    cycle_start_year = (current_year // 3) * 3
    period_start = datetime(cycle_start_year, 1, 1).date()
    period_end = datetime(cycle_start_year + 2, 12, 31).date()

    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()

    current_year_start = datetime(current_year, 1, 1).date()
    current_year_end = datetime(current_year, 12, 31).date()
    current_year_records = [r for r in ce_records if current_year_start <= r.date_completed <= current_year_end]

    total_hours = sum(r.hours for r in ce_records)
    current_year_hours = sum(r.hours for r in current_year_records)
    ethics_hours = sum(r.hours for r in ce_records if 'ethics' in (r.category or '').lower() or 'ethics' in (r.title or '').lower())

    return {
        'designation': 'EA',
        'total_required': 72.0,
        'total_earned': total_hours,
        'total_remaining': max(0, 72.0 - total_hours),
        'total_percentage': min(100, max(0, total_hours / 72.0 * 100)),
        'yearly_minimum': 16.0,
        'current_year_hours': current_year_hours,
        'yearly_percentage': min(100, max(0, current_year_hours / 16.0 * 100)),
        'ethics_required': 2.0,
        'ethics_earned': min(ethics_hours, 2.0),
        'ethics_remaining': max(0, 2.0 - ethics_hours),
        'ethics_percentage': min(100, max(0, ethics_hours / 2.0 * 100)),
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= 72.0 and current_year_hours >= 16.0 and ethics_hours >= 2.0
    }


def _calculate_cepi_requirements(user, user_designation, designation_name):
    """Shared logic for CEP and ECA (both CEPI designations with same requirements)."""
    if not user_designation or user_designation.designation != designation_name:
        return None

    current_date = datetime.now().date()
    designation_date = user_designation.created_at.date() if user_designation.created_at else current_date
    years_since = (current_date - designation_date).days / 365.25
    period_number = int(years_since // 2)

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

    if period_end > current_date:
        period_end = current_date

    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()

    total_hours = sum(r.hours for r in ce_records)

    return {
        'designation': designation_name,
        'total_required': 30.0,
        'total_earned': total_hours,
        'total_remaining': max(0, 30.0 - total_hours),
        'total_percentage': min(100, max(0, total_hours / 30.0 * 100)),
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= 30.0,
        'admin_fee': 250.0,
        'volunteer_hours_required': 15.0
    }


def calculate_cep_requirements(user, user_designation):
    return _calculate_cepi_requirements(user, user_designation, 'CEP')


def calculate_eca_requirements(user, user_designation):
    return _calculate_cepi_requirements(user, user_designation, 'ECA')


def calculate_cfa_requirements(user, user_designation):
    """CFA Institute: 20 PL credits per year (calendar year)."""
    if not user_designation or user_designation.designation != 'CFA':
        return None

    current_year = datetime.now().year
    period_start = datetime(current_year, 1, 1).date()
    period_end = datetime(current_year, 12, 31).date()

    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()

    total_hours = sum(r.hours for r in ce_records)
    required = 20.0

    return {
        'designation': 'CFA',
        'total_required': required,
        'total_earned': total_hours,
        'total_remaining': max(0, required - total_hours),
        'total_percentage': min(100, max(0, total_hours / required * 100)),
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= required
    }


def calculate_clu_requirements(user, user_designation):
    """CLU (The American College): 30 hours every 2 years."""
    if not user_designation or user_designation.designation != 'CLU':
        return None

    current_year = datetime.now().year
    cycle_start = current_year - 1 if current_year % 2 == 0 else current_year
    period_start = datetime(cycle_start, 1, 1).date()
    period_end = datetime(cycle_start + 1, 12, 31).date()

    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()

    total_hours = sum(r.hours for r in ce_records)
    required = 30.0

    return {
        'designation': 'CLU',
        'total_required': required,
        'total_earned': total_hours,
        'total_remaining': max(0, required - total_hours),
        'total_percentage': min(100, max(0, total_hours / required * 100)),
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= required
    }


def calculate_chfc_requirements(user, user_designation):
    """ChFC (The American College): 30 hours every 2 years."""
    if not user_designation or user_designation.designation != 'ChFC':
        return None

    current_year = datetime.now().year
    cycle_start = current_year - 1 if current_year % 2 == 0 else current_year
    period_start = datetime(cycle_start, 1, 1).date()
    period_end = datetime(cycle_start + 1, 12, 31).date()

    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()

    total_hours = sum(r.hours for r in ce_records)
    required = 30.0

    return {
        'designation': 'ChFC',
        'total_required': required,
        'total_earned': total_hours,
        'total_remaining': max(0, required - total_hours),
        'total_percentage': min(100, max(0, total_hours / required * 100)),
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= required
    }


def _calculate_iwi_requirements(user, user_designation, designation_name, required_hours=40.0):
    """Shared logic for Investments & Wealth Institute designations (CIMA, CIMC, CPWA)."""
    if not user_designation or user_designation.designation != designation_name:
        return None

    current_year = datetime.now().year
    cycle_start = current_year - 1 if current_year % 2 == 0 else current_year
    period_start = datetime(cycle_start, 1, 1).date()
    period_end = datetime(cycle_start + 1, 12, 31).date()

    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()

    total_hours = sum(r.hours for r in ce_records)

    return {
        'designation': designation_name,
        'total_required': required_hours,
        'total_earned': total_hours,
        'total_remaining': max(0, required_hours - total_hours),
        'total_percentage': min(100, max(0, total_hours / required_hours * 100)),
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= required_hours
    }


def calculate_cima_requirements(user, ud):
    return _calculate_iwi_requirements(user, ud, 'CIMA', 40.0)


def calculate_cimc_requirements(user, ud):
    return _calculate_iwi_requirements(user, ud, 'CIMC', 40.0)


def calculate_cpwa_requirements(user, ud):
    return _calculate_iwi_requirements(user, ud, 'CPWA', 40.0)


def calculate_crps_requirements(user, user_designation):
    """CRPS: 16 hours every 2 years."""
    if not user_designation or user_designation.designation != 'CRPS':
        return None

    current_year = datetime.now().year
    cycle_start = current_year - 1 if current_year % 2 == 0 else current_year
    period_start = datetime(cycle_start, 1, 1).date()
    period_end = datetime(cycle_start + 1, 12, 31).date()

    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()

    total_hours = sum(r.hours for r in ce_records)
    required = 16.0

    return {
        'designation': 'CRPS',
        'total_required': required,
        'total_earned': total_hours,
        'total_remaining': max(0, required - total_hours),
        'total_percentage': min(100, max(0, total_hours / required * 100)),
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= required
    }


def calculate_ricp_requirements(user, user_designation):
    """RICP (The American College): 30 hours every 2 years."""
    if not user_designation or user_designation.designation != 'RICP':
        return None

    current_year = datetime.now().year
    cycle_start = current_year - 1 if current_year % 2 == 0 else current_year
    period_start = datetime(cycle_start, 1, 1).date()
    period_end = datetime(cycle_start + 1, 12, 31).date()

    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()

    total_hours = sum(r.hours for r in ce_records)
    required = 30.0

    return {
        'designation': 'RICP',
        'total_required': required,
        'total_earned': total_hours,
        'total_remaining': max(0, required - total_hours),
        'total_percentage': min(100, max(0, total_hours / required * 100)),
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= required
    }


def calculate_cdfa_requirements(user, user_designation):
    """CDFA: 15 hours per year."""
    if not user_designation or user_designation.designation != 'CDFA':
        return None

    current_year = datetime.now().year
    period_start = datetime(current_year, 1, 1).date()
    period_end = datetime(current_year, 12, 31).date()

    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()

    total_hours = sum(r.hours for r in ce_records)
    required = 15.0

    return {
        'designation': 'CDFA',
        'total_required': required,
        'total_earned': total_hours,
        'total_remaining': max(0, required - total_hours),
        'total_percentage': min(100, max(0, total_hours / required * 100)),
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= required
    }


def calculate_aif_requirements(user, user_designation):
    """AIF (Fi360): 6 hours per year."""
    if not user_designation or user_designation.designation != 'AIF':
        return None

    current_year = datetime.now().year
    period_start = datetime(current_year, 1, 1).date()
    period_end = datetime(current_year, 12, 31).date()

    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()

    total_hours = sum(r.hours for r in ce_records)
    required = 6.0

    return {
        'designation': 'AIF',
        'total_required': required,
        'total_earned': total_hours,
        'total_remaining': max(0, required - total_hours),
        'total_percentage': min(100, max(0, total_hours / required * 100)),
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= required
    }


def calculate_iar_requirements(user, user_designation):
    """IAR: 12 hours per year (including 6 ethics/products)."""
    if not user_designation or user_designation.designation != 'IAR':
        return None

    current_year = datetime.now().year
    period_start = datetime(current_year, 1, 1).date()
    period_end = datetime(current_year, 12, 31).date()

    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= period_start,
        CERecord.date_completed <= period_end
    ).all()

    total_hours = sum(r.hours for r in ce_records)
    ethics_hours = sum(r.hours for r in ce_records if 'ethics' in (r.category or '').lower() or 'ethics' in (r.title or '').lower())
    required = 12.0
    ethics_required = 6.0

    return {
        'designation': 'IAR',
        'total_required': required,
        'total_earned': total_hours,
        'total_remaining': max(0, required - total_hours),
        'total_percentage': min(100, max(0, total_hours / required * 100)),
        'ethics_required': ethics_required,
        'ethics_earned': min(ethics_hours, ethics_required),
        'ethics_remaining': max(0, ethics_required - ethics_hours),
        'ethics_percentage': min(100, max(0, ethics_hours / ethics_required * 100)),
        'period_start': period_start,
        'period_end': period_end,
        'is_complete': total_hours >= required and ethics_hours >= ethics_required
    }


# Map designation codes to their calculator functions
DESIGNATION_CALCULATORS = {
    'CFP': calculate_cfp_requirements,
    'CPA': calculate_cpa_requirements,
    'EA': calculate_ea_requirements,
    'CEP': calculate_cep_requirements,
    'ECA': calculate_eca_requirements,
    'CFA': calculate_cfa_requirements,
    'CLU': calculate_clu_requirements,
    'ChFC': calculate_chfc_requirements,
    'CIMA': calculate_cima_requirements,
    'CIMC': calculate_cimc_requirements,
    'CPWA': calculate_cpwa_requirements,
    'CRPS': calculate_crps_requirements,
    'RICP': calculate_ricp_requirements,
    'CDFA': calculate_cdfa_requirements,
    'AIF': calculate_aif_requirements,
    'IAR': calculate_iar_requirements,
}


def calculate_designation_requirements(user, user_designations):
    requirements = []
    for ud in user_designations:
        calc = DESIGNATION_CALCULATORS.get(ud.designation)
        if calc:
            req = calc(user, ud)
            if req:
                requirements.append(req)
    return requirements


def calculate_napfa_requirements(user):
    if not user.is_napfa_member or not user.napfa_join_date:
        return None

    current_year = datetime.now().year
    if current_year % 2 == 0:
        cycle_start_year = current_year
    else:
        cycle_start_year = current_year - 1
    cycle_end_year = cycle_start_year + 1

    cycle_start = datetime(cycle_start_year, 1, 1).date()
    cycle_end = datetime(cycle_end_year, 12, 31).date()
    join_date = user.napfa_join_date

    if join_date <= datetime(cycle_start_year, 6, 30).date():
        total_required = 60
        napfa_approved_required = 30
    elif join_date <= datetime(cycle_start_year, 12, 31).date():
        total_required = 45
        napfa_approved_required = 30
    elif join_date <= datetime(cycle_end_year, 6, 30).date():
        total_required = 30
        napfa_approved_required = 30
    else:
        total_required = 15
        napfa_approved_required = 15

    ce_records = CERecord.query.filter_by(user_id=user.id).filter(
        CERecord.date_completed >= cycle_start,
        CERecord.date_completed <= cycle_end
    ).all()

    total_hours = sum(r.hours for r in ce_records)
    napfa_approved_hours = sum(r.hours for r in ce_records if r.is_napfa_approved)
    ethics_completed = any(r.is_ethics_course for r in ce_records)

    return {
        'total_required': total_required,
        'total_earned': total_hours,
        'total_remaining': max(0, total_required - total_hours),
        'total_percentage': min(100, max(0, total_hours / total_required * 100 if total_required else 0)),
        'napfa_approved_required': napfa_approved_required,
        'napfa_approved_earned': napfa_approved_hours,
        'napfa_approved_remaining': max(0, napfa_approved_required - napfa_approved_hours),
        'napfa_approved_percentage': min(100, max(0, napfa_approved_hours / napfa_approved_required * 100 if napfa_approved_required else 0)),
        'ethics_required': True,
        'ethics_completed': ethics_completed,
        'cycle_start': cycle_start,
        'cycle_end': cycle_end,
        'is_complete': total_hours >= total_required and napfa_approved_hours >= napfa_approved_required and ethics_completed
    }


# Designation tooltip descriptions (shared across register and manage pages)
DESIGNATION_REQUIREMENTS = {
    'CFP': 'CFP® professionals must complete 30 hours of continuing education (CE) every two years, which includes 2 hours of CFP Board-approved Ethics CE and 28 hours in one or more of the CFP Board\'s Principal Topics.',
    'CFA': 'CFA charterholders must complete 20 professional learning (PL) credits per calendar year through the CFA Institute.',
    'CPA': 'CPAs must complete continuing professional education (CPE) requirements that vary by state. Most states require 40 hours of CPE per year.',
    'CLE': 'Continuing Legal Education (CLE) requirements vary by state and jurisdiction. Most states require attorneys to complete a certain number of CLE hours annually or biennially.',
    'CLU': 'CLU professionals must complete 30 hours of continuing education every 2 years as specified by The American College.',
    'EA': 'Enrolled Agents (EAs) must complete 72 hours of continuing education (CE) every three years, with a minimum of 16 hours per year. At least 2 hours must be on ethics.',
    'ChFC': 'ChFC® professionals must complete 30 hours of continuing education every 2 years as specified by The American College.',
    'CIMA': 'CIMA® professionals must complete 40 hours of continuing education every 2 years as specified by the Investments & Wealth Institute.',
    'CIMC': 'CIMC® professionals must complete 40 hours of continuing education every 2 years as specified by the Investments & Wealth Institute.',
    'CPWA': 'CPWA® professionals must complete 40 hours of continuing education every 2 years as specified by the Investments & Wealth Institute.',
    'CRPS': 'CRPS® professionals must complete 16 hours of continuing education every 2 years as specified by The College for Financial Planning.',
    'RICP': 'RICP® professionals must complete 30 hours of continuing education every 2 years as specified by The American College.',
    'CDFA': 'CDFA® professionals must complete 15 hours of continuing education per year as specified by the Institute for Divorce Financial Analysts.',
    'AIF': 'AIF® professionals must complete 6 hours of continuing education per year as specified by Fi360.',
    'IAR': 'Investment Adviser Representatives (IARs) must complete 12 hours of continuing education per year, including 6 hours of ethics/products knowledge.',
    'CEP': 'Certified Equity Professional (CEP) requires 30 hours of continuing education every two years. $250 administrative fee (waived after 15 hours of volunteer work).',
    'ECA': 'Equity Compensation Associate (ECA) requires 30 hours of continuing education every two years. $250 administrative fee (waived after 15 hours of volunteer work).'
}

ALLOWED_DESIGNATIONS = ['CFP', 'CFA', 'CPA', 'CLE', 'CLU', 'EA', 'ChFC', 'CIMA', 'CIMC', 'CPWA', 'CRPS', 'RICP', 'CDFA', 'AIF', 'IAR', 'CEP', 'ECA']
