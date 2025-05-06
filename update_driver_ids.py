from app import app, db, User
from flask import Flask
from sqlalchemy import text

def update_driver_ids():
    with app.app_context():
        try:
            # Get all drivers sorted by ID in descending order
            # We update from highest to lowest to avoid conflicts
            drivers = User.query.filter(
                User.username.like('driver%')
            ).order_by(User.id.desc()).all()
            
            print("Current driver IDs:")
            for driver in drivers:
                print(f"Driver {driver.username}: ID {driver.id}")
            
            print("\nUpdating IDs...")
            # Update each driver's ID (subtract 1)
            for driver in drivers:
                new_id = driver.id - 1
                if 1 <= new_id <= 11:
                    print(f"Updating {driver.username} from ID {driver.id} to {new_id}")
                    db.session.execute(text(
                        "UPDATE user SET id = :new_id WHERE id = :old_id"
                    ), {'new_id': new_id, 'old_id': driver.id})
            
            db.session.commit()
            print("\nUpdate completed!")
            
            # Verify the changes
            print("\nNew driver IDs:")
            drivers = User.query.filter(
                User.username.like('driver%')
            ).order_by(User.id).all()
            for driver in drivers:
                print(f"Driver {driver.username}: ID {driver.id}")
                
        except Exception as e:
            db.session.rollback()
            print(f"Error updating driver IDs: {str(e)}")
            if hasattr(e, 'orig'):
                print("Original error:", e.orig)

if __name__ == '__main__':
    update_driver_ids() 