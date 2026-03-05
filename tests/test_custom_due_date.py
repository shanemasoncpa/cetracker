"""Tests for user-settable CE due dates (custom_period_end)."""
import pytest
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from models import db, UserDesignation, CERecord


class TestApplyCustomPeriod:
    """Test the _apply_custom_period helper function."""

    def test_returns_auto_dates_when_no_override(self, test_app):
        from designation_helpers import _apply_custom_period
        with test_app.app_context():
            ud = UserDesignation(user_id=1, designation='CFP')
            ud.custom_period_end = None
            auto_start = date(2025, 3, 1)
            auto_end = date(2027, 2, 28)
            start, end = _apply_custom_period(ud, auto_start, auto_end)
            assert start == auto_start
            assert end == auto_end

    def test_overrides_for_2yr_cycle(self, test_app):
        from designation_helpers import _apply_custom_period
        with test_app.app_context():
            ud = UserDesignation(user_id=1, designation='CFP')
            ud.custom_period_end = date(2027, 3, 31)
            start, end = _apply_custom_period(ud, date(2025, 1, 1), date(2026, 12, 31))
            assert end == date(2027, 3, 31)
            assert start == date(2025, 4, 1)

    def test_overrides_for_1yr_cycle(self, test_app):
        from designation_helpers import _apply_custom_period
        with test_app.app_context():
            ud = UserDesignation(user_id=1, designation='CPA')
            ud.custom_period_end = date(2026, 6, 30)
            start, end = _apply_custom_period(ud, date(2026, 1, 1), date(2026, 12, 31))
            assert end == date(2026, 6, 30)
            assert start == date(2025, 7, 1)

    def test_overrides_for_3yr_cycle(self, test_app):
        from designation_helpers import _apply_custom_period
        with test_app.app_context():
            ud = UserDesignation(user_id=1, designation='EA')
            ud.custom_period_end = date(2027, 12, 31)
            start, end = _apply_custom_period(ud, date(2025, 1, 1), date(2027, 12, 31))
            assert end == date(2027, 12, 31)
            assert start == date(2025, 1, 1)


class TestCFPCalculatorWithCustomDate:
    """Integration test: CFP calculator uses custom date when set."""

    def test_cfp_uses_custom_period(self, test_app, sample_user):
        from designation_helpers import calculate_cfp_requirements
        with test_app.app_context():
            user_id = sample_user['id']
            from models import User
            user = db.session.get(User, user_id)

            ud = UserDesignation(user_id=user_id, designation='CFP', birth_month=3)
            ud.custom_period_end = date(2027, 3, 31)
            db.session.add(ud)

            # Add a CE record within the custom period
            rec = CERecord(
                user_id=user_id, title='Test CE', hours=10.0,
                date_completed=date(2026, 6, 15), category='General'
            )
            db.session.add(rec)
            db.session.commit()

            result = calculate_cfp_requirements(user, ud)
            assert result is not None
            assert result['period_end'] == date(2027, 3, 31)
            assert result['total_earned'] == 10.0

    def test_cfp_custom_period_filters_records(self, test_app, sample_user):
        from designation_helpers import calculate_cfp_requirements
        with test_app.app_context():
            user_id = sample_user['id']
            from models import User
            user = db.session.get(User, user_id)

            ud = UserDesignation(user_id=user_id, designation='CFP', birth_month=3)
            ud.custom_period_end = date(2027, 3, 31)
            db.session.add(ud)

            # Record outside custom period (before start)
            outside = CERecord(
                user_id=user_id, title='Old CE', hours=5.0,
                date_completed=date(2024, 1, 15), category='General'
            )
            # Record inside custom period
            inside = CERecord(
                user_id=user_id, title='New CE', hours=8.0,
                date_completed=date(2026, 6, 15), category='General'
            )
            db.session.add_all([outside, inside])
            db.session.commit()

            result = calculate_cfp_requirements(user, ud)
            assert result['total_earned'] == 8.0


