# SMS Reminder Application

A simple and efficient SMS reminder system built with Flask and AWS SNS.

## Features

- Create SMS reminders with custom messages
- Schedule reminders for specific times
- View all scheduled reminders
- Automatic SMS sending using AWS SNS
- RESTful API endpoints

## Prerequisites

- Python 3.8+
- AWS Account with SNS access
- SQLite (default) or any SQL database

## Setup Instructions

1. Clone the repository
2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
   - Copy `.env.example` to `.env`
   - Update the variables in `.env` with your credentials:
```
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///reminders.db
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_REGION=your-aws-region
```

5. Initialize the database:
```bash
flask db init
flask db migrate
flask db upgrade
```

6. Run the application:
```bash
python app.py
```

## API Endpoints

### Create a Reminder
- **POST** `/api/reminders`
```json
{
    "phone_number": "+1234567890",
    "message": "Your reminder message",
    "scheduled_time": "2025-02-02T10:00:00"
}
```

### Get All Reminders
- **GET** `/api/reminders`

## Environment Variables

- `SECRET_KEY`: Flask secret key
- `DATABASE_URL`: Database connection URL
- `AWS_ACCESS_KEY_ID`: AWS access key
- `AWS_SECRET_ACCESS_KEY`: AWS secret key
- `AWS_REGION`: AWS region (default: us-east-1)
