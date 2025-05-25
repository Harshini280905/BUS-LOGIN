from app import app, db
import sqlite3

def migrate_database():
    with app.app_context():
        # Connect to the database
        conn = sqlite3.connect('instance/bus_schedule.db')
        cursor = conn.cursor()
        
        try:
            # Add start_date column
            cursor.execute('ALTER TABLE performance_metric ADD COLUMN start_date DATE')
            print("Successfully added start_date column to performance_metric table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print("start_date column already exists")
            else:
                raise e
        
        try:
            # Add end_date column
            cursor.execute('ALTER TABLE performance_metric ADD COLUMN end_date DATE')
            print("Successfully added end_date column to performance_metric table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print("end_date column already exists")
            else:
                raise e
        
        # Commit changes and close connection
        conn.commit()
        conn.close()

if __name__ == '__main__':
    migrate_database() 