class TestSetDueDateRoute:
    """Test the set_due_date POST action."""

    def test_set_due_date(self, logged_in_client, test_app, sample_user):
        with test_app.app_context():
            ud = UserDesignation(user_id=sample_user['id'], designation='CFP', birth_month=6)
            db.session.add(ud)
            db.session.commit()
            ud_id = ud.id

        resp = logged_in_client.post('/manage_designations', data={
            'action': 'set_due_date',
            'designation_id': ud_id,
            'custom_period_end': '2027-03-31',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b'Due date for CFP set to' in resp.data

        with test_app.app_context():
            ud = db.session.get(UserDesignation, ud_id)
            assert ud.custom_period_end == date(2027, 3, 31)

    def test_clear_due_date(self, logged_in_client, test_app, sample_user):
        with test_app.app_context():
            ud = UserDesignation(
                user_id=sample_user['id'], designation='CPA', state='NY',
                custom_period_end=date(2027, 6, 30)
            )
            db.session.add(ud)
            db.session.commit()
            ud_id = ud.id

        resp = logged_in_client.post('/manage_designations', data={
            'action': 'set_due_date',
            'designation_id': ud_id,
            'custom_period_end': '',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b'reset to auto-calculated' in resp.data

        with test_app.app_context():
            ud = db.session.get(UserDesignation, ud_id)
            assert ud.custom_period_end is None

    def test_set_due_date_wrong_user(self, logged_in_client, test_app, sample_user):
        """Cannot set due date for another user's designation."""
        from werkzeug.security import generate_password_hash
        with test_app.app_context():
            from models import User
            other = User(username='other', email='other@test.com',
                         password_hash=generate_password_hash('pass'))
            db.session.add(other)
            db.session.commit()
            ud = UserDesignation(user_id=other.id, designation='AIF')
            db.session.add(ud)
            db.session.commit()
            ud_id = ud.id

        resp = logged_in_client.post('/manage_designations', data={
            'action': 'set_due_date',
            'designation_id': ud_id,
            'custom_period_end': '2027-12-31',
        }, follow_redirects=True)
        assert b'permission' in resp.data.lower()


class TestDashboardCustomBadge:
    """Test that the dashboard shows '(custom)' badge."""

    def test_custom_badge_shown(self, logged_in_client, test_app, sample_user):
        with test_app.app_context():
            ud = UserDesignation(
                user_id=sample_user['id'], designation='CFA',
                custom_period_end=date(2027, 6, 30)
            )
            db.session.add(ud)
            db.session.commit()

        resp = logged_in_client.get('/dashboard')
        assert resp.status_code == 200
        assert b'(custom)' in resp.data

    def test_custom_badge_not_shown_auto(self, logged_in_client, test_app, sample_user):
        with test_app.app_context():
            ud = UserDesignation(user_id=sample_user['id'], designation='CFA')
            db.session.add(ud)
            db.session.commit()

        resp = logged_in_client.get('/dashboard')
        assert resp.status_code == 200
        assert b'(custom)' not in resp.data


class TestBackupExport:
    """Test that backup includes custom_period_end."""

    def test_backup_includes_custom_period_end(self, logged_in_client, test_app, sample_user):
        import json
        with test_app.app_context():
            ud = UserDesignation(
                user_id=sample_user['id'], designation='CFP', birth_month=3,
                custom_period_end=date(2027, 3, 31)
            )
            db.session.add(ud)
            db.session.commit()

        resp = logged_in_client.get('/export_backup')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['designations'][0]['custom_period_end'] == '2027-03-31'

    def test_backup_null_custom_period_end(self, logged_in_client, test_app, sample_user):
        import json
        with test_app.app_context():
            ud = UserDesignation(
                user_id=sample_user['id'], designation='CFA',
            )
            db.session.add(ud)
            db.session.commit()

        resp = logged_in_client.get('/export_backup')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['designations'][0]['custom_period_end'] is None
