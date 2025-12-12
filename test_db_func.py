import sys
import os

# Add current directory to sys.path
sys.path.append(os.getcwd())

try:
    from db_handler import get_last_active_strategy_id
    print("Import successful")
    id = get_last_active_strategy_id()
    print(f"Last ID: {id}")
except Exception as e:
    print(f"Error: {e}")
