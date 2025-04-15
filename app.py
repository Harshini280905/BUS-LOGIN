from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, make_response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, time, date, timedelta
from werkzeug.utils import secure_filename
import os
from functools import wraps
from sqlalchemy import or_, and_

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bus_schedule.db'
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'static/profile_pics'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER_LICENSE'] = 'static/uploads/licenses'
db = SQLAlchemy(app)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER_LICENSE'], exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

# Database Models
class User(db.Model):
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
    start_time = db.Column(db.String(50), nullable=False)
    end_time = db.Column(db.String(50), nullable=False)
    route = db.Column(db.String(100), nullable=False)
    bus_number = db.Column(db.String(20), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    assigned_driver = db.Column(db.String(100), nullable=False)
    is_peak_hour = db.Column(db.Boolean, default=False)
    schedule_type = db.Column(db.String(20), default='regular')  # regular, special, emergency
    created_by = db.Column(db.String(150), db.ForeignKey('user.username'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_modified = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='scheduled')  # scheduled, in_progress, completed, cancelled

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
    driver_username = db.Column(db.String(150), db.ForeignKey('user.username'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    check_in = db.Column(db.DateTime)
    check_out = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='pending')  # pending, present, absent, on_leave
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)

class BreakPeriod(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    driver_username = db.Column(db.String(150), db.ForeignKey('user.username'), nullable=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime)
    break_type = db.Column(db.String(50), nullable=False)  # rest, lunch, emergency
    status = db.Column(db.String(20), default='scheduled')  # scheduled, ongoing, completed

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipient_username = db.Column(db.String(150), db.ForeignKey('user.username'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)  # schedule_update, emergency, announcement
    priority = db.Column(db.String(20), default='normal')  # normal, high, urgent
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
    db.drop_all()  # This will reset the database - be careful with this in production!
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
    
    # Add test drivers if they don't exist
    test_drivers = [
        {
            'username': 'driver1',
            'password': 'driver123',
            'full_name': 'John Driver',
            'email': 'john@bus.com',
            'phone': '1234567891',
            'address': '123 Driver St',
            'emergency_contact': '555-0001'
        },
        {
            'username': 'driver2',
            'password': 'driver123',
            'full_name': 'Jane Driver',
            'email': 'jane@bus.com',
            'phone': '1234567892',
            'address': '456 Driver Ave',
            'emergency_contact': '555-0002'
        }
    ]
    
    for driver_data in test_drivers:
        driver = User.query.filter_by(username=driver_data['username']).first()
        if not driver:
            driver = User(
                username=driver_data['username'],
                password=generate_password_hash(driver_data['password']),
                role='driver',
                full_name=driver_data['full_name'],
                email=driver_data['email'],
                phone=driver_data['phone'],
                address=driver_data['address'],
                emergency_contact=driver_data['emergency_contact']
            )
            db.session.add(driver)
    
    db.session.commit()

def check_schedule_conflict(driver, start_time, end_time, exclude_id=None):
    """Check if a driver has any schedule conflicts"""
    start_time_obj = datetime.strptime(start_time, '%H:%M').time()
    end_time_obj = datetime.strptime(end_time, '%H:%M').time()
    
    # Get all schedules for the driver
    query = Schedule.query.filter_by(assigned_driver=driver)
    if exclude_id:
        query = query.filter(Schedule.id != exclude_id)
    schedules = query.all()
    
    for schedule in schedules:
        existing_start = datetime.strptime(schedule.start_time, '%H:%M').time()
        existing_end = datetime.strptime(schedule.end_time, '%H:%M').time()
        
        # Check for any overlap between time ranges
        if (
            (start_time_obj >= existing_start and start_time_obj < existing_end) or  # New start time falls within existing schedule
            (end_time_obj > existing_start and end_time_obj <= existing_end) or      # New end time falls within existing schedule
            (start_time_obj <= existing_start and end_time_obj >= existing_end)      # New schedule completely encompasses existing schedule
        ):
            return True, f"Schedule conflict: Driver {driver} already has a schedule from {existing_start.strftime('%H:%M')} to {existing_end.strftime('%H:%M')}"
    
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
    """Check if a route is already assigned to another driver at the same time"""
    query = Schedule.query.filter_by(route=route)
    if exclude_id:
        query = query.filter(Schedule.id != exclude_id)
    
    schedules = query.all()
    start_time_obj = datetime.strptime(start_time, '%H:%M').time()
    end_time_obj = datetime.strptime(end_time, '%H:%M').time()
    
    for schedule in schedules:
        existing_start = datetime.strptime(schedule.start_time, '%H:%M').time()
        existing_end = datetime.strptime(schedule.end_time, '%H:%M').time()
        
        if (start_time_obj <= existing_end and end_time_obj >= existing_start):
            return True, f"Route conflict: Route {route} is already assigned to driver {schedule.assigned_driver} from {existing_start.strftime('%H:%M')} to {existing_end.strftime('%H:%M')}"
    
    return False, None

# Home Page
@app.route('/')
def index():
    return redirect(url_for('login'))

# User Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            session['user_id'] = user.id
            session['role'] = user.role
            session['username'] = user.username
            flash('Login Successful!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password!', 'danger')
        return redirect(url_for('login'))
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

# Admin Dashboard
@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    pending_leaves = get_pending_leave_count()
    pending_notifications = get_pending_notifications(session['username'])
    return render_template('admin_dashboard.html', pending_leaves=pending_leaves, pending_notifications=pending_notifications)

# Driver Dashboard
@app.route('/driver_dashboard')
def driver_dashboard():
    if 'user_id' not in session or session['role'] != 'driver':
        return redirect(url_for('login'))
    pending_leaves = get_driver_pending_leaves(session['username'])
    pending_notifications = get_pending_notifications(session['username'])
    return render_template('driver_dashboard.html', pending_leaves=pending_leaves, pending_notifications=pending_notifications)

# View Schedules
@app.route('/view_schedules')
def view_schedules():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if session['role'] == 'admin':
        schedules = Schedule.query.all()
    else:
        # For drivers, only show their assigned schedules
        schedules = Schedule.query.filter_by(assigned_driver=session['username']).all()
    
    return render_template('view_schedules.html', schedules=schedules)

# Create Schedule with enhanced conflict checking
@app.route('/add', methods=['GET', 'POST'])
def add_schedule():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        start_time = request.form['start_time']
        end_time = request.form['end_time']
        route = request.form['route']
        driver = request.form['assigned_driver']
        
        # Check for schedule conflict
        has_conflict, message = check_schedule_conflict(driver, start_time, end_time)
        if has_conflict:
            flash(message, 'danger')
            return redirect(url_for('add_schedule'))
        
        # Check for route conflict
        has_route_conflict, route_message = check_route_conflict(route, start_time, end_time)
        if has_route_conflict:
            flash(route_message, 'danger')
            return redirect(url_for('add_schedule'))
        
        # Check for approved leave conflicts
        leaves = LeaveRequest.query.filter_by(
            driver_username=driver,
            status='approved'
        ).all()
        
        for leave in leaves:
            if (start_time >= leave.start_time and start_time <= leave.end_time) or \
               (end_time >= leave.start_time and end_time <= leave.end_time):
                flash(f'Cannot assign schedule: Driver has approved leave during this time.', 'danger')
                return redirect(url_for('add_schedule'))
        
        new_schedule = Schedule(
            start_time=start_time,
            end_time=end_time,
            route=route,
            bus_number=request.form['bus_number'],
            capacity=request.form['capacity'],
            assigned_driver=driver
        )
        db.session.add(new_schedule)
        db.session.commit()
        flash('Schedule Created Successfully!', 'success')
        return redirect(url_for('view_schedules'))
    
    return render_template('add_schedule.html')

# Edit Schedule
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_schedule(id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    schedule = Schedule.query.get(id)
    if request.method == 'POST':
        # Check for driver schedule conflict
        existing_schedule = Schedule.query.filter(
            Schedule.assigned_driver == request.form['assigned_driver'],
            Schedule.start_time == request.form['start_time'],
            Schedule.route == request.form['route'],
            Schedule.id != id
        ).first()
        
        if existing_schedule:
            flash('Error: This driver is already assigned to the same route at the same time!', 'danger')
            return redirect(url_for('edit_schedule', id=id))
            
        schedule.start_time = request.form['start_time']
        schedule.end_time = request.form['end_time']
        schedule.route = request.form['route']
        schedule.bus_number = request.form['bus_number']
        schedule.capacity = request.form['capacity']
        schedule.assigned_driver = request.form['assigned_driver']
        db.session.commit()
        flash('Schedule Updated Successfully!', 'info')
        return redirect(url_for('view_schedules'))
    return render_template('edit_schedule.html', schedule=schedule)

# Delete Schedule
@app.route('/delete/<int:id>')
def delete_schedule(id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    schedule = Schedule.query.get(id)
    db.session.delete(schedule)
    db.session.commit()
    flash('Schedule Deleted!', 'danger')
    return redirect(url_for('view_schedules'))

# Apply for Leave
@app.route('/apply-leave', methods=['GET', 'POST'])
def apply_leave():
    if 'user_id' not in session or session['role'] != 'driver':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        new_leave = LeaveRequest(
            driver_username=session['username'],
            date=request.form['date'],
            start_time=request.form['start_time'],
            end_time=request.form['end_time'],
            reason=request.form['reason']
        )
        db.session.add(new_leave)
        db.session.commit()
        flash('Leave request submitted successfully!', 'success')
        return redirect(url_for('driver_dashboard'))
    
    return render_template('apply_leave.html')

# Manage Leave Requests
@app.route('/manage-leaves')
def manage_leaves():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    leave_requests = LeaveRequest.query.order_by(LeaveRequest.created_at.desc()).all()
    return render_template('manage_leaves.html', leave_requests=leave_requests)

# Handle Leave Request with Response
@app.route('/handle-leave/<int:id>/<string:action>', methods=['POST'])
def handle_leave(id, action):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    leave_request = LeaveRequest.query.get_or_404(id)
    response = request.form.get('response', '')
    
    if action in ['approve', 'reject']:
        if action == 'approve':
            # Check for schedule conflicts
            schedules = Schedule.query.filter_by(assigned_driver=leave_request.driver_username).all()
            for schedule in schedules:
                if schedule.start_time <= leave_request.end_time and schedule.end_time >= leave_request.start_time:
                    flash('Cannot approve leave: Driver has scheduled routes during this time.', 'danger')
                    return redirect(url_for('manage_leaves'))
        
        leave_request.status = 'approved' if action == 'approve' else 'rejected'
        leave_request.admin_response = response
        leave_request.response_time = datetime.utcnow()
        db.session.commit()
        flash(f'Leave request {action}d successfully!', 'success')
    
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
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    return render_template('profile.html', user=user)

@app.route('/view-drivers')
def view_drivers():
    if 'user_id' not in session or session['role'] != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('login'))
    
    drivers = User.query.filter_by(role='driver').all()
    return render_template('view_drivers.html', drivers=drivers)

@app.route('/update-profile', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    
    try:
        user.full_name = request.form.get('full_name')
        if request.form.get('dob'):
            user.dob = datetime.strptime(request.form.get('dob'), '%Y-%m-%d').date()
        user.phone = request.form.get('phone')
        user.email = request.form.get('email')
        user.address = request.form.get('address')
        
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename != '':
                filename = secure_filename(f"{user.username}_{file.filename}")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                user.profile_pic = filename
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating profile: {str(e)}', 'danger')
    
    return redirect(url_for('profile'))
@app.route('/settings')
def settings():
    return render_template('settings.html')


# View My Leave Requests (for drivers)
@app.route('/my-leaves')
def my_leaves():
    if 'user_id' not in session or session['role'] != 'driver':
        return redirect(url_for('login'))
    
    leaves = LeaveRequest.query.filter_by(
        driver_username=session['username']
    ).order_by(LeaveRequest.created_at.desc()).all()
    
    return render_template('my_leaves.html', leaves=leaves)

# Logout
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    session.pop('username', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload-license', methods=['GET', 'POST'])
def upload_license():
    if 'user_id' not in session or session['role'] != 'driver':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        if 'license' not in request.files:
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        file = request.files['license']
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{session['username']}_{file.filename}")
            if not os.path.exists(app.config['UPLOAD_FOLDER_LICENSE']):
                os.makedirs(app.config['UPLOAD_FOLDER_LICENSE'])
            
            file_path = os.path.join(app.config['UPLOAD_FOLDER_LICENSE'], filename)
            file.save(file_path)
            
            # Save to database
            license_entry = DriverLicense(
                driver_username=session['username'],
                file_path=file_path
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
def request_shift_swap():
    if 'user_id' not in session or session['role'] != 'driver':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        schedule_id = request.form.get('schedule_id')
        reason = request.form.get('reason')
        target_driver = request.form.get('target_driver')
        
        # Create shift swap request
        swap_request = ShiftSwap(
            requesting_driver=session['username'],
            target_driver=target_driver,
            schedule_id=schedule_id,
            reason=reason
        )
        db.session.add(swap_request)
        db.session.commit()
        
        # Create notification for target driver
        notification = Notification(
            recipient_username=target_driver,
            title='New Shift Swap Request',
            message=f'Driver {session["username"]} has requested to swap their shift with you.',
            notification_type='schedule_update',
            priority='normal'
        )
        db.session.add(notification)
        db.session.commit()
        
        flash('Shift swap request submitted successfully!', 'success')
        return redirect(url_for('driver_dashboard'))
    
    # Get available drivers and schedules for the form
    available_drivers = User.query.filter_by(role='driver').filter(User.username != session['username']).all()
    driver_schedules = Schedule.query.filter_by(assigned_driver=session['username']).all()
    
    return render_template('request_shift_swap.html', 
                         available_drivers=available_drivers,
                         schedules=driver_schedules)

@app.route('/manage-shift-swaps')
def manage_shift_swaps():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    swap_requests = ShiftSwap.query.order_by(ShiftSwap.created_at.desc()).all()
    return render_template('manage_shift_swaps.html', swap_requests=swap_requests)

@app.route('/handle-shift-swap/<int:id>/<string:action>', methods=['POST'])
def handle_shift_swap(id, action):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    swap_request = ShiftSwap.query.get_or_404(id)
    response = request.form.get('response', '')
    
    if action in ['approve', 'reject']:
        if action == 'approve':
            # Update schedule assignment
            schedule = Schedule.query.get(swap_request.schedule_id)
            old_driver = schedule.assigned_driver
            schedule.assigned_driver = swap_request.target_driver
            
            # Create notifications for both drivers
            notification1 = Notification(
                recipient_username=swap_request.requesting_driver,
                title='Shift Swap Approved',
                message=f'Your shift swap request has been approved.',
                notification_type='schedule_update',
                priority='high'
            )
            notification2 = Notification(
                recipient_username=swap_request.target_driver,
                title='Shift Swap Approved',
                message=f'You have been assigned to a new shift through a swap.',
                notification_type='schedule_update',
                priority='high'
            )
            db.session.add(notification1)
            db.session.add(notification2)
        
        swap_request.status = 'approved' if action == 'approve' else 'rejected'
        swap_request.admin_response = response
        swap_request.response_time = datetime.utcnow()
        db.session.commit()
        
        flash(f'Shift swap request {action}d successfully!', 'success')
    
    return redirect(url_for('manage_shift_swaps'))

# Break Period Management Routes
@app.route('/manage-breaks', methods=['GET', 'POST'])
def manage_breaks():
    if 'user_id' not in session or session['role'] != 'driver':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        schedule_id = request.form.get('schedule_id')
        break_type = request.form.get('break_type')
        start_time = datetime.strptime(request.form.get('start_time'), '%Y-%m-%d %H:%M')
        
        # Create break period
        break_period = BreakPeriod(
            driver_username=session['username'],
            schedule_id=schedule_id,
            start_time=start_time,
            break_type=break_type
        )
        db.session.add(break_period)
        db.session.commit()
        
        flash('Break period scheduled successfully!', 'success')
        return redirect(url_for('manage_breaks'))
    
    # Get driver's schedules and existing breaks
    schedules = Schedule.query.filter_by(assigned_driver=session['username']).all()
    breaks = BreakPeriod.query.filter_by(driver_username=session['username']).all()
    
    return render_template('manage_breaks.html', 
                         schedules=schedules,
                         breaks=breaks)

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
def notifications():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    is_admin = session.get('is_admin', False)
    notifications = Notification.query.filter_by(
        recipient_username=session['username'],
        is_read=False
    ).order_by(Notification.created_at.desc()).all()
    
    return render_template('notifications.html', notifications=notifications, is_admin=is_admin)

@app.route('/mark-notification-read/<int:notification_id>')
def mark_notification_read(notification_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    notification = Notification.query.get_or_404(notification_id)
    if notification.recipient_username != session['username']:
        flash('Unauthorized access!', 'danger')
        return redirect(url_for('notifications'))
    
    notification.is_read = True
    notification.read_at = datetime.utcnow()
    db.session.commit()
    
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
def manage_licenses():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    licenses = DriverLicense.query.all()
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

# View Attendance Record
@app.route('/view_attendance')
def view_attendance():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if session['role'] == 'admin':
        attendance = Attendance.query.all()
    else:
        attendance = Attendance.query.filter_by(driver_username=session['username']).all()
    
    return render_template('view_attendance.html', attendance=attendance)

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
    schedule_date = request.form.get('schedule_date')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    bus_number = request.form.get('bus_number')
    
    # Validate driver availability
    driver = User.query.get(driver_id)
    if not driver:
        flash('Invalid driver selected.', 'danger')
        return redirect(url_for('manage_assignments'))
    
    # Check for leave conflicts
    leave_conflict = LeaveRequest.query.filter(
        LeaveRequest.driver_username == driver.username,
        LeaveRequest.status == 'approved',
        LeaveRequest.start_date <= schedule_date,
        LeaveRequest.end_date >= schedule_date
    ).first()
    
    if leave_conflict:
        flash('Driver is on approved leave for the selected date.', 'danger')
        return redirect(url_for('manage_assignments'))
    
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
        flash('Driver already has an assignment during this time period.', 'danger')
        return redirect(url_for('manage_assignments'))
    
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
    
    db.session.add(assignment)
    db.session.commit()
    
    # Create notification for driver
    notification = Notification(
        recipient_username=driver.username,
        title='New Bus Assignment',
        message=f'You have been assigned bus {bus_number} on {schedule_date} from {start_time} to {end_time}.',
        notification_type='schedule_update',
        priority='high'
    )
    db.session.add(notification)
    db.session.commit()
    
    flash('Bus assignment created successfully!', 'success')
    return redirect(url_for('manage_assignments'))

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

if __name__ == '__main__':
    app.run(debug=True)