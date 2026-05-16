import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "parking.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS parking_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_number TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT,
            duration_minutes INTEGER,
            fee REAL,
            status TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def find_active_record(plate_number: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM parking_records
        WHERE plate_number = ? AND status = 'in'
        ORDER BY id DESC
        LIMIT 1
        """,
        (plate_number,),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def create_entry_record(plate_number: str, entry_time: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO parking_records (plate_number, entry_time, status)
        VALUES (?, ?, 'in')
        """,
        (plate_number, entry_time),
    )
    conn.commit()
    conn.close()


def finish_exit_record(record_id: int, exit_time: str, duration_minutes: int, fee: float):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE parking_records
        SET exit_time = ?, duration_minutes = ?, fee = ?, status = 'out'
        WHERE id = ?
        """,
        (exit_time, duration_minutes, fee, record_id),
    )
    conn.commit()
    conn.close()

def list_all_records():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM parking_records
        ORDER BY id DESC
        """
    )
    rows = cursor.fetchall()
    conn.close()
    return rows

def init_settings():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS parking_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            total_spaces INTEGER NOT NULL,
            available_spaces INTEGER NOT NULL,
            hourly_rate REAL NOT NULL DEFAULT 6
        )
        """
    )

    cursor.execute("PRAGMA table_info(parking_settings)")
    columns = [row[1] for row in cursor.fetchall()]

    if "hourly_rate" not in columns:
        cursor.execute(
            """
            ALTER TABLE parking_settings
            ADD COLUMN hourly_rate REAL NOT NULL DEFAULT 6
            """
        )

    cursor.execute("SELECT COUNT(*) FROM parking_settings")
    count = cursor.fetchone()[0]

    if count == 0:
        cursor.execute(
            """
            INSERT INTO parking_settings (id, total_spaces, available_spaces, hourly_rate)
            VALUES (1, 20, 20, 6)
            """
        )

    conn.commit()
    conn.close()


def get_space_status():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT total_spaces, available_spaces, hourly_rate
        FROM parking_settings
        WHERE id = 1
        """
    )
    row = cursor.fetchone()
    conn.close()
    return row


def occupy_one_space():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE parking_settings
        SET available_spaces = available_spaces - 1
        WHERE id = 1 AND available_spaces > 0
        """
    )
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected

def release_one_space():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE parking_settings
        SET available_spaces = CASE
            WHEN available_spaces < total_spaces THEN available_spaces + 1
            ELSE total_spaces
        END
        WHERE id = 1
        """
    )
    conn.commit()
    conn.close()

def update_total_spaces(total_spaces: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT total_spaces, available_spaces
        FROM parking_settings
        WHERE id = 1
        """
    )
    row = cursor.fetchone()

    current_total = row["total_spaces"]
    current_available = row["available_spaces"]
    occupied = current_total - current_available

    new_available = total_spaces - occupied
    if new_available < 0:
        new_available = 0

    cursor.execute(
        """
        UPDATE parking_settings
        SET total_spaces = ?, available_spaces = ?
        WHERE id = 1
        """,
        (total_spaces, new_available),
    )

    conn.commit()
    conn.close()

def get_dashboard_stats():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS total_records FROM parking_records")
    total_records = cursor.fetchone()["total_records"]

    cursor.execute("SELECT COUNT(*) AS cars_in_lot FROM parking_records WHERE status = 'in'")
    cars_in_lot = cursor.fetchone()["cars_in_lot"]

    cursor.execute("SELECT COUNT(*) AS completed_exits FROM parking_records WHERE status = 'out'")
    completed_exits = cursor.fetchone()["completed_exits"]

    cursor.execute("SELECT COALESCE(SUM(fee), 0) AS total_revenue FROM parking_records WHERE status = 'out'")
    total_revenue = cursor.fetchone()["total_revenue"]

    conn.close()

    return {
        "total_records": total_records,
        "cars_in_lot": cars_in_lot,
        "completed_exits": completed_exits,
        "total_revenue": float(total_revenue),
    }

def update_hourly_rate(hourly_rate: float):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE parking_settings
        SET hourly_rate = ?
        WHERE id = 1
        """,
        (hourly_rate,),
    )
    conn.commit()
    conn.close()





