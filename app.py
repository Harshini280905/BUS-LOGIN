from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, time
from werkzeug.utils import secure_filename
import os
from functools import wraps

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

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.String(50), nullable=False)
    end_time = db.Column(db.String(50), nullable=False)
    route = db.Column(db.String(100), nullable=False)
    bus_number = db.Column(db.String(20), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    assigned_driver = db.Column(db.String(100), nullable=False)

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
            phone='1234567890'
        )
        db.session.add(admin)
    
    # Add 10 drivers if they don't exist
    for i in range(1, 11):
        driver = User.query.filter_by(username=f'driver{i}').first()
        if not driver:
            driver = User(
                username=f'driver{i}',
                password=generate_password_hash(f'driver{i}'),
                role='driver',
                full_name=f'Driver {i}',
                email=f'driver{i}@busschedule.com',
                phone=f'123456789{i}'
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
    return render_template('admin_dashboard.html', pending_leaves=pending_leaves)

# Driver Dashboard
@app.route('/driver_dashboard')
def driver_dashboard():
    if 'user_id' not in session or session['role'] != 'driver':
        return redirect(url_for('login'))
    pending_leaves = get_driver_pending_leaves(session['username'])
    return render_template('driver_dashboard.html', pending_leaves=pending_leaves)

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

if __name__ == '__main__':
    app.run(debug=True)