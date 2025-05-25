import sqlite3
from datetime import datetime

def migrate_bus_management():
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect('instance/bus_schedule.db')
        cursor = conn.cursor()
        
        # Add bus_number column to bus_management table
        cursor.execute('''
            ALTER TABLE bus_management 
            ADD COLUMN bus_number VARCHAR(20)
        ''')
        
        # Commit the changes
        conn.commit()
        print("Successfully added bus_number column to bus_management table")
        
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("Column bus_number already exists")
        else:
            print(f"Error: {str(e)}")
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_bus_management() 