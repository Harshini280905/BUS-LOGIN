class ShiftSwapRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    requesting_driver = db.Column(db.String(100), db.ForeignKey('user.username'), nullable=False)
    target_driver = db.Column(db.String(100), db.ForeignKey('user.username'), nullable=False)
    your_shift_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    target_shift_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    swap_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    admin_response = db.Column(db.Text)

    # Relationships
    requesting_driver_rel = db.relationship('User', foreign_keys=[requesting_driver], backref='requested_swaps')
    target_driver_rel = db.relationship('User', foreign_keys=[target_driver], backref='targeted_swaps')
    your_shift = db.relationship('Schedule', foreign_keys=[your_shift_id])
    target_shift = db.relationship('Schedule', foreign_keys=[target_shift_id]) 