from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, make_response, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, time, date, timedelta
from werkzeug.utils import secure_filename
import os
from functools import wraps
from sqlalchemy import or_, and_
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import base64
from io import BytesIO
from PIL import Image




app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bus_schedule.db'
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'static/profile_pics'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER_LICENSE'] = 'static/uploads/licenses'
db = SQLAlchemy(app)

# Initialize LoginManager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User loader function
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER_LICENSE'], exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

@app.context_processor
def inject_user():
    return dict(current_user=current_user)

@app.context_processor
def inject_notifications():
    unread_count = 0
    if current_user.is_authenticated:
        unread_count = Notification.query.filter_by(
            recipient_username=current_user.username,
            is_read=False
        ).count()
    return dict(unread_count=unread_count)

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin or driver
    full_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text)
    join_date = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    profile_pic = db.Column(db.String(255))
    emergency_contact = db.Column(db.String(200))
    license_number = db.Column(db.String(100))
    license_expiry = db.Column(db.Date)

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    route = db.Column(db.String(100), nullable=False)
    bus_number = db.Column(db.String(20), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    assigned_driver = db.Column(db.String(150), db.ForeignKey('user.username'))
    is_peak_hour = db.Column(db.Boolean, default=False)
    schedule_type = db.Column(db.String(20), default='regular')
    created_by = db.Column(db.String(150), db.ForeignKey('user.username'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_modified = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')  # pending, assigned, acknowledged, completed
    driver_acknowledged = db.Column(db.Boolean, default=False)
    acknowledgment_time = db.Column(db.DateTime)

class LeaveRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    driver_username = db.Column(db.String(150), nullable=False)
    date = db.Column(db.String(50), nullable=False)
    start_time = db.Column(db.String(50), nullable=False)
    end_time = db.Column(db.String(50), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    admin_response = db.Column(db.Text)
    response_time = db.Column(db.DateTime)

class DriverLicense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    driver_username = db.Column(db.String(150), db.ForeignKey('user.username'), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    expiry_date = db.Column(db.Date)
    license_number = db.Column(db.String(50))
    license_type = db.Column(db.String(50))  # e.g., Class A, Class B, etc.
    driver = db.relationship('User', backref=db.backref('license', uselist=False))

    def __repr__(self):
        return f'<DriverLicense {self.driver_username}>'

class ShiftSwap(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    requesting_driver = db.Column(db.String(150), db.ForeignKey('user.username'), nullable=False)
    target_driver = db.Column(db.String(150), db.ForeignKey('user.username'), nullable=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    admin_response = db.Column(db.Text)
    response_time = db.Column(db.DateTime)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    driver_username = db.Column(db.String(150), db.ForeignKey('user.username'))
    date = db.Column(db.Date, nullable=False)
    check_in_time = db.Column(db.DateTime)
    check_out_time = db.Column(db.DateTime)
    check_in_photo = db.Column(db.Text)  # Store base64 encoded image
    check_out_photo = db.Column(db.Text)  # Store base64 encoded image
    status = db.Column(db.String(20), default='present')  # present, absent, late
    total_hours = db.Column(db.Float)

class BreakPeriod(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    driver_username = db.Column(db.String(150), db.ForeignKey('user.username'), nullable=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=True)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    break_type = db.Column(db.String(50), nullable=False)  # rest, lunch, emergency
    status = db.Column(db.String(20), default='scheduled')  # scheduled, ongoing, completed

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipient_username = db.Column(db.String(150), db.ForeignKey('user.username'))
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50))  # schedule, attendance, leave, etc.
    priority = db.Column(db.String(20), default='normal')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime)
    is_read = db.Column(db.Boolean, default=False)

class PerformanceMetric(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    driver_username = db.Column(db.String(150), db.ForeignKey('user.username'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    on_time_arrival_percentage = db.Column(db.Float)
    break_compliance_percentage = db.Column(db.Float)
    total_hours_worked = db.Column(db.Float)
    incidents_reported = db.Column(db.Integer, default=0)
    passenger_feedback_rating = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class BusAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    driver_name = db.Column(db.String(150), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(50), nullable=False)
    end_time = db.Column(db.String(50), nullable=False)
    bus_number = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='scheduled')  # scheduled, in_progress, completed, cancelled

# Create DB Tables
with app.app_context():
    # Only create tables if they don't exist
    db.create_all()
    
    # Check if admin exists
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            password=generate_password_hash('admin123'),
            role='admin',
            full_name='System Administrator',
            email='admin@busschedule.com',
            phone='1234567890',
            address='Admin Office',
            emergency_contact='911'
        )
        db.session.add(admin)
    
    # Initialize test drivers only if they don't exist
    test_drivers = [
        {
            'username': 'driver1',
            'password': 'driver123',
            'name': 'Sarvesh',
            'license_number': 'DL123456',
            'phone': '1234567890',
            'email': 'sarvesh@example.com',
            'role': 'driver'
        },
        {
            'username': 'driver2',
            'password': 'driver123',
            'name': 'Karthick',
            'license_number': 'DL789012',
            'phone': '9876543210',
            'email': 'karthick@example.com',
            'role': 'driver'
        },
        {
            'username': 'driver3',
            'password': 'driver123',
            'name': 'Saravanan',
            'license_number': 'DL345678',
            'phone': '4567890123',
            'email': 'saravanan@example.com',
            'role': 'driver'
        },
        {
            'username': 'driver4',
            'password': 'driver123',
            'name': 'Ram',
            'license_number': 'DL901234',
            'phone': '7890123456',
            'email': 'ram@example.com',
            'role': 'driver'
        },
        {
            'username': 'driver5',
            'password': 'driver123',
            'name': 'Arun',
            'license_number': 'DL567890',
            'phone': '2345678901',
            'email': 'arun@example.com',
            'role': 'driver'
        },
        {
            'username': 'driver6',
            'password': 'driver123',
            'name': 'Sankar',
            'license_number': 'DL123789',
            'phone': '8901234567',
            'email': 'sankar@example.com',
            'role': 'driver'
        },
        {
            'username': 'driver7',
            'password': 'driver123',
            'name': 'Santhosh',
            'license_number': 'DL456123',
            'phone': '3456789012',
            'email': 'santhosh@example.com',
            'role': 'driver'
        },
        {
            'username': 'driver8',
            'password': 'driver123',
            'name': 'Rajkumar',
            'license_number': 'DL789456',
            'phone': '6789012345',
            'email': 'rajkumar@example.com',
            'role': 'driver'
        },
        {
            'username': 'driver9',
            'password': 'driver123',
            'name': 'Praveen',
            'license_number': 'DL234567',
            'phone': '9012345678',
            'email': 'praveen@example.com',
            'role': 'driver'
        },
        {
            'username': 'driver10',
            'password': 'driver123',
            'name': 'Kishore',
            'license_number': 'DL890123',
            'phone': '5678901234',
            'email': 'kishore@example.com',
            'role': 'driver'
        },
        {
            'username': 'driver11',
            'password': 'driver123',
            'name': 'Shiva',
            'license_number': 'DL456789',
            'phone': '2345678901',
            'email': 'shiva@example.com',
            'role': 'driver'
        }
    ]
    
    for driver_data in test_drivers:
        driver = User.query.filter_by(username=driver_data['username']).first()
        if not driver:
            driver = User(
                username=driver_data['username'],
                password=generate_password_hash(driver_data['password']),
                role=driver_data['role'],
                full_name=driver_data['name'],
                email=driver_data['email'],
                phone=driver_data['phone'],
                license_number=driver_data['license_number']
            )
            db.session.add(driver)
    
    db.session.commit()

def check_schedule_conflict(driver, start_time, end_time, exclude_id=None):
    """Check if a driver has any schedule conflicts on the same date"""
    # Convert time strings to time objects if they're strings
    if isinstance(start_time, str):
        start_time_obj = datetime.strptime(start_time, '%H:%M').time()
        start_date = None  # We'll get this from the schedule
    else:
        start_time_obj = start_time.time()
        start_date = start_time.date()
    
    if isinstance(end_time, str):
        end_time_obj = datetime.strptime(end_time, '%H:%M').time()
    else:
        end_time_obj = end_time.time()
    
    # Get all schedules for the driver
    query = Schedule.query.filter_by(assigned_driver=driver)
    if exclude_id:
        query = query.filter(Schedule.id != exclude_id)
    schedules = query.all()
    
    for schedule in schedules:
        # Only check for conflicts on the same date
        if start_date and schedule.date != start_date:
            continue
            
        existing_start = schedule.start_time.time()
        existing_end = schedule.end_time.time()
        
        # Check for any overlap between time ranges
        if (
            (start_time_obj >= existing_start and start_time_obj < existing_end) or  # New start time falls within existing schedule
            (end_time_obj > existing_start and end_time_obj <= existing_end) or      # New end time falls within existing schedule
            (start_time_obj <= existing_start and end_time_obj >= existing_end)      # New schedule completely encompasses existing schedule
        ):
            return True, f"Schedule conflict: Driver {driver} already has a schedule from {existing_start.strftime('%H:%M')} to {existing_end.strftime('%H:%M')} on {schedule.date.strftime('%Y-%m-%d')}"
    
    return False, None

def check_leave_conflict(driver_username, date, start_time, end_time, exclude_id=None):
    """Check if a driver has any leave conflicts"""
    query = LeaveRequest.query.filter_by(
        driver_username=driver_username,
        date=date,
        status='approved'
    )
    if exclude_id:
        query = query.filter(LeaveRequest.id != exclude_id)
    
    leaves = query.all()
    start_time_obj = datetime.strptime(start_time, '%H:%M').time()
    end_time_obj = datetime.strptime(end_time, '%H:%M').time()
    
    for leave in leaves:
        existing_start = datetime.strptime(leave.start_time, '%H:%M').time()
        existing_end = datetime.strptime(leave.end_time, '%H:%M').time()
        
        if (start_time_obj <= existing_end and end_time_obj >= existing_start):
            return True, f"Leave conflict: You already have approved leave from {existing_start.strftime('%H:%M')} to {existing_end.strftime('%H:%M')} on {date}"
    
    return False, None

def check_route_conflict(route, start_time, end_time, exclude_id=None):
    """Check ONLY for driver conflicts (same driver on same date/time) and bus conflicts (same bus on same date/time)"""
    # Convert time strings to time objects if they're strings
    if isinstance(start_time, str):
        start_time_obj = datetime.strptime(start_time, '%H:%M').time()
        start_date = None  # We'll get this from the schedule
    else:
        start_time_obj = start_time.time()
        start_date = start_time.date()
    
    if isinstance(end_time, str):
        end_time_obj = datetime.strptime(end_time, '%H:%M').time()
    else:
        end_time_obj = end_time.time()
    
    # Get all schedules
    query = Schedule.query
    if exclude_id:
        query = query.filter(Schedule.id != exclude_id)
    schedules = query.all()
    
    for schedule in schedules:
        # Skip if dates don't match
        if start_date and schedule.date != start_date:
            continue
            
        # Convert schedule times to time objects
        existing_start = schedule.start_time.time()
        existing_end = schedule.end_time.time()
        
        # Check for time overlap only if dates match
        if (start_time_obj <= existing_end and end_time_obj >= existing_start):
            # Check if it's a driver conflict (same driver on same date/time)
            if schedule.assigned_driver:
                return True, f"Driver conflict: Driver {schedule.assigned_driver} is already assigned from {existing_start.strftime('%H:%M')} to {existing_end.strftime('%H:%M')} on {schedule.date.strftime('%Y-%m-%d')}"
            
            # Check if it's a bus conflict (same bus on same date/time)
            if schedule.bus_number:
                return True, f"Bus conflict: Bus {schedule.bus_number} is already assigned from {existing_start.strftime('%H:%M')} to {existing_end.strftime('%H:%M')} on {schedule.date.strftime('%Y-%m-%d')}"
    
    return False, None

# Home Page
@app.route('/')
def index():
    return redirect(url_for('login'))

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('driver_dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            if user.role != role:
                flash('Invalid role selected!', 'danger')
                return redirect(url_for('login'))
                
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            flash('Login successful!', 'success')
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('driver_dashboard'))
        else:
            flash('Invalid username or password!', 'danger')
    
    return render_template('login.html')

# Forgot Password
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form['username']
        user = User.query.filter_by(username=username).first()
        if user:
            # In a real application, you would send an email with a reset link
            # For this demo, we'll just show the password
            flash(f'Your password is: {user.username}123', 'info')
        else:
            flash('Username not found!', 'danger')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

# Change Password
@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        user = User.query.get(session['user_id'])
        
        if not check_password_hash(user.password, current_password):
            flash('Current password is incorrect!', 'danger')
            return redirect(url_for('change_password'))
        
        if new_password != confirm_password:
            flash('New passwords do not match!', 'danger')
            return redirect(url_for('change_password'))
        
        user.password = generate_password_hash(new_password)
        db.session.commit()
        flash('Password changed successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('change_password.html')

# Dashboard
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session['role'] == 'admin':
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('driver_dashboard'))

# Schedule Management Routes
@app.route('/schedules')
@login_required
def manage_schedules():
    if current_user.role != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    # Get all schedules with driver information, ordered by date and time
    schedules = Schedule.query.order_by(
        Schedule.date.asc(),
        Schedule.start_time.asc()
    ).all()
    
    # Get all drivers for the form
    drivers = User.query.filter_by(role='driver').all()
    
    return render_template('manage_schedules.html', 
                         schedules=schedules,
                         drivers=drivers,
                         today=date.today())

@app.route('/schedules/add', methods=['GET', 'POST'])
@login_required
def add_schedule():
    if current_user.role != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    if request.method == 'POST':
        try:
            # Get form data
            date = request.form['date']
            start_time = request.form['start_time']
            end_time = request.form['end_time']
            driver = request.form['driver']
            bus_number = request.form['bus_number']
            capacity = int(request.form['capacity'])
            route = request.form['route']
            is_peak_hour = 'is_peak_hour' in request.form
            
            # Convert date and time strings to DateTime objects
            schedule_date = datetime.strptime(date, '%Y-%m-%d').date()
            start_datetime = datetime.combine(schedule_date, datetime.strptime(start_time, '%H:%M').time())
            end_datetime = datetime.combine(schedule_date, datetime.strptime(end_time, '%H:%M').time())
            
            # Check for schedule conflict
            has_conflict, message = check_schedule_conflict(driver, start_datetime, end_datetime)
            if has_conflict:
                flash(message, 'danger')
                return redirect(url_for('manage_schedules'))
            
            # Check for approved leave conflicts
            has_leave_conflict, leave_message = check_leave_conflict(driver, date, start_time, end_time)
            if has_leave_conflict:
                flash(leave_message, 'danger')
                return redirect(url_for('manage_schedules'))
            
            # Check for route conflicts - pass the full datetime objects
            has_route_conflict, route_message = check_route_conflict(route, start_datetime, end_datetime)
            if has_route_conflict:
                flash(route_message, 'danger')
                return redirect(url_for('manage_schedules'))
            
            # Create new schedule
            new_schedule = Schedule(
                date=schedule_date,
                start_time=start_datetime,
                end_time=end_datetime,
                route=route,
                bus_number=bus_number,
                capacity=capacity,
                assigned_driver=driver,
                is_peak_hour=is_peak_hour,
                created_by=current_user.username,
                status='scheduled'
            )
            
            db.session.add(new_schedule)
            
            # Create notification only for the assigned driver
            notification = Notification(
                recipient_username=driver,
                title='New Schedule Assignment',
                message=f'You have been assigned to route {route} on {date} from {start_time} to {end_time}.',
                notification_type='schedule_update',
                priority='high'
            )
            db.session.add(notification)
            
            db.session.commit()
            flash('Schedule created successfully!', 'success')
            return redirect(url_for('manage_schedules'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating schedule: {str(e)}', 'danger')
            return redirect(url_for('manage_schedules'))
    
    # GET request - render the form
    drivers = User.query.filter_by(role='driver').all()
    return render_template('manage_schedules.html', drivers=drivers, today=date.today())

@app.route('/schedules/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_schedule(id):
    if current_user.role != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    schedule = Schedule.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Get form data
            schedule_date = request.form['date']
            start_time = request.form['start_time']
            end_time = request.form['end_time']
            driver = request.form['driver']
            bus_number = request.form['bus_number']
            capacity = int(request.form['capacity'])
            route = request.form['route']
            is_peak_hour = 'is_peak_hour' in request.form
            
            # Convert date and time strings to DateTime objects
            schedule_date = datetime.strptime(schedule_date, '%Y-%m-%d').date()
            start_datetime = datetime.combine(schedule_date, datetime.strptime(start_time, '%H:%M').time())
            end_datetime = datetime.combine(schedule_date, datetime.strptime(end_time, '%H:%M').time())
            
            # Check for schedule conflict (excluding current schedule)
            has_conflict, message = check_schedule_conflict(driver, start_datetime, end_datetime, exclude_id=id)
            if has_conflict:
                flash(message, 'danger')
                return redirect(url_for('edit_schedule', id=id))
            
            # Check for approved leave conflicts
            has_leave_conflict, leave_message = check_leave_conflict(driver, schedule_date.strftime('%Y-%m-%d'), start_time, end_time)
            if has_leave_conflict:
                flash(leave_message, 'danger')
                return redirect(url_for('edit_schedule', id=id))
            
            # Check for route conflicts (excluding current schedule) - pass the full datetime objects
            has_route_conflict, route_message = check_route_conflict(route, start_datetime, end_datetime, exclude_id=id)
            if has_route_conflict:
                flash(route_message, 'danger')
                return redirect(url_for('edit_schedule', id=id))
            
            # Update schedule
            schedule.date = schedule_date
            schedule.start_time = start_datetime
            schedule.end_time = end_datetime
            schedule.route = route
            schedule.bus_number = bus_number
            schedule.capacity = capacity
            schedule.assigned_driver = driver
            schedule.is_peak_hour = is_peak_hour
            schedule.last_modified = datetime.utcnow()
            
            # Create notification for the assigned driver
            notification = Notification(
                recipient_username=driver,
                title='Schedule Updated',
                message=f'Your schedule has been updated for {schedule_date.strftime("%Y-%m-%d")} from {start_time} to {end_time} on route {route}.',
                notification_type='schedule_update',
                priority='high'
            )
            db.session.add(notification)
            
            db.session.commit()
            flash('Schedule updated successfully!', 'success')
            return redirect(url_for('manage_schedules'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating schedule: {str(e)}', 'danger')
            return redirect(url_for('edit_schedule', id=id))
    
    # GET request - render the edit form
    drivers = User.query.filter_by(role='driver').all()
    return render_template('edit_schedule.html', 
                         schedule=schedule, 
                         drivers=drivers,
                         today=date.today())

@app.route('/schedules/delete/<int:id>')
@login_required
def delete_schedule(id):
    if current_user.role != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    schedule = Schedule.query.get_or_404(id)
    
    try:
        # Create notification for the driver
        notification = Notification(
            recipient_username=schedule.assigned_driver,
            title='Schedule Cancelled',
            message=f'Your schedule for {schedule.date} on route {schedule.route} has been cancelled.',
            notification_type='schedule_update',
            priority='high'
        )
        db.session.add(notification)
        
        db.session.delete(schedule)
        db.session.commit()
        flash('Schedule deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting schedule: {str(e)}', 'danger')
    
    return redirect(url_for('manage_schedules'))

# Attendance Management Routes
@app.route('/view-attendance', methods=['GET', 'POST'])
@login_required
def view_attendance():
    if current_user.role != 'admin':
        flash('Access denied. Admin only.', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    # Get all drivers for the dropdown
    drivers = User.query.filter_by(role='driver').all()
    
    # Get selected driver's attendance if provided
    selected_driver = request.args.get('driver')
    attendance_records = []
    
    if selected_driver:
        attendance_records = Attendance.query.filter_by(
            driver_username=selected_driver
        ).order_by(Attendance.date.desc()).all()
    
    return render_template('view_attendance.html', 
                         drivers=drivers,
                         selected_driver=selected_driver,
                         attendance_records=attendance_records)

@app.route('/attendance/mark', methods=['GET', 'POST'])
@login_required
def mark_attendance():
    if current_user.role != 'driver':
        flash('Access denied!', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    # Get today's attendance record if exists
    today = date.today()
    today_attendance = Attendance.query.filter_by(
        driver_username=current_user.username,
        date=today
    ).first()
    
    if request.method == 'POST':
        action = request.form.get('action')
        photo_data = request.form.get('photo')
        
        if not photo_data:
            flash('Please capture a photo first!', 'danger')
            return redirect(url_for('mark_attendance'))
        
        current_time = datetime.now()
        
        if not today_attendance:
            if action != 'check_in':
                flash('You must check in first!', 'danger')
                return redirect(url_for('mark_attendance'))
            
            # Create new attendance record
            today_attendance = Attendance(
                driver_username=current_user.username,
                date=today,
                check_in_time=current_time,
                check_in_photo=photo_data,
                status='present'
            )
            db.session.add(today_attendance)
            flash('Check-in recorded successfully!', 'success')
        
        else:
            if action == 'check_in':
                if today_attendance.check_in_time:
                    flash('You have already checked in today!', 'warning')
                    return redirect(url_for('mark_attendance'))
                
                today_attendance.check_in_time = current_time
                today_attendance.check_in_photo = photo_data
                flash('Check-in recorded successfully!', 'success')
            
            elif action == 'check_out':
                if today_attendance.check_out_time:
                    flash('You have already checked out today!', 'warning')
                    return redirect(url_for('mark_attendance'))
                
                today_attendance.check_out_time = current_time
                today_attendance.check_out_photo = photo_data
                
                # Calculate total hours
                if today_attendance.check_in_time:
                    time_diff = current_time - today_attendance.check_in_time
                    today_attendance.total_hours = time_diff.total_seconds() / 3600
                
                flash('Check-out recorded successfully!', 'success')
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f'Error recording attendance: {str(e)}', 'danger')
        
        return redirect(url_for('mark_attendance'))
    
    return render_template('mark_attendance.html', 
                         today_attendance=today_attendance,
                         today=today)

# Dashboard Routes
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    # Get counts for dashboard
    total_drivers = User.query.filter_by(role='driver').count()
    pending_leaves = LeaveRequest.query.filter_by(status='pending').count()
    active_schedules = Schedule.query.filter_by(status='active').count()
    
    # Get the 3 most recent notifications for admin (only shift swaps and leave requests)
    recent_notifications = Notification.query.filter(
        Notification.recipient_username == 'admin',
        Notification.notification_type.in_(['shift_swap', 'leave_request'])
    ).order_by(Notification.created_at.desc()).limit(3).all()
    
    return render_template('admin_dashboard.html',
                         total_drivers=total_drivers,
                         pending_leaves=pending_leaves,
                         active_schedules=active_schedules,
                         recent_notifications=recent_notifications)

@app.route('/driver/dashboard')
@login_required
def driver_dashboard():
    if current_user.role != 'driver':
        flash('Access denied!', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    # Get driver-specific data
    today = date.today()
    today_schedule = Schedule.query.filter_by(
        assigned_driver=current_user.username,
        date=today
    ).all()
    
    upcoming_leaves = LeaveRequest.query.filter_by(
        driver_username=current_user.username,
        status='approved'
    ).filter(LeaveRequest.date >= today).all()
    
    recent_notifications = Notification.query.filter_by(
        recipient_username=current_user.username
    ).order_by(Notification.created_at.desc()).limit(5).all()
    
    # Get shift swap requests with schedule information
    shift_swaps = []
    swap_requests = ShiftSwap.query.filter_by(
        requesting_driver=current_user.username
    ).order_by(ShiftSwap.created_at.desc()).all()
    
    for swap in swap_requests:
        schedule = Schedule.query.get(swap.schedule_id)
        if schedule:
            shift_swaps.append({
                'swap': swap,
                'schedule': schedule
            })
    
    return render_template('driver_dashboard.html',
                         today_schedule=today_schedule,
                         upcoming_leaves=upcoming_leaves,
                         recent_notifications=recent_notifications,
                         shift_swaps=shift_swaps)

# View Schedules
@app.route('/view-schedules')
@login_required
def view_schedules():
    if current_user.role == 'admin':
        schedules = Schedule.query.order_by(
            Schedule.date.asc(),
            Schedule.start_time.asc()
        ).all()
    else:
        # For drivers, only show their assigned schedules
        schedules = Schedule.query.filter_by(
            assigned_driver=current_user.username
        ).order_by(
            Schedule.date.asc(),
            Schedule.start_time.asc()
        ).all()
    
    return render_template('view_schedules.html', schedules=schedules)

# Apply for Leave
@app.route('/apply-leave', methods=['GET', 'POST'])
@login_required
def apply_leave():
    if current_user.role != 'driver':
        flash('Access denied!', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        leave_type = request.form.get('leave_type')
        session = request.form.get('session')
        reason = request.form.get('reason')
        contact = request.form.get('contact')
        
        # Create leave request
        leave_request = LeaveRequest(
            driver_username=current_user.username,
            date=start_date,
            start_time='00:00' if session in ['full_day', 'half_day_morning'] else '12:00',
            end_time='23:59' if session in ['full_day', 'half_day_afternoon'] else '12:00',
            reason=reason,
            status='pending'
        )
        db.session.add(leave_request)
        
        # Create notification for admin
        notification = Notification(
            recipient_username='admin',
            title='New Leave Request',
            message=f'Driver {current_user.username} has requested leave from {start_date} to {end_date}.',
            notification_type='leave_request',
            priority='normal'
        )
        db.session.add(notification)
        db.session.commit()
        
        flash('Leave request submitted successfully!', 'success')
        return redirect(url_for('my_leaves'))
    
    return render_template('apply_leave.html', today=date.today().strftime('%Y-%m-%d'))

# Manage Leave Requests
@app.route('/manage-leaves')
@login_required
def manage_leaves():
    if current_user.role != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    # Get all leave requests ordered by creation date
    leave_requests = LeaveRequest.query.order_by(LeaveRequest.created_at.desc()).all()
    
    # Get all drivers for the dropdown
    drivers = User.query.filter_by(role='driver').all()
    
    return render_template('manage_leaves.html', 
                         leave_requests=leave_requests,
                         drivers=drivers,
                         today=date.today())

@app.route('/handle-leave/<int:id>/<string:action>', methods=['POST'])
@login_required
def handle_leave(id, action):
    if current_user.role != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    leave_request = LeaveRequest.query.get_or_404(id)
    response = request.form.get('response', '')
    
    try:
        if action == 'approve':
            # Check for schedule conflicts
            schedules = Schedule.query.filter_by(
                assigned_driver=leave_request.driver_username,
                date=leave_request.date
            ).all()
            
            if schedules:
                flash('Cannot approve leave: Driver has scheduled routes on this date.', 'danger')
                return redirect(url_for('manage_leaves'))
            
            leave_request.status = 'approved'
        elif action == 'reject':
            leave_request.status = 'rejected'
        
        leave_request.admin_response = response
        leave_request.response_time = datetime.utcnow()
        
        # Create notification for driver
        notification = Notification(
            recipient_username=leave_request.driver_username,
            title=f'Leave Request {action.capitalize()}d',
            message=f'Your leave request for {leave_request.date} has been {action}d. {response}',
            notification_type='leave',
            priority='high'
        )
        db.session.add(notification)
        db.session.commit()
        
        flash(f'Leave request {action}d successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing leave request: {str(e)}', 'danger')
    
    return redirect(url_for('manage_leaves'))

# Get Pending Leave Count
def get_pending_leave_count():
    return LeaveRequest.query.filter_by(status='pending').count()

# Get Pending Leave Count for Driver
def get_driver_pending_leaves(username):
    return LeaveRequest.query.filter_by(
        driver_username=username,
        status='pending'
    ).count()

# Profile Management
@app.route('/profile')
@login_required
def profile():
    if current_user.role == 'driver':
        license = DriverLicense.query.filter_by(driver_username=current_user.username).first()
        return render_template('profile.html', user=current_user, license=license)
    return render_template('profile.html', user=current_user)

@app.route('/view-drivers')
@login_required
def view_drivers():
    if current_user.role != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    # Get all drivers with their license information
    drivers = User.query.filter_by(role='driver').all()
    
    # Get license information for each driver
    driver_licenses = {}
    for driver in drivers:
        license = DriverLicense.query.filter_by(driver_username=driver.username).first()
        if license:
            driver_licenses[driver.username] = {
                'status': license.status,
                'expiry_date': license.expiry_date,
                'license_number': license.license_number
            }
    
    return render_template('view_drivers.html', 
                         drivers=drivers,
                         driver_licenses=driver_licenses)

@app.route('/update-profile', methods=['POST'])
@login_required
def update_profile():
    try:
        current_user.full_name = request.form.get('full_name')
        if request.form.get('dob'):
            current_user.dob = datetime.strptime(request.form.get('dob'), '%Y-%m-%d').date()
        current_user.phone = request.form.get('phone')
        current_user.email = request.form.get('email')
        current_user.address = request.form.get('address')
        
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename != '':
                # Ensure upload directory exists
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                
                filename = secure_filename(f"{current_user.username}_{file.filename}")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                current_user.profile_pic = filename
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating profile: {str(e)}', 'danger')
    
    return redirect(url_for('profile'))

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')

@app.route('/update-settings', methods=['POST'])
@login_required
def update_settings():
    try:
        # Update account information
        if 'full_name' in request.form:
            current_user.full_name = request.form['full_name']
        if 'email' in request.form:
            current_user.email = request.form['email']
        if 'phone' in request.form:
            current_user.phone = request.form['phone']
        
        # Update password if provided
        if 'current_password' in request.form and request.form['current_password']:
            if check_password_hash(current_user.password, request.form['current_password']):
                if request.form['new_password'] == request.form['confirm_password']:
                    current_user.password = generate_password_hash(request.form['new_password'])
                else:
                    flash('New passwords do not match.', 'danger')
                    return redirect(url_for('settings'))
            else:
                flash('Current password is incorrect.', 'danger')
                return redirect(url_for('settings'))
        
        # Update system settings if admin
        if current_user.role == 'admin':
            if 'notifications_enabled' in request.form:
                # Update notification settings
                pass
            if 'timezone' in request.form:
                # Update timezone settings
                pass
        
        db.session.commit()
        flash('Settings updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error updating settings. Please try again.', 'danger')
    
    return redirect(url_for('settings'))

# View My Leave Requests (for drivers)
@app.route('/my-leaves')
@login_required
def my_leaves():
    if current_user.role != 'driver':
        flash('Access denied!', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    leaves = LeaveRequest.query.filter_by(
        driver_username=current_user.username
    ).order_by(LeaveRequest.created_at.desc()).all()
    
    return render_template('my_leaves.html', leaves=leaves)

# Logout route
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload-license', methods=['GET', 'POST'])
@login_required
def upload_license():
    if current_user.role != 'driver':
        flash('Access denied!', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        if 'license' not in request.files:
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        file = request.files['license']
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{current_user.username}_{file.filename}")
            if not os.path.exists(app.config['UPLOAD_FOLDER_LICENSE']):
                os.makedirs(app.config['UPLOAD_FOLDER_LICENSE'])
            
            file_path = os.path.join(app.config['UPLOAD_FOLDER_LICENSE'], filename)
            file.save(file_path)
            
            # Save to database with only the filename
            license_entry = DriverLicense(
                driver_username=current_user.username,
                file_path=filename,  # Store only the filename
                license_number=request.form.get('license_number'),
                license_type=request.form.get('license_type'),
                expiry_date=datetime.strptime(request.form.get('expiry_date'), '%Y-%m-%d').date() if request.form.get('expiry_date') else None
            )
            db.session.add(license_entry)
            db.session.commit()
            
            flash('License uploaded successfully!', 'success')
            return redirect(url_for('driver_dashboard'))
        
        flash('Invalid file type. Allowed types: PDF, PNG, JPG, JPEG', 'danger')
        return redirect(request.url)
    
    return render_template('upload_license.html')

# Shift Management Routes
@app.route('/request-shift-swap', methods=['GET', 'POST'])
@login_required
def request_shift_swap():
    if request.method == 'GET':
        # Get current driver's shifts
        your_shifts = Schedule.query.filter_by(assigned_driver=current_user.username).all()
        
        return render_template('request_shift_swap.html',
                             your_shifts=your_shifts,
                             today=date.today())
    
    # Handle POST request
    swap_date = request.form.get('swap_date')
    your_shift_id = request.form.get('your_shift')
    reason = request.form.get('reason')
    
    if not all([swap_date, your_shift_id, reason]):
        flash('All fields are required', 'danger')
        return redirect(url_for('request_shift_swap'))
    
    # Get the schedule details
    schedule = Schedule.query.get(your_shift_id)
    if not schedule:
        flash('Invalid shift selected', 'danger')
        return redirect(url_for('request_shift_swap'))
    
    # Create new shift swap request
    swap_request = ShiftSwap(
        requesting_driver=current_user.username,
        schedule_id=your_shift_id,
        reason=reason,
        status='pending'
    )
    
    try:
        db.session.add(swap_request)
        
        # Create notification for admin
        notification = Notification(
            recipient_username='admin',
            title='New Shift Swap Request',
            message=f'Driver {current_user.username} has requested to swap their shift on {swap_date} for route {schedule.route} ({schedule.start_time.strftime("%H:%M")} - {schedule.end_time.strftime("%H:%M")}).',
            notification_type='shift_swap',
            priority='normal'
        )
        db.session.add(notification)
        
        db.session.commit()
        flash('Shift swap request submitted successfully', 'success')
        return redirect(url_for('driver_dashboard'))
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while submitting your request', 'danger')
        return redirect(url_for('request_shift_swap'))

@app.route('/api/driver-shifts')
@login_required
def get_driver_shifts():
    date_str = request.args.get('date')
    driver = request.args.get('driver')
    
    if not date_str or not driver:
        return jsonify([])
    
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        shifts = Schedule.query.filter_by(
            driver_username=driver,
            date=target_date
        ).all()
        
        return jsonify([{
            'id': shift.id,
            'route_name': shift.route_name,
            'start_time': shift.start_time.strftime('%H:%M'),
            'end_time': shift.end_time.strftime('%H:%M')
        } for shift in shifts])
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Break Period Management Routes
@app.route('/manage-breaks', methods=['GET', 'POST'])
@login_required
def manage_breaks():
    if current_user.role != 'admin':
        flash('Access denied. Admin only.', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    if request.method == 'POST':
        try:
            driver_username = request.form['driver']
            break_date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
            start_time_str = request.form['start_time']
            end_time_str = request.form['end_time']
            reason = request.form['reason']
            
            # Combine date and time for start and end times
            start_time = datetime.combine(break_date, datetime.strptime(start_time_str, '%H:%M').time())
            end_time = datetime.combine(break_date, datetime.strptime(end_time_str, '%H:%M').time())
            
            # Check if driver exists
            driver = User.query.filter_by(username=driver_username, role='driver').first()
            if not driver:
                flash('Driver not found.', 'danger')
                return redirect(url_for('manage_breaks'))
            
            # Check if break time conflicts with schedule
            schedule = Schedule.query.filter_by(
                assigned_driver=driver_username,
                date=break_date
            ).first()
            
            if schedule:
                schedule_start = datetime.combine(break_date, datetime.strptime(schedule.start_time, '%H:%M').time())
                schedule_end = datetime.combine(break_date, datetime.strptime(schedule.end_time, '%H:%M').time())
                
                if (start_time < schedule_end and end_time > schedule_start):
                    flash('Break time conflicts with driver\'s schedule.', 'danger')
                    return redirect(url_for('manage_breaks'))
            
            # Create new break record
            new_break = BreakPeriod(
                driver_username=driver_username,
                schedule_id=schedule.id if schedule else None,
                start_time=start_time,
                end_time=end_time,
                break_type='rest',  # Default to rest break
                status='scheduled'
            )
            
            db.session.add(new_break)
            db.session.commit()
            
            # Create notification for driver
            notification = Notification(
                recipient_username=driver_username,
                title='Break Scheduled',
                message=f'Your break has been scheduled for {break_date} from {start_time_str} to {end_time_str}',
                notification_type='break',
                priority='normal'
            )
            db.session.add(notification)
            db.session.commit()
            
            flash('Break scheduled successfully.', 'success')
            return redirect(url_for('manage_breaks'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error scheduling break: {str(e)}', 'danger')
            return redirect(url_for('manage_breaks'))
    
    # GET request - show break management page
    drivers = User.query.filter_by(role='driver').all()
    breaks = BreakPeriod.query.order_by(BreakPeriod.start_time.desc()).all()
    return render_template('manage_breaks.html', drivers=drivers, breaks=breaks, today=date.today())

@app.route('/start-break/<int:break_id>')
def start_break(break_id):
    if 'user_id' not in session or session['role'] != 'driver':
        return redirect(url_for('login'))
    
    break_period = BreakPeriod.query.get_or_404(break_id)
    if break_period.driver_username != session['username']:
        flash('Unauthorized access!', 'danger')
        return redirect(url_for('manage_breaks'))
    
    break_period.status = 'ongoing'
    break_period.start_time = datetime.utcnow()
    db.session.commit()
    
    flash('Break started successfully!', 'success')
    return redirect(url_for('manage_breaks'))

@app.route('/end-break/<int:break_id>')
def end_break(break_id):
    if 'user_id' not in session or session['role'] != 'driver':
        return redirect(url_for('login'))
    
    break_period = BreakPeriod.query.get_or_404(break_id)
    if break_period.driver_username != session['username']:
        flash('Unauthorized access!', 'danger')
        return redirect(url_for('manage_breaks'))
    
    break_period.status = 'completed'
    break_period.end_time = datetime.utcnow()
    db.session.commit()
    
    flash('Break ended successfully!', 'success')
    return redirect(url_for('manage_breaks'))

# Notification Routes
@app.route('/notifications')
@login_required
def notifications():
    if current_user.role == 'admin':
        # For admin, show only shift swaps and leave requests
        notifications = Notification.query.filter(
            Notification.recipient_username == 'admin',
            Notification.notification_type.in_(['shift_swap', 'leave_request'])
        ).order_by(Notification.created_at.desc()).all()
    else:
        # For drivers, show all their notifications
        notifications = Notification.query.filter_by(
            recipient_username=current_user.username
        ).order_by(Notification.created_at.desc()).all()
    
    return render_template('notifications.html', 
                         notifications=notifications,
                         is_admin=current_user.role == 'admin')

@app.route('/mark-notification-read/<int:notification_id>')
@login_required
def mark_notification_read(notification_id):
    notification = Notification.query.get_or_404(notification_id)
    
    # Check if user is authorized to mark this notification as read
    if current_user.role != 'admin' and notification.recipient_username != current_user.username:
        flash('Unauthorized access!', 'danger')
        return redirect(url_for('notifications'))
    
    notification.is_read = True
    notification.read_at = datetime.utcnow()
    db.session.commit()
    
    return redirect(url_for('notifications'))

@app.route('/delete-notification/<int:notification_id>')
@login_required
def delete_notification(notification_id):
    notification = Notification.query.get_or_404(notification_id)
    
    # Check if user is authorized to delete this notification
    if current_user.role != 'admin' and notification.recipient_username != current_user.username:
        flash('Unauthorized access!', 'danger')
        return redirect(url_for('notifications'))
    
    try:
        db.session.delete(notification)
        db.session.commit()
        flash('Notification deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting notification: {str(e)}', 'danger')
    
    return redirect(url_for('notifications'))

# Reporting and Analytics Routes
@app.route('/reports')
def reports_dashboard():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    return render_template('reports_dashboard.html')

@app.route('/reports/performance', methods=['GET', 'POST'])
def performance_reports():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        driver_username = request.form.get('driver_username')
        
        # Get performance metrics
        query = PerformanceMetric.query.filter(
            PerformanceMetric.date.between(start_date, end_date)
        )
        if driver_username:
            query = query.filter_by(driver_username=driver_username)
        
        metrics = query.all()
        
        # Calculate averages
        total_metrics = len(metrics)
        if total_metrics > 0:
            avg_on_time = sum(m.on_time_arrival_percentage or 0 for m in metrics) / total_metrics
            avg_break_compliance = sum(m.break_compliance_percentage or 0 for m in metrics) / total_metrics
            avg_hours = sum(m.total_hours_worked or 0 for m in metrics) / total_metrics
            total_incidents = sum(m.incidents_reported or 0 for m in metrics)
            avg_rating = sum(m.passenger_feedback_rating or 0 for m in metrics) / total_metrics
        else:
            avg_on_time = avg_break_compliance = avg_hours = total_incidents = avg_rating = 0
        
        summary = {
            'avg_on_time': round(avg_on_time, 2),
            'avg_break_compliance': round(avg_break_compliance, 2),
            'avg_hours': round(avg_hours, 2),
            'total_incidents': total_incidents,
            'avg_rating': round(avg_rating, 2)
        }
        
        return render_template('performance_report.html',
                             metrics=metrics,
                             summary=summary,
                             start_date=start_date,
                             end_date=end_date)
    
    drivers = User.query.filter_by(role='driver').all()
    return render_template('performance_report.html', drivers=drivers)

@app.route('/reports/incidents', methods=['GET', 'POST'])
def incident_reports():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        incident_type = request.form.get('incident_type')
        
        # Get incidents from performance metrics
        query = PerformanceMetric.query.filter(
            PerformanceMetric.date.between(start_date, end_date),
            PerformanceMetric.incidents_reported > 0
        )
        
        incidents = query.all()
        
        return render_template('incident_report.html',
                             incidents=incidents,
                             start_date=start_date,
                             end_date=end_date)
    
    return render_template('incident_report.html')

@app.route('/reports/compliance', methods=['GET', 'POST'])
def compliance_reports():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        
        # Get break compliance from performance metrics
        metrics = PerformanceMetric.query.filter(
            PerformanceMetric.date.between(start_date, end_date)
        ).all()
        
        # Get driver license status
        drivers = User.query.filter_by(role='driver').all()
        license_status = []
        for driver in drivers:
            if driver.license_expiry:
                days_to_expiry = (driver.license_expiry - datetime.utcnow().date()).days
                status = 'Valid' if days_to_expiry > 0 else 'Expired'
            else:
                status = 'Not Provided'
                days_to_expiry = None
            
            license_status.append({
                'username': driver.username,
                'full_name': driver.full_name,
                'license_number': driver.license_number,
                'status': status,
                'days_to_expiry': days_to_expiry
            })
        
        return render_template('compliance_report.html',
                             metrics=metrics,
                             license_status=license_status,
                             start_date=start_date,
                             end_date=end_date)
    
    return render_template('compliance_report.html')

@app.route('/reports/export/<report_type>')
def export_report(report_type):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    # Get date range from query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if start_date and end_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        if report_type == 'performance':
            metrics = PerformanceMetric.query.filter(
                PerformanceMetric.date.between(start_date, end_date)
            ).all()
            
            # Create CSV content
            csv_content = 'Date,Driver,On-Time %,Break Compliance %,Hours Worked,Incidents,Rating\n'
            for metric in metrics:
                csv_content += f'{metric.date},{metric.driver_username},{metric.on_time_arrival_percentage},'
                csv_content += f'{metric.break_compliance_percentage},{metric.total_hours_worked},'
                csv_content += f'{metric.incidents_reported},{metric.passenger_feedback_rating}\n'
            
            # Create response
            output = make_response(csv_content)
            output.headers['Content-Disposition'] = f'attachment; filename=performance_report_{start_date}_{end_date}.csv'
            output.headers['Content-type'] = 'text/csv'
            return output
    
    flash('Invalid date range for report export', 'danger')
    return redirect(url_for('reports_dashboard'))

# Get Pending Notifications Count
def get_pending_notifications(username):
    return Notification.query.filter_by(
        recipient_username=username,
        is_read=False
    ).count()

# Manage Licenses
@app.route('/manage-licenses')
@login_required
def manage_licenses():
    if current_user.role != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    # Get all licenses with driver information
    licenses = DriverLicense.query.order_by(DriverLicense.upload_date.desc()).all()
    
    return render_template('manage_licenses.html', licenses=licenses)

# View Performance Metrics
@app.route('/view-performance')
def view_performance():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if session['role'] == 'admin':
        metrics = PerformanceMetric.query.all()
    else:
        metrics = PerformanceMetric.query.filter_by(driver_username=session['username']).all()
    
    return render_template('view_performance.html', metrics=metrics)

# Bus Assignment Management Routes
@app.route('/manage_assignments')
def manage_assignments():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    # Get all drivers and assignments
    drivers = User.query.filter_by(role='driver').all()
    assignments = BusAssignment.query.order_by(BusAssignment.date.desc()).all()
    
    # Get all leave dates to prevent scheduling on leave days
    leave_dates = []
    approved_leaves = LeaveRequest.query.filter_by(status='approved').all()
    for leave in approved_leaves:
        current_date = leave.start_date
        while current_date <= leave.end_date:
            leave_dates.append(current_date.strftime('%Y-%m-%d'))
            current_date += timedelta(days=1)
    
    return render_template('manage_assignments.html', 
                         drivers=drivers,
                         assignments=assignments,
                         today=date.today().strftime('%Y-%m-%d'),
                         leave_dates=leave_dates)

@app.route('/assign_schedule', methods=['POST'])
def assign_schedule():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    driver_id = request.form.get('driver_id')
    schedule_date = datetime.strptime(request.form.get('schedule_date'), '%Y-%m-%d').date()
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    bus_number = request.form.get('bus_number')
    
    # Validate driver availability
    driver = User.query.get(driver_id)
    if not driver:
        flash('Invalid driver selected.', 'danger')
        return redirect(url_for('manage_assignments'))
    
    # Check for leave conflicts - only for approved leaves on the specific date
    leave_conflict = LeaveRequest.query.filter(
        LeaveRequest.driver_username == driver.username,
        LeaveRequest.status == 'approved',
        LeaveRequest.date == schedule_date.strftime('%Y-%m-%d')
    ).first()
    
    if leave_conflict:
        return jsonify({
            'status': 'error',
            'message': f'Driver has approved leave on {schedule_date.strftime("%Y-%m-%d")}'
        }), 400
    
    # Check for schedule conflicts
    schedule_conflict = BusAssignment.query.filter(
        BusAssignment.driver_id == driver_id,
        BusAssignment.date == schedule_date,
        or_(
            and_(BusAssignment.start_time <= start_time, BusAssignment.end_time > start_time),
            and_(BusAssignment.start_time < end_time, BusAssignment.end_time >= end_time)
        )
    ).first()
    
    if schedule_conflict:
        return jsonify({
            'status': 'error',
            'message': 'Driver already has an assignment during this time period.'
        }), 400
    
    # Create new assignment
    assignment = BusAssignment(
        driver_id=driver_id,
        driver_name=driver.username,
        date=schedule_date,
        start_time=start_time,
        end_time=end_time,
        bus_number=bus_number,
        status='scheduled'
    )
    
    try:
        db.session.add(assignment)
        db.session.commit()
        
        # Create notification for driver
        notification = Notification(
            recipient_username=driver.username,
            title='New Bus Assignment',
            message=f'You have been assigned bus {bus_number} on {schedule_date.strftime("%Y-%m-%d")} from {start_time} to {end_time}.',
            notification_type='schedule_update',
            priority='high'
        )
        db.session.add(notification)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Bus assignment created successfully!'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/edit-assignment/<int:id>', methods=['POST'])
def edit_assignment(id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    assignment = BusAssignment.query.get_or_404(id)
    driver_id = request.form.get('driver_id')
    schedule_date = request.form.get('schedule_date')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    bus_number = request.form.get('bus_number')
    
    # Validate driver availability (similar checks as assign_schedule)
    driver = User.query.get(driver_id)
    if not driver:
        flash('Invalid driver selected.', 'danger')
        return redirect(url_for('manage_assignments'))
    
    # Check for conflicts excluding current assignment
    schedule_conflict = BusAssignment.query.filter(
        BusAssignment.driver_id == driver_id,
        BusAssignment.date == schedule_date,
        BusAssignment.id != id,
        or_(
            and_(BusAssignment.start_time <= start_time, BusAssignment.end_time > start_time),
            and_(BusAssignment.start_time < end_time, BusAssignment.end_time >= end_time)
        )
    ).first()
    
    if schedule_conflict:
        flash('Driver already has an assignment during this time period.', 'danger')
        return redirect(url_for('manage_assignments'))
    
    # Update assignment
    assignment.driver_id = driver_id
    assignment.driver_name = driver.username
    assignment.date = schedule_date
    assignment.start_time = start_time
    assignment.end_time = end_time
    assignment.bus_number = bus_number
    
    db.session.commit()
    
    # Notify driver of changes
    notification = Notification(
        recipient_username=driver.username,
        title='Bus Assignment Updated',
        message=f'Your bus assignment for {schedule_date} has been updated. New details: Bus {bus_number} from {start_time} to {end_time}.',
        notification_type='schedule_update',
        priority='high'
    )
    db.session.add(notification)
    db.session.commit()
    
    flash('Bus assignment updated successfully!', 'success')
    return redirect(url_for('manage_assignments'))

@app.route('/delete-assignment/<int:id>')
def delete_assignment(id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    assignment = BusAssignment.query.get_or_404(id)
    driver_username = assignment.driver_name
    assignment_date = assignment.date
    
    db.session.delete(assignment)
    
    # Notify driver of cancellation
    notification = Notification(
        recipient_username=driver_username,
        title='Bus Assignment Cancelled',
        message=f'Your bus assignment for {assignment_date} has been cancelled.',
        notification_type='schedule_update',
        priority='high'
    )
    db.session.add(notification)
    db.session.commit()
    
    flash('Bus assignment deleted successfully!', 'success')
    return redirect(url_for('manage_assignments'))

@app.route('/api/available-drivers')
@login_required
def get_available_drivers():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    date = request.args.get('date')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    
    if not all([date, start_time, end_time]):
        return jsonify({'error': 'Missing parameters'}), 400
    
    # Convert date string to date object
    schedule_date = datetime.strptime(date, '%Y-%m-%d').date()
    
    # Get all drivers
    all_drivers = User.query.filter_by(role='driver').all()
    available_drivers = []
    
    for driver in all_drivers:
        # Check for existing schedules
        schedule_conflict = Schedule.query.filter(
            Schedule.assigned_driver == driver.username,
            Schedule.date == schedule_date,
            Schedule.start_time <= end_time,
            Schedule.end_time >= start_time
        ).first()
        
        # Check for approved leaves
        leave_conflict = LeaveRequest.query.filter(
            LeaveRequest.driver_username == driver.username,
            LeaveRequest.date == date,
            LeaveRequest.status == 'approved',
            LeaveRequest.start_time <= end_time,
            LeaveRequest.end_time >= start_time
        ).first()
        
        if not schedule_conflict and not leave_conflict:
            available_drivers.append({
                'username': driver.username,
                'full_name': driver.full_name
            })
    
    return jsonify({'drivers': available_drivers})

@app.route('/api/schedule/<int:id>')
@login_required
def get_schedule(id):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    schedule = Schedule.query.get_or_404(id)
    return jsonify({
        'id': schedule.id,
        'date': schedule.date.strftime('%Y-%m-%d'),
        'start_time': schedule.start_time.strftime('%H:%M'),
        'end_time': schedule.end_time.strftime('%H:%M'),
        'driver_username': schedule.assigned_driver,
        'bus_number': schedule.bus_number,
        'capacity': schedule.capacity,
        'is_peak_hour': schedule.is_peak_hour
    })

@app.route('/manage-shift-swaps')
@login_required
def manage_shift_swaps():
    if current_user.role != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    # Get all shift swap requests with related information
    swap_requests = ShiftSwap.query.order_by(ShiftSwap.created_at.desc()).all()
    
    # Get schedule information for each swap request
    swap_details = []
    for request in swap_requests:
        schedule = Schedule.query.get(request.schedule_id)
        requesting_driver = User.query.filter_by(username=request.requesting_driver).first()
        target_driver = User.query.filter_by(username=request.target_driver).first() if request.target_driver else None
        
        swap_details.append({
            'request': request,
            'schedule': schedule,
            'requesting_driver_rel': requesting_driver,
            'target_driver_rel': target_driver
        })
    
    return render_template('manage_shift_swaps.html', 
                         swap_requests=swap_details)

@app.route('/handle-shift-swap', methods=['POST'])
@login_required
def handle_shift_swap():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied!'}), 403
    
    request_id = request.form.get('request_id')
    action = request.form.get('action')
    response = request.form.get('response', '')
    
    if not request_id or not action:
        return jsonify({'success': False, 'message': 'Missing required parameters'}), 400
    
    swap_request = ShiftSwap.query.get_or_404(request_id)
    
    if swap_request.status != 'pending':
        return jsonify({'success': False, 'message': 'This request has already been processed'}), 400
    
    try:
        if action == 'approve':
            # Get the requesting driver's schedule
            your_schedule = Schedule.query.get(swap_request.schedule_id)
            if not your_schedule:
                return jsonify({'success': False, 'message': 'Schedule not found'}), 400
            
            # If target driver is specified, check their availability
            if swap_request.target_driver:
                # Check if target driver has any schedule on this date
                target_schedule = Schedule.query.filter_by(
                    assigned_driver=swap_request.target_driver,
                    date=your_schedule.date
                ).first()
                
                if target_schedule:
                    # If target driver has a schedule, swap the drivers
                    temp_driver = your_schedule.assigned_driver
                    your_schedule.assigned_driver = target_schedule.assigned_driver
                    target_schedule.assigned_driver = temp_driver
                else:
                    # If target driver has no schedule, just assign the schedule to them
                    your_schedule.assigned_driver = swap_request.target_driver
            else:
                # If no target driver specified, just unassign the schedule
                your_schedule.assigned_driver = None
            
            swap_request.status = 'approved'
            swap_request.admin_response = response
            
            # Create notification for requesting driver
            notification = Notification(
                recipient_username=swap_request.requesting_driver,
                title='Shift Swap Approved',
                message=f'Your shift swap request has been approved. {response}',
                notification_type='shift_swap',
                priority='normal'
            )
            db.session.add(notification)
            
            # If target driver exists, notify them
            if swap_request.target_driver:
                target_notification = Notification(
                    recipient_username=swap_request.target_driver,
                    title='Shift Swap Approved',
                    message=f'Your shift has been swapped with {swap_request.requesting_driver}. {response}',
                    notification_type='shift_swap',
                    priority='normal'
                )
                db.session.add(target_notification)
            
        elif action == 'reject':
            swap_request.status = 'rejected'
            swap_request.admin_response = response
            
            # Create notification for requesting driver
            notification = Notification(
                recipient_username=swap_request.requesting_driver,
                title='Shift Swap Rejected',
                message=f'Your shift swap request has been rejected. {response}',
                notification_type='shift_swap',
                priority='normal'
            )
            db.session.add(notification)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Shift swap request processed successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/view-license')
@login_required
def view_license():
    if current_user.role != 'driver':
        flash('Access denied!', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    license_entry = DriverLicense.query.filter_by(driver_username=current_user.username).first()
    if not license_entry:
        flash('No license found', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    try:
        # Construct the full file path using the stored filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER_LICENSE'], license_entry.file_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError("License file not found")
        
        return send_from_directory(app.config['UPLOAD_FOLDER_LICENSE'], license_entry.file_path, as_attachment=True)
    except Exception as e:
        flash(f'Error viewing license: {str(e)}', 'danger')
        return redirect(url_for('driver_dashboard'))

@app.route('/edit-license', methods=['GET', 'POST'])
@login_required
def edit_license():
    if current_user.role != 'driver':
        flash('Access denied!', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    license = DriverLicense.query.filter_by(
        driver_username=current_user.username
    ).first()
    
    if request.method == 'POST':
        try:
            if 'license' in request.files:
                file = request.files['license']
                if file and allowed_file(file.filename):
                    filename = secure_filename(f"{current_user.username}_{file.filename}")
                    file_path = os.path.join(app.config['UPLOAD_FOLDER_LICENSE'], filename)
                    file.save(file_path)
                    
                    # Get form data
                    license_number = request.form.get('license_number')
                    license_type = request.form.get('license_type')
                    expiry_date = request.form.get('expiry_date')
                    
                    if license:
                        # Update existing license
                        license.file_path = filename  # Store only the filename
                        license.upload_date = datetime.utcnow()
                        license.status = 'pending'
                        license.license_number = license_number
                        license.license_type = license_type
                        if expiry_date:
                            license.expiry_date = datetime.strptime(expiry_date, '%Y-%m-%d').date()
                    else:
                        # Create new license
                        license = DriverLicense(
                            driver_username=current_user.username,
                            file_path=filename,  # Store only the filename
                            status='pending',
                            license_number=license_number,
                            license_type=license_type
                        )
                        if expiry_date:
                            license.expiry_date = datetime.strptime(expiry_date, '%Y-%m-%d').date()
                        db.session.add(license)
                    
                    db.session.commit()
                    flash('License updated successfully!', 'success')
                    return redirect(url_for('driver_dashboard'))
                else:
                    flash('Invalid file type. Allowed types: PDF, JPG, JPEG, PNG', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating license: {str(e)}', 'danger')
    
    return render_template('edit_license.html', license=license)

@app.route('/approve-license/<int:id>')
@login_required
def approve_license(id):
    if current_user.role != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    license = DriverLicense.query.get_or_404(id)
    
    try:
        license.status = 'approved'
        
        # Create notification for the driver
        notification = Notification(
            recipient_username=license.driver_username,
            title='License Approved',
            message='Your driver license has been approved by the admin.',
            notification_type='license',
            priority='high'
        )
        db.session.add(notification)
        
        db.session.commit()
        flash('License approved successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error approving license: {str(e)}', 'danger')
    
    return redirect(url_for('manage_licenses'))

@app.route('/reject-license/<int:id>')
@login_required
def reject_license(id):
    if current_user.role != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    license = DriverLicense.query.get_or_404(id)
    
    try:
        license.status = 'rejected'
        
        # Create notification for the driver
        notification = Notification(
            recipient_username=license.driver_username,
            title='License Rejected',
            message='Your driver license has been rejected by the admin. Please upload a valid license.',
            notification_type='license',
            priority='high'
        )
        db.session.add(notification)
        
        db.session.commit()
        flash('License rejected successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error rejecting license: {str(e)}', 'danger')
    
    return redirect(url_for('manage_licenses'))

@app.route('/view-license/<int:id>')
@login_required
def view_license_file(id):
    if current_user.role != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    license = DriverLicense.query.get_or_404(id)
    
    try:
        # Construct the full file path using the stored filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER_LICENSE'], license.file_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError("License file not found")
        
        return send_from_directory(app.config['UPLOAD_FOLDER_LICENSE'], license.file_path, as_attachment=True)
    except Exception as e:
        flash(f'Error viewing license file: {str(e)}', 'danger')
        return redirect(url_for('manage_licenses'))

# View Attendance History
@app.route('/attendance-history')
@login_required
def attendance_history():
    if current_user.role == 'admin':
        return redirect(url_for('view_attendance'))
    
    # For drivers, show their own attendance history
    attendance_records = Attendance.query.filter_by(
        driver_username=current_user.username
    ).order_by(Attendance.date.desc()).all()
    
    return render_template('attendance_history.html', attendance_records=attendance_records)

@app.route('/acknowledge-schedule/<int:id>', methods=['POST'])
@login_required
def acknowledge_schedule(id):
    if current_user.role != 'driver':
        flash('Access denied!', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    schedule = Schedule.query.get_or_404(id)
    
    if schedule.assigned_driver != current_user.username:
        flash('You can only acknowledge your own schedules!', 'danger')
        return redirect(url_for('view_schedules'))
    
    try:
        schedule.driver_acknowledged = True
        schedule.acknowledgment_time = datetime.utcnow()
        schedule.status = 'acknowledged'
        
        # Create notification for admin
        notification = Notification(
            recipient_username='admin',
            title='Schedule Acknowledged',
            message=f'Driver {current_user.username} has acknowledged the schedule for {schedule.date} on route {schedule.route}.',
            notification_type='schedule_update',
            priority='normal'
        )
        db.session.add(notification)
        
        db.session.commit()
        flash('Schedule acknowledged successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error acknowledging schedule: {str(e)}', 'danger')
    
    return redirect(url_for('view_schedules'))

@app.route('/update-driver-names')
@login_required
def update_driver_names():
    if current_user.role != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('driver_dashboard'))
    
    # Dictionary mapping old usernames to new names
    driver_updates = {
        'driver1': 'Sarvesh',
        'driver2': 'Karthick',
        'driver3': 'Saravanan',
        'driver4': 'Ram',
        'driver5': 'Arun',
        'driver6': 'Sankar',
        'driver7': 'Santhosh',
        'driver8': 'Rajkumar',
        'driver9': 'Praveen',
        'driver10': 'Kishore',
        'driver11': 'Shiva'
    }
    
    try:
        for username, new_name in driver_updates.items():
            driver = User.query.filter_by(username=username).first()
            if driver:
                driver.full_name = new_name
                driver.email = f"{new_name.lower()}@example.com"
        
        db.session.commit()
        flash('Driver names updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating driver names: {str(e)}', 'danger')
    
    return redirect(url_for('view_drivers'))

if __name__ == '__main__':
    app.run(debug=True)