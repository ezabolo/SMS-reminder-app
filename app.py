from flask import Flask, request, jsonify, send_file, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from dateutil import tz

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configure SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///reminders.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)

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

# Authentication middleware
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
        admin = Admin.query.filter_by(username=data['username']).first()
        
        if admin and admin.check_password(data['password']):
            session['admin_id'] = admin.id
            return jsonify({
                'status': 'success',
                'message': 'Logged in successfully'
            })
        return jsonify({'error': 'Invalid credentials'}), 401
    except Exception as e:
        return jsonify({'error': str(e)}), 400

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
        if not all(key in data for key in ['patient_id', 'message', 'scheduled_time']):
            return jsonify({
                'error': 'Missing required fields',
                'required_fields': ['patient_id', 'message', 'scheduled_time']
            }), 400

        # Validate patient exists
        patient = Patient.query.get(data['patient_id'])
        if not patient:
            return jsonify({
                'error': 'Patient not found'
            }), 404

        # Validate scheduled time
        try:
            # Handle various datetime formats
            scheduled_time_str = data['scheduled_time']
            # Remove any trailing 'Z' and replace with +00:00 for UTC
            if scheduled_time_str.endswith('Z'):
                scheduled_time_str = scheduled_time_str[:-1] + '+00:00'
            # If no timezone info, assume UTC
            elif not any(x in scheduled_time_str for x in ['+', '-', 'Z']):
                scheduled_time_str += '+00:00'
            
            scheduled_time = datetime.fromisoformat(scheduled_time_str)
            
            # Convert to UTC if it's not
            if scheduled_time.tzinfo is not None:
                scheduled_time = scheduled_time.astimezone(tz.tzutc())
            
            # Remove timezone info for database storage
            scheduled_time = scheduled_time.replace(tzinfo=None)
            
            if scheduled_time < datetime.utcnow():
                return jsonify({
                    'error': 'Scheduled time must be in the future'
                }), 400
                
        except Exception as e:
            return jsonify({
                'error': f'Invalid datetime format. Please use format: YYYY-MM-DDTHH:MM:SS (e.g., 2025-02-02T15:30:00)'
            }), 400

        reminder = Reminder(
            patient_id=data['patient_id'],
            message=data['message'],
            scheduled_time=scheduled_time
        )
        db.session.add(reminder)
        db.session.commit()

        return jsonify({
            'status': 'success',
            'message': 'Reminder created successfully',
            'reminder': {
                'id': reminder.id,
                'patient_id': reminder.patient_id,
                'message': reminder.message,
                'scheduled_time': reminder.scheduled_time.isoformat(),
                'status': reminder.status,
                'created_at': reminder.created_at.isoformat()
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/reminders', methods=['GET'])
@admin_required
def get_reminders():
    try:
        reminders = Reminder.query.join(Patient).order_by(Reminder.scheduled_time.desc()).all()
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

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Create admin account if it doesn't exist
def create_admin():
    with app.app_context():
        if not Admin.query.filter_by(username='admin').first():
            admin = Admin(username='admin')
            admin.set_password('admin123')  # Default password
            db.session.add(admin)
            db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_admin()
    app.run(debug=True)
