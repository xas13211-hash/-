import sys
import os

# Add current directory to sys.path to allow imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db_handler import init_db, get_db_connection

def verify():
    print("Checking PostgreSQL connection...")
    try:
        conn = get_db_connection()
        conn.close()
        print("✅ Connection successful!")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("Please check your configuration in config.py and ensure PostgreSQL is running.")
        return

    print("\nInitializing database tables...")
    try:
        init_db()
        print("✅ Database initialized successfully!")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")

if __name__ == "__main__":
    verify()
