import sqlite3
from datetime import datetime

def migrate_incidents():
    try:
        # Connect to the database
        conn = sqlite3.connect('instance/bus_schedule.db')
        cursor = conn.cursor()

        # Add new columns
        cursor.execute('ALTER TABLE incident ADD COLUMN start_date DATE')
        cursor.execute('ALTER TABLE incident ADD COLUMN end_date DATE')
        
        # Update existing records to have current date as start_date and end_date
        cursor.execute('''
            UPDATE incident 
            SET start_date = date, 
                end_date = date 
            WHERE start_date IS NULL 
            AND end_date IS NULL
        ''')

        # Commit changes
        conn.commit()
        print("Successfully added start_date and end_date columns to incident table")

    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("Columns already exist, skipping migration")
        else:
            print(f"Error during migration: {str(e)}")
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_incidents() 