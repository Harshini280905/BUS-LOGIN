from app import app, db, User
from flask import Flask

def update_driver_names():
    with app.app_context():
        # Dictionary mapping usernames to new names
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
            # First, get all drivers and sort them by ID
            drivers = User.query.filter(User.username.like('driver%')).order_by(User.id).all()
            
            # Update each driver's username and name
            for i, driver in enumerate(drivers, 1):
                if i <= 11:  # Only process first 11 drivers
                    new_username = f'driver{i}'
                    new_name = driver_updates[new_username]
                    print(f"Updating driver ID {driver.id} from {driver.username} to {new_username} ({new_name})")
                    driver.username = new_username
                    driver.full_name = new_name
                    driver.email = f"{new_name.lower()}@example.com"
            
            db.session.commit()
            print("Driver names and IDs updated successfully!")
        except Exception as e:
            db.session.rollback()
            print(f"Error updating driver names: {str(e)}")

if __name__ == '__main__':
    update_driver_names() 