import pytest
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, User, CERecord, UserDesignation, Feedback


@pytest.fixture(scope='function')
def test_app():
    """Create a test application instance."""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SECRET_KEY'] = 'test-secret-key'

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(test_app):
    """Create a test client."""
    return test_app.test_client()


@pytest.fixture
def runner(test_app):
    """Create a CLI test runner."""
    return test_app.test_cli_runner()


@pytest.fixture
def sample_user(test_app):
    """Create a sample user for testing."""
    from werkzeug.security import generate_password_hash

    with test_app.app_context():
        user = User(
            username='testuser',
            email='test@example.com',
            password_hash=generate_password_hash('password123'),
            is_napfa_member=False
        )
        db.session.add(user)
        db.session.commit()

        return {'id': user.id, 'username': 'testuser', 'email': 'test@example.com', 'password': 'password123'}


@pytest.fixture
def logged_in_client(client, sample_user):
    """Return a client that is already logged in."""
    client.post('/login', data={
        'username': sample_user['username'],
        'password': sample_user['password']
    })
    return client
