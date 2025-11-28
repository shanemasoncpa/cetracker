# CE Tracker

A free web application for tracking Continuing Education (CE) credentials. Users can register, log in, and manage their CE records with an intuitive interface.

## Features

- **User Authentication**: Secure registration and login system
- **CE Management**: Add, view, and delete CE records
- **Dashboard**: View all CE records in a clean table format
- **Statistics**: Track total CE hours and number of records
- **Easy Entry**: Dropdown form for quick CE hour selection
- **Modern UI**: Responsive design that works on all devices

## Installation

1. **Install Python** (3.8 or higher recommended)

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:
   ```bash
   python app.py
   ```

4. **Access the application**:
   Open your browser and navigate to `http://localhost:5000`

## Usage

1. **Register**: Create a new account with a username, email, and password
2. **Login**: Sign in with your credentials
3. **Add CE**: Click "Add CE" to enter new continuing education records
4. **View Records**: See all your CE records in the dashboard table
5. **Track Progress**: Monitor your total CE hours at a glance

## Database

The application uses SQLite, which creates a `ce_tracker.db` file automatically on first run. This database stores:
- User accounts and authentication data
- CE records with details (title, provider, hours, date, category, description)

## Project Structure

```
cpetracker/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── templates/            # HTML templates
│   ├── base.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   └── add_ce.html
├── static/               # Static files
│   └── style.css
└── ce_tracker.db        # SQLite database (created automatically)
```

## Security Notes

- Passwords are hashed using Werkzeug's security functions
- Session-based authentication
- User data is isolated (users can only see their own CE records)

## Future Enhancements

Potential features for future development:
- Export CE records to PDF/CSV
- CE renewal period tracking
- Email reminders for CE requirements
- Category-based filtering and reporting
- Certificate upload functionality

