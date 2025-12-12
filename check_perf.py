import psycopg2
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

try:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, total_return FROM strategy_perf")
    rows = cursor.fetchall()
    print(f"Rows in strategy_perf: {len(rows)}")
    for row in rows:
        print(row)
    conn.close()
except Exception as e:
    print(e)
