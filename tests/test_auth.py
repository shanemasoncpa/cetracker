"""Tests for authentication flows: register, login, logout, password reset."""


def test_register_page_loads(client):
    response = client.get('/register')
    assert response.status_code == 200
    assert b'Register' in response.data


def test_register_success(client):
    response = client.post('/register', data={
        'username': 'newuser',
        'email': 'new@example.com',
        'password': 'password123',
        'confirm_password': 'password123',
        'disclaimer_ack': 'on',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Registration successful' in response.data


def test_register_duplicate_username(client, sample_user):
    response = client.post('/register', data={
        'username': 'testuser',
        'email': 'different@example.com',
        'password': 'password123',
        'confirm_password': 'password123',
        'disclaimer_ack': 'on',
    }, follow_redirects=True)
    assert b'Username already exists' in response.data


def test_register_duplicate_email(client, sample_user):
    response = client.post('/register', data={
        'username': 'differentuser',
        'email': 'test@example.com',
        'password': 'password123',
        'confirm_password': 'password123',
        'disclaimer_ack': 'on',
    }, follow_redirects=True)
    assert b'Email already exists' in response.data


def test_register_without_disclaimer_ack(client):
    response = client.post('/register', data={
        'username': 'newuser',
        'email': 'new@example.com',
        'password': 'password123',
        'confirm_password': 'password123',
    }, follow_redirects=True)
    assert b'You must acknowledge the disclaimer to register' in response.data


def test_register_password_mismatch(client):
    response = client.post('/register', data={
        'username': 'newuser',
        'email': 'new@example.com',
        'password': 'password123',
        'confirm_password': 'different',
    }, follow_redirects=True)
    assert b'Passwords do not match' in response.data


def test_register_password_too_short(client):
    response = client.post('/register', data={
        'username': 'newuser',
        'email': 'new@example.com',
        'password': '123',
        'confirm_password': '123',
    }, follow_redirects=True)
    assert b'at least 6 characters' in response.data


def test_register_missing_fields(client):
    response = client.post('/register', data={
        'username': '',
        'email': '',
        'password': '',
        'confirm_password': '',
    }, follow_redirects=True)
    assert b'required' in response.data.lower()


def test_register_with_cfp_requires_birth_month(client):
    response = client.post('/register', data={
        'username': 'cfpuser',
        'email': 'cfp@example.com',
        'password': 'password123',
        'confirm_password': 'password123',
        'designations': ['CFP'],
    }, follow_redirects=True)
    assert b'Birth month is required' in response.data


def test_register_with_cpa_requires_state(client):
    response = client.post('/register', data={
        'username': 'cpauser',
        'email': 'cpa@example.com',
        'password': 'password123',
        'confirm_password': 'password123',
        'designations': ['CPA'],
    }, follow_redirects=True)
    assert b'State is required' in response.data


def test_login_page_loads(client):
    response = client.get('/login')
    assert response.status_code == 200
    assert b'Login' in response.data or b'login' in response.data


def test_login_success(client, sample_user):
    response = client.post('/login', data={
        'username': sample_user['username'],
        'password': sample_user['password'],
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Login successful' in response.data


def test_login_wrong_password(client, sample_user):
    response = client.post('/login', data={
        'username': sample_user['username'],
        'password': 'wrongpassword',
    }, follow_redirects=True)
    assert b'Invalid password' in response.data


def test_login_nonexistent_user(client):
    response = client.post('/login', data={
        'username': 'nobody',
        'password': 'password123',
    }, follow_redirects=True)
    assert b'User not found' in response.data


def test_login_empty_fields(client):
    response = client.post('/login', data={
        'username': '',
        'password': '',
    }, follow_redirects=True)
    assert b'Please enter both' in response.data


def test_logout(logged_in_client):
    response = logged_in_client.get('/logout', follow_redirects=True)
    assert response.status_code == 200
    assert b'logged out' in response.data.lower()


def test_dashboard_requires_login(client):
    response = client.get('/dashboard', follow_redirects=True)
    assert b'log in' in response.data.lower()


def test_profile_requires_login(client):
    response = client.get('/profile', follow_redirects=True)
    assert b'log in' in response.data.lower()


def test_forgot_password_page_loads(client):
    response = client.get('/forgot_password')
    assert response.status_code == 200


def test_forgot_password_generates_token(client, sample_user, test_app):
    response = client.post('/forgot_password', data={
        'email': sample_user['email'],
    }, follow_redirects=False)
    # Should redirect to the reset page with token
    assert response.status_code == 302

    from models import User as UserModel
    with test_app.app_context():
        user = UserModel.query.filter_by(email=sample_user['email']).first()
        assert user.reset_token is not None


def test_forgot_password_nonexistent_email(client):
    response = client.post('/forgot_password', data={
        'email': 'nobody@example.com',
    }, follow_redirects=True)
    # Should not reveal that the email doesn't exist
    assert b'If an account with that email exists' in response.data


def test_reset_password_with_valid_token(client, sample_user, test_app):
    # Generate token first
    client.post('/forgot_password', data={'email': sample_user['email']})

    from models import User as UserModel
    with test_app.app_context():
        user = UserModel.query.filter_by(email=sample_user['email']).first()
        token = user.reset_token

    # Reset password
    response = client.post(f'/reset_password/{token}', data={
        'new_password': 'newpassword123',
        'confirm_password': 'newpassword123',
    }, follow_redirects=True)
    assert b'password has been reset' in response.data.lower()

    # Login with new password
    response = client.post('/login', data={
        'username': sample_user['username'],
        'password': 'newpassword123',
    }, follow_redirects=True)
    assert b'Login successful' in response.data


def test_reset_password_invalid_token(client):
    response = client.get('/reset_password/invalidtoken', follow_redirects=True)
    assert b'invalid or has expired' in response.data.lower()
