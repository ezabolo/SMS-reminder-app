from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from datetime import datetime
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
import os
from utils.sms_handler import SMSHandler
from werkzeug.security import generate_password_hash, check_password_hash
from dateutil import tz

# Load environment variables
load_dotenv()

# Initialize SMS Handler
sms_handler = SMSHandler()

# Initialize Flask app
app = Flask(__name__, static_url_path='/static', static_folder='static')
CORS(app)

# Configure SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///reminders.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Admin credentials
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'Kdf$325Mfs&7r&d!'

# Models
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reminders = db.relationship('Reminder', backref='patient', lazy=True)

class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    message = db.Column(db.String(160), nullable=False)
    scheduled_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Admin authentication decorator
def admin_required(f):
    def wrapper(*args, **kwargs):
        if 'admin_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# Routes
@app.route('/')
def index():
    if 'admin_id' not in session:
        return send_file('templates/login.html')
    return send_file('templates/index.html')

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            admin = Admin.query.filter_by(username=username).first()
            if not admin:
                admin = Admin(username=username)
                admin.set_password(password)
                db.session.add(admin)
                db.session.commit()
            session['admin_id'] = admin.id
            return jsonify({'status': 'success'})

        return jsonify({'error': 'Invalid credentials'}), 401
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('admin_id', None)
    return jsonify({'status': 'success', 'message': 'Logged out successfully'})

@app.route('/api/patients', methods=['GET'])
@admin_required
def get_patients():
    try:
        patients = Patient.query.order_by(Patient.name).all()
        return jsonify({
            'status': 'success',
            'patients': [{
                'id': p.id,
                'name': p.name,
                'phone_number': p.phone_number,
                'email': p.email,
                'created_at': p.created_at.isoformat()
            } for p in patients]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/patients', methods=['POST'])
@admin_required
def create_patient():
    try:
        data = request.json
        if not all(key in data for key in ['name', 'phone_number']):
            return jsonify({
                'error': 'Missing required fields',
                'required_fields': ['name', 'phone_number']
            }), 400

        patient = Patient(
            name=data['name'],
            phone_number=data['phone_number'],
            email=data.get('email')
        )
        db.session.add(patient)
        db.session.commit()

        return jsonify({
            'status': 'success',
            'message': 'Patient created successfully',
            'patient': {
                'id': patient.id,
                'name': patient.name,
                'phone_number': patient.phone_number,
                'email': patient.email,
                'created_at': patient.created_at.isoformat()
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/patients/<int:patient_id>', methods=['DELETE'])
@admin_required
def delete_patient(patient_id):
    try:
        patient = Patient.query.get_or_404(patient_id)
        db.session.delete(patient)
        db.session.commit()
        return jsonify({
            'status': 'success',
            'message': f'Patient {patient_id} deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/reminders', methods=['POST'])
@admin_required
def create_reminder():
    try:
        data = request.json
        patient_id = data.get('patient_id')
        message = data.get('message')
        scheduled_time = data.get('scheduled_time')

        if not all([patient_id, message, scheduled_time]):
            return jsonify({'error': 'Missing required fields'}), 400

        # Get patient details
        patient = Patient.query.get(patient_id)
        if not patient:
            return jsonify({'error': 'Patient not found'}), 404

        # Create reminder
        reminder = Reminder(
            patient_id=patient_id,
            message=message,
            scheduled_time=datetime.fromisoformat(scheduled_time.replace('Z', '+00:00'))
        )
        db.session.add(reminder)
        db.session.commit()

        # Send SMS notification
        formatted_message = sms_handler.format_appointment_message(
            patient.name,
            scheduled_time,
            message
        )
        sms_result = sms_handler.send_sms(patient.phone_number, formatted_message)

        if not sms_result['success']:
            # Log the error but don't prevent reminder creation
            print(f"SMS sending failed: {sms_result['error']}")

        return jsonify({
            'status': 'success',
            'reminder': {
                'id': reminder.id,
                'patient_id': reminder.patient_id,
                'message': reminder.message,
                'scheduled_time': reminder.scheduled_time.isoformat(),
                'status': reminder.status,
                'sms_status': 'sent' if sms_result.get('success', False) else 'failed'
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reminders', methods=['GET'])
@admin_required
def get_reminders():
    try:
        # Get date filter from query parameters
        filter_date = request.args.get('date')
        
        # Base query joining with Patient
        query = Reminder.query.join(Patient)
        
        # Apply date filter if provided
        if filter_date:
            try:
                # Parse the date string
                filter_date = datetime.strptime(filter_date, '%Y-%m-%d')
                # Get start and end of the day in UTC
                start_of_day = filter_date.replace(hour=0, minute=0, second=0, microsecond=0)
                end_of_day = filter_date.replace(hour=23, minute=59, second=59, microsecond=999999)
                # Filter reminders for the specified date
                query = query.filter(
                    Reminder.scheduled_time >= start_of_day,
                    Reminder.scheduled_time <= end_of_day
                )
            except ValueError:
                return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        # Order by scheduled time
        reminders = query.order_by(Reminder.scheduled_time.asc()).all()
        
        return jsonify({
            'status': 'success',
            'count': len(reminders),
            'reminders': [{
                'id': r.id,
                'patient': {
                    'id': r.patient.id,
                    'name': r.patient.name,
                    'phone_number': r.patient.phone_number
                },
                'message': r.message,
                'scheduled_time': r.scheduled_time.isoformat(),
                'status': r.status,
                'created_at': r.created_at.isoformat()
            } for r in reminders]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reminders/<int:reminder_id>', methods=['DELETE'])
@admin_required
def delete_reminder(reminder_id):
    try:
        reminder = Reminder.query.get_or_404(reminder_id)
        db.session.delete(reminder)
        db.session.commit()
        return jsonify({
            'status': 'success',
            'message': f'Reminder {reminder_id} deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Test SMS endpoint
@app.route('/api/test-sms', methods=['POST'])
@admin_required
def test_sms():
    try:
        data = request.json
        phone_number = data.get('phone_number')
        
        if not phone_number:
            return jsonify({'error': 'Phone number is required'}), 400

        test_message = "This is a test message from Artistic Family Dentistry's Appointment Reminder System."
        result = sms_handler.send_sms(phone_number, test_message)

        if result['success']:
            return jsonify({
                'status': 'success',
                'message': 'Test SMS sent successfully',
                'message_id': result['message_id']
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f"Failed to send SMS: {result['error']}"
            }), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Create admin account if it doesn't exist
def create_admin():
    with app.app_context():
        if not Admin.query.filter_by(username=ADMIN_USERNAME).first():
            admin = Admin(username=ADMIN_USERNAME)
            admin.set_password(ADMIN_PASSWORD)  
            db.session.add(admin)
            db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_admin()
    app.run(debug=True)
