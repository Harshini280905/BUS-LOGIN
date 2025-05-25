import sqlite3
from datetime import datetime

def migrate_incident_severity():
    # Connect to the database
    conn = sqlite3.connect('instance/bus_schedule.db')
    cursor = conn.cursor()
    
    try:
        # First, create a temporary table with the new structure
        cursor.execute('''
            CREATE TABLE incident_temp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_username VARCHAR(80) NOT NULL,
                date DATE NOT NULL,
                start_date DATE,
                end_date DATE,
                incident_type VARCHAR(50) NOT NULL,
                description TEXT NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'open',
                reported_by VARCHAR(80) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (driver_username) REFERENCES user (username),
                FOREIGN KEY (reported_by) REFERENCES user (username)
            )
        ''')
        
        # Copy data from old table to new table
        cursor.execute('''
            INSERT INTO incident_temp (
                id, driver_username, date, start_date, end_date,
                incident_type, description, status, reported_by,
                created_at, updated_at
            )
            SELECT 
                id, driver_username, date, start_date, end_date,
                incident_type, description, status, reported_by,
                created_at, updated_at
            FROM incident
        ''')
        
        # Drop the old table
        cursor.execute('DROP TABLE incident')
        
        # Rename the new table to the original name
        cursor.execute('ALTER TABLE incident_temp RENAME TO incident')
        
        conn.commit()
        print("Successfully updated incident table structure")
        
    except sqlite3.OperationalError as e:
        print(f"Error: {e}")
        conn.rollback()
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_incident_severity() 