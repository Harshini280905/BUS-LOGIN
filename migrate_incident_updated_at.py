import sqlite3
from datetime import datetime

def migrate_incident_updated_at():
    # Connect to the database
    conn = sqlite3.connect('instance/bus_schedule.db')
    cursor = conn.cursor()
    
    try:
        # Add updated_at column
        cursor.execute('''
            ALTER TABLE incident 
            ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ''')
        
        # Update existing records to set updated_at to created_at
        cursor.execute('''
            UPDATE incident 
            SET updated_at = created_at 
            WHERE updated_at IS NULL
        ''')
        
        conn.commit()
        print("Successfully added updated_at column to incident table")
        
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("Column updated_at already exists")
        else:
            print(f"Error: {e}")
        conn.rollback()
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_incident_updated_at() 