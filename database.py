"""
database.py
Handles all SQLite persistence for the University Facilities Booking App.
Also contains the 'manager' classes that implement the business logic for
each module described in the assignment brief:

    a. Room Reservation Management        -> BookingManager (category='Room')
    b. Sports & Recreation Booking Mgmt    -> BookingManager (category='Sports')
    c. Equipment Booking Management        -> BookingManager (category='Equipment')
    d. Facility & Resource Management      -> FacilityManager
    e. Facility Usage & Maintenance Mgmt   -> UsageManager, MaintenanceManager
"""

import re
import sqlite3
import hashlib
import secrets
from datetime import datetime, date, timedelta

DB_NAME = "facility_booking.db"

# Student ID card format: 2 digits + 3 capital letters + 5 digits, e.g. 23WMR12345
STUDENT_ID_RE = re.compile(r"^\d{2}[A-Z]{3}\d{5}$")
# Card expiry date as printed on the card: DD-MM-YYYY
EXPIRY_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
# Barcode number printed under the barcode: digits only
BARCODE_NUMBER_RE = re.compile(r"^\d{6,14}$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


# --------------------------------------------------------------------------
# DATABASE LAYER
# --------------------------------------------------------------------------
class Database:
    """Thin wrapper around a single SQLite connection shared by the app."""

    def __init__(self, db_name: str = DB_NAME):
        self.conn = sqlite3.connect(db_name)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()
        self._migrate_users_table()
        self._migrate_facilities_table()
        self._migrate_admins_table()
        self._seed_data()

    # ---- schema -----------------------------------------------------
    def _migrate_users_table(self):
        """
        Adds the student-ID-card columns to a `users` table created by an
        older version of this app (before card scanning existed), so
        upgrading doesn't require deleting the existing database file.
        """
        cur = self.conn.cursor()
        existing_cols = {row["name"] for row in cur.execute("PRAGMA table_info(users)").fetchall()}
        for col in ("student_id", "expiry_date", "barcode_number",
                    "password_hash", "salt", "profile_picture"):
            if col not in existing_cols:
                cur.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
        self.conn.commit()
        # Non-unique index (SQLite can't add a UNIQUE constraint via ALTER
        # TABLE); uniqueness for a filled-in student_id is instead enforced
        # in UserManager.add_user/update_user before the write happens.
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_student_id ON users(student_id)")
        self.conn.commit()

    def _migrate_facilities_table(self):
        cur = self.conn.cursor()
        existing_cols = {row["name"] for row in cur.execute("PRAGMA table_info(facilities)").fetchall()}
        if "image_path" not in existing_cols:
            cur.execute("ALTER TABLE facilities ADD COLUMN image_path TEXT")
        self.conn.commit()

    def _migrate_admins_table(self):
        """Adds a profile-picture column to `admins` so staff accounts can
        have an avatar too, same as student/user records."""
        cur = self.conn.cursor()
        existing_cols = {row["name"] for row in cur.execute("PRAGMA table_info(admins)").fetchall()}
        if "profile_picture" not in existing_cols:
            cur.execute("ALTER TABLE admins ADD COLUMN profile_picture TEXT")
        self.conn.commit()

    def _create_tables(self):
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('Student','Faculty','Staff','Admin')),
                email TEXT NOT NULL,
                student_id TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                barcode_number TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS facilities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL CHECK(category IN ('Room','Sports','Equipment')),
                type TEXT NOT NULL,
                capacity INTEGER NOT NULL DEFAULT 0,
                location TEXT NOT NULL,
                condition TEXT NOT NULL DEFAULT 'Good'
                    CHECK(condition IN ('Good','Fair','Under Maintenance','Out of Service')),
                status TEXT NOT NULL DEFAULT 'Available'
                    CHECK(status IN ('Available','Booked','Maintenance')),
                image_path TEXT
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                facility_id INTEGER NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                booking_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                purpose TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending'
                    CHECK(status IN ('Pending','Approved','Cancelled','Completed')),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS maintenance_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                facility_id INTEGER NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
                log_date TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Reported'
                    CHECK(status IN ('Reported','In Progress','Resolved')),
                reported_by TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                facility_id INTEGER NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
                booking_id INTEGER REFERENCES bookings(id) ON DELETE SET NULL,
                check_in TEXT,
                check_out TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    # ---- demo seed data ----------------------------------------------
    def _seed_data(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM users")
        if cur.fetchone()["c"] == 0:
            cur.executemany(
                "INSERT INTO users (name, role, email, student_id, expiry_date, barcode_number) "
                "VALUES (?,?,?,?,?,?)",
                [
                    ("Leo Tan", "Student", "leo@uni.edu", "23WMR12345", "31-12-2026", "100001"),
                    ("Dr. Aisha Rahman", "Faculty", "aisha@uni.edu", "24FAC12345", "31-12-2026", "100002"),
                    ("Facilities Office", "Admin", "facilities@uni.edu", "24ADM12345", "31-12-2026", "100003"),
                ],
            )
        cur.execute("SELECT COUNT(*) AS c FROM facilities")
        if cur.fetchone()["c"] == 0:
            cur.executemany(
                "INSERT INTO facilities (name, category, type, capacity, location, condition, status, image_path) "
                "VALUES (?,?,?,?,?,?,?,?)",
                [
                    ("LR-101", "Room", "Lecture Hall", 120, "Block A", "Good", "Available", None),
                    ("Classroom 3B", "Room", "Classroom", 40, "Block B", "Good", "Available", None),
                    ("Comp Lab 2", "Room", "Lab", 30, "Block C", "Good", "Available", None),
                    ("Main Gym", "Sports", "Gym", 60, "Sports Complex", "Good", "Available", None),
                    ("Badminton Court 1", "Sports", "Court", 4, "Sports Complex", "Good", "Available", None),
                    ("Swimming Pool", "Sports", "Pool", 50, "Sports Complex", "Fair", "Available", None),
                    ("Field A", "Sports", "Field", 22, "Outdoor Grounds", "Good", "Available", None),
                    ("Projector #1", "Equipment", "Projector", 1, "AV Store", "Good", "Available", None),
                    ("Laptop Set (x10)", "Equipment", "Laptop", 10, "IT Store", "Good", "Available", None),
                    ("Oscilloscope", "Equipment", "Lab Instrument", 1, "Electronics Lab", "Good", "Available", None),
                ],
            )
        self.conn.commit()

    def close(self):
        self.conn.close()


# --------------------------------------------------------------------------
# USER MANAGER
# --------------------------------------------------------------------------
class UserManager:
    # Student ID cards don't print an email address or role, so scanning a
    # card auto-fills those two from the student ID instead of leaving them
    # blank. Adjust the domain here if your institution uses a different one.
    DEFAULT_EMAIL_DOMAIN = "tarumt.edu.my"
    DEFAULT_SCAN_ROLE = "Student"

    def __init__(self, db: Database):
        self.db = db

    @classmethod
    def suggest_email(cls, student_id, domain=None):
        """Best-guess student email derived from the card's student ID,
        e.g. '23WMR12345' -> '23wmr12345@tarumt.edu.my'. Returns "" if the
        student ID isn't in the expected format."""
        student_id = (student_id or "").strip().upper()
        if not cls.validate_student_id(student_id):
            return ""
        return f"{student_id.lower()}@{domain or cls.DEFAULT_EMAIL_DOMAIN}"

    # ---- validation ----------------------------------------------------
    @staticmethod
    def validate_student_id(student_id):
        """Format: 2 digits + 3 capital letters + 5 digits, e.g. 23WMR12345."""
        return bool(STUDENT_ID_RE.match((student_id or "").strip().upper()))

    @staticmethod
    def validate_expiry_date(expiry_date):
        """Format: DD-MM-YYYY, as printed on the card."""
        value = (expiry_date or "").strip()
        if not EXPIRY_DATE_RE.match(value):
            return False
        try:
            datetime.strptime(value, "%d-%m-%Y")
            return True
        except ValueError:
            return False

    @staticmethod
    def validate_barcode_number(barcode_number):
        """Digits only, matching what the printed barcode encodes."""
        return bool(BARCODE_NUMBER_RE.match((barcode_number or "").strip()))

    @staticmethod
    def validate_email(email):
        """Basic email format check, e.g. name@example.com."""
        return bool(EMAIL_RE.match((email or "").strip()))

    def _clean_and_validate_user(self, fields):
        cleaned = {
            "name": (fields.get("name") or "").strip(),
            "role": (fields.get("role") or "").strip(),
            "email": (fields.get("email") or "").strip(),
            "student_id": (fields.get("student_id") or "").strip().upper(),
            "expiry_date": (fields.get("expiry_date") or "").strip(),
            "barcode_number": (fields.get("barcode_number") or "").strip(),
        }
        labels = {
            "name": "Name",
            "role": "Role",
            "email": "Email",
            "student_id": "Student ID",
            "expiry_date": "Expiry date",
            "barcode_number": "Barcode number",
        }
        missing = [label for key, label in labels.items() if not cleaned[key]]
        if missing:
            raise ValueError("Please fill in: " + ", ".join(missing) + ".")
        if cleaned["role"] not in ("Student", "Faculty", "Staff", "Admin"):
            raise ValueError("Role must be Student, Faculty, Staff, or Admin.")
        if not self.validate_email(cleaned["email"]):
            raise ValueError("Email must be valid, e.g. student@example.com.")
        if not self.validate_student_id(cleaned["student_id"]):
            raise ValueError("Student ID must be 2 digits + 3 capital letters + 5 digits, "
                              "e.g. 23WMR12345.")
        if not self.validate_expiry_date(cleaned["expiry_date"]):
            raise ValueError("Expiry date must be a valid DD-MM-YYYY date, e.g. 31-12-2026.")
        if not self.validate_barcode_number(cleaned["barcode_number"]):
            raise ValueError("Barcode number must be 6-14 digits.")
        return cleaned

    def _assert_unique_student_id(self, student_id, ignore_user_id=None):
        if not student_id:
            return
        row = self.find_by_student_id(student_id)
        if row and row["id"] != ignore_user_id:
            raise ValueError(f"Student ID '{student_id}' is already assigned to {row['name']}.")

    # ---- reads -----------------------------------------------------------
    def list_users(self):
        return self.db.conn.execute("SELECT * FROM users ORDER BY name").fetchall()

    def get_user(self, user_id):
        return self.db.conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    def find_by_student_id(self, student_id):
        student_id = (student_id or "").strip().upper()
        if not student_id:
            return None
        return self.db.conn.execute(
            "SELECT * FROM users WHERE student_id=?", (student_id,)
        ).fetchone()

    def search_users(self, search_text=None, role=None):
        query = "SELECT * FROM users WHERE 1=1"
        params = []
        if role and role != "All":
            query += " AND role=?"
            params.append(role)
        if search_text:
            query += " AND (name LIKE ? OR student_id LIKE ? OR email LIKE ?)"
            like = f"%{search_text}%"
            params += [like, like, like]
        query += " ORDER BY name"
        return self.db.conn.execute(query, params).fetchall()

    # ---- writes ------------------------------------------------------------
    def add_user(self, name, role, email="", student_id="", expiry_date="", barcode_number=""):
        cleaned = self._clean_and_validate_user({
            "name": name,
            "role": role,
            "email": email,
            "student_id": student_id,
            "expiry_date": expiry_date,
            "barcode_number": barcode_number,
        })
        self._assert_unique_student_id(cleaned["student_id"])

        cur = self.db.conn.execute(
            "INSERT INTO users (name, role, email, student_id, expiry_date, barcode_number) "
            "VALUES (?,?,?,?,?,?)",
            (
                cleaned["name"], cleaned["role"], cleaned["email"], cleaned["student_id"],
                cleaned["expiry_date"], cleaned["barcode_number"],
            ),
        )
        self.db.conn.commit()
        return cur.lastrowid

    def update_user(self, user_id, **fields):
        if not fields:
            return
        current = self.get_user(user_id)
        if current is None:
            raise ValueError("User not found.")
        merged = {key: current[key] for key in (
            "name", "role", "email", "student_id", "expiry_date", "barcode_number"
        )}
        merged.update(fields)
        cleaned = self._clean_and_validate_user(merged)
        self._assert_unique_student_id(cleaned["student_id"], ignore_user_id=user_id)

        cols = ", ".join(f"{k}=?" for k in cleaned)
        vals = list(cleaned.values()) + [user_id]
        self.db.conn.execute(f"UPDATE users SET {cols} WHERE id=?", vals)
        self.db.conn.commit()

    def delete_user(self, user_id):
        self.db.conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        self.db.conn.commit()

    # ---- student self-service: password + profile picture ----------------
    # Separate from AuthManager's `admins` table - these credentials let a
    # user sign in to the *student portal* as themselves (see
    # StudentAuthManager below), scoped to their own record only.
    _ITERATIONS = 100_000

    @classmethod
    def _hash(cls, password: str, salt_hex: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), cls._ITERATIONS
        ).hex()

    def has_password(self, user_id):
        row = self.get_user(user_id)
        return bool(row and row["password_hash"])

    def set_password(self, user_id, new_password):
        new_password = (new_password or "").strip()
        if len(new_password) < 6:
            raise ValueError("Password must be at least 6 characters.")
        salt = secrets.token_hex(16)
        pw_hash = self._hash(new_password, salt)
        self.db.conn.execute(
            "UPDATE users SET salt=?, password_hash=? WHERE id=?", (salt, pw_hash, user_id)
        )
        self.db.conn.commit()

    def verify_password(self, user_id, password):
        row = self.get_user(user_id)
        if row is None or not row["password_hash"]:
            return False
        return self._hash(password or "", row["salt"]) == row["password_hash"]

    def update_profile_picture(self, user_id, path):
        self.db.conn.execute(
            "UPDATE users SET profile_picture=? WHERE id=?", (path, user_id)
        )
        self.db.conn.commit()


# --------------------------------------------------------------------------
# FACILITY & RESOURCE MANAGER  (module d)
# --------------------------------------------------------------------------
class FacilityManager:
    def __init__(self, db: Database):
        self.db = db

    def list_facilities(self, category=None):
        if category and category != "All":
            return self.db.conn.execute(
                "SELECT * FROM facilities WHERE category=? ORDER BY name", (category,)
            ).fetchall()
        return self.db.conn.execute("SELECT * FROM facilities ORDER BY category, name").fetchall()

    def get_facility(self, facility_id):
        return self.db.conn.execute(
            "SELECT * FROM facilities WHERE id=?", (facility_id,)
        ).fetchone()

    def add_facility(self, name, category, ftype, capacity, location, condition="Good"):
        name = (name or "").strip()
        category = (category or "").strip()
        ftype = (ftype or "").strip()
        location = (location or "").strip()
        condition = (condition or "").strip()
        if not all((name, category, ftype, location, condition)):
            raise ValueError("Name, category, type, location, and condition are required.")
        cur = self.db.conn.execute(
            "INSERT INTO facilities (name, category, type, capacity, location, condition, status, image_path) "
            "VALUES (?,?,?,?,?,?, 'Available', NULL)",
            (name, category, ftype, capacity, location, condition),
        )
        self.db.conn.commit()
        return cur.lastrowid

    def update_facility(self, facility_id, **fields):
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [facility_id]
        self.db.conn.execute(f"UPDATE facilities SET {cols} WHERE id=?", vals)
        self.db.conn.commit()

    def delete_facility(self, facility_id):
        self.db.conn.execute("DELETE FROM facilities WHERE id=?", (facility_id,))
        self.db.conn.commit()

    def set_condition(self, facility_id, condition):
        status = "Maintenance" if condition in ("Under Maintenance", "Out of Service") else "Available"
        self.db.conn.execute(
            "UPDATE facilities SET condition=?, status=? WHERE id=?",
            (condition, status, facility_id),
        )
        self.db.conn.commit()

    def utilization_report(self):
        """Returns booking-count per facility -> used for statistics/reports."""
        return self.db.conn.execute(
            """
            SELECT f.id, f.name, f.category,
                   COUNT(b.id) AS total_bookings,
                   SUM(CASE WHEN b.status='Approved' THEN 1 ELSE 0 END) AS approved,
                   SUM(CASE WHEN b.status='Cancelled' THEN 1 ELSE 0 END) AS cancelled
            FROM facilities f
            LEFT JOIN bookings b ON b.facility_id = f.id
            GROUP BY f.id
            ORDER BY total_bookings DESC
            """
        ).fetchall()


# --------------------------------------------------------------------------
# BOOKING MANAGER  (modules a, b, c share this engine, filtered by category)
# --------------------------------------------------------------------------
class BookingManager:
    # A booking can no longer be moved to a different date/time once it's
    # within this many hours of its (current) start time - or once it has
    # already started/finished. Keeps people from yanking a facility out
    # from under a booking that's effectively already underway.
    RESCHEDULE_LOCK_HOURS = 3

    def __init__(self, db: Database, facility_manager: FacilityManager):
        self.db = db
        self.fm = facility_manager

    @staticmethod
    def _to_minutes(hhmm):
        h, m = map(int, hhmm.split(":"))
        return h * 60 + m

    @staticmethod
    def _booking_start_dt(booking):
        return datetime.strptime(
            f"{booking['booking_date']} {booking['start_time']}", "%Y-%m-%d %H:%M"
        )

    def reschedule_lock_reason(self, booking):
        """Returns a human-readable reason this booking can no longer be
        rescheduled, or None if it's still open to changes."""
        if booking["status"] in ("Completed", "Cancelled"):
            return f"This booking is already {booking['status'].lower()} and can no longer be rescheduled."
        hours_left = (self._booking_start_dt(booking) - datetime.now()).total_seconds() / 3600
        if hours_left < self.RESCHEDULE_LOCK_HOURS:
            return (
                f"This booking starts in less than {self.RESCHEDULE_LOCK_HOURS} hours "
                "(or has already started), so it can no longer be rescheduled."
            )
        return None

    @staticmethod
    def _parse_expiry_date(expiry_date):
        return datetime.strptime((expiry_date or "").strip(), "%d-%m-%Y").date()

    def _assert_user_card_active(self, user_id):
        user = self.db.conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if user is None:
            raise ValueError("Requester does not exist.")
        try:
            expiry_date = self._parse_expiry_date(user["expiry_date"])
        except ValueError:
            raise ValueError(
                f"{user['name']}'s student ID expiry date is invalid. "
                "Please update their ID details before booking or borrowing."
            )
        if expiry_date < date.today():
            raise ValueError(
                f"{user['name']}'s student ID expired on {user['expiry_date']}. "
                "Please renew or update their ID before booking or borrowing."
            )

    def has_conflict(self, facility_id, booking_date, start_time, end_time, ignore_booking_id=None):
        """Prevents double-booking: checks for overlapping approved/pending bookings."""
        rows = self.db.conn.execute(
            """
            SELECT * FROM bookings
            WHERE facility_id=? AND booking_date=? AND status IN ('Pending','Approved')
            """,
            (facility_id, booking_date),
        ).fetchall()
        new_start, new_end = self._to_minutes(start_time), self._to_minutes(end_time)
        for r in rows:
            if ignore_booking_id and r["id"] == ignore_booking_id:
                continue
            existing_start = self._to_minutes(r["start_time"])
            existing_end = self._to_minutes(r["end_time"])
            if new_start < existing_end and existing_start < new_end:
                return True
        return False

    def create_booking(self, facility_id, user_id, booking_date, start_time, end_time, purpose):
        booking_date = (booking_date or "").strip()
        start_time = (start_time or "").strip()
        end_time = (end_time or "").strip()
        purpose = (purpose or "").strip()
        if not all((facility_id, user_id, booking_date, start_time, end_time, purpose)):
            raise ValueError("Facility, requester, date, start time, end time, and purpose are required.")
        self._assert_user_card_active(user_id)
        facility = self.fm.get_facility(facility_id)
        if facility is None:
            raise ValueError("Facility does not exist.")
        if facility["condition"] in ("Under Maintenance", "Out of Service"):
            raise ValueError(f"'{facility['name']}' is currently {facility['condition']} and cannot be booked.")
        if self._to_minutes(end_time) <= self._to_minutes(start_time):
            raise ValueError("End time must be after start time.")
        try:
            start_dt = datetime.strptime(f"{booking_date} {start_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            raise ValueError("Invalid date or time format.")
        if start_dt < datetime.now():
            raise ValueError("You can't book a date/time that has already passed.")
        if self.has_conflict(facility_id, booking_date, start_time, end_time):
            raise ValueError("This facility is already booked for the selected time slot.")

        cur = self.db.conn.execute(
            """
            INSERT INTO bookings (facility_id, user_id, booking_date, start_time, end_time,
                                   purpose, status, created_at)
            VALUES (?,?,?,?,?,?, 'Pending', ?)
            """,
            (facility_id, user_id, booking_date, start_time, end_time, purpose,
             datetime.now().isoformat(timespec="seconds")),
        )
        self.db.conn.commit()
        return cur.lastrowid

    def list_bookings(self, category=None, status=None, search_text=None):
        query = """
            SELECT b.*, f.name AS facility_name, f.category AS category, u.name AS user_name
            FROM bookings b
            JOIN facilities f ON f.id = b.facility_id
            JOIN users u ON u.id = b.user_id
            WHERE 1=1
        """
        params = []
        if category and category != "All":
            query += " AND f.category=?"
            params.append(category)
        if status and status != "All":
            query += " AND b.status=?"
            params.append(status)
        if search_text:
            query += " AND (f.name LIKE ? OR u.name LIKE ? OR b.purpose LIKE ?)"
            like = f"%{search_text}%"
            params += [like, like, like]
        query += " ORDER BY b.booking_date DESC, b.start_time DESC"
        return self.db.conn.execute(query, params).fetchall()

    def get_booking(self, booking_id):
        return self.db.conn.execute(
            """
            SELECT b.*, f.name AS facility_name, f.category AS category, u.name AS user_name
            FROM bookings b
            JOIN facilities f ON f.id = b.facility_id
            JOIN users u ON u.id = b.user_id
            WHERE b.id=?
            """,
            (booking_id,),
        ).fetchone()

    def update_status(self, booking_id, new_status):
        if new_status == "Approved":
            booking = self.get_booking(booking_id)
            if booking is None:
                raise ValueError("Booking not found.")
            self._assert_user_card_active(booking["user_id"])
        self.db.conn.execute("UPDATE bookings SET status=? WHERE id=?", (new_status, booking_id))
        self.db.conn.commit()

    def reschedule(self, booking_id, booking_date, start_time, end_time):
        booking_date = (booking_date or "").strip()
        start_time = (start_time or "").strip()
        end_time = (end_time or "").strip()
        if not all((booking_date, start_time, end_time)):
            raise ValueError("New date, start time, and end time are required.")
        booking = self.get_booking(booking_id)
        if booking is None:
            raise ValueError("Booking not found.")
        lock_reason = self.reschedule_lock_reason(booking)
        if lock_reason:
            raise ValueError(lock_reason)
        try:
            new_start_dt = datetime.strptime(f"{booking_date} {start_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            raise ValueError("Invalid date or time format.")
        if new_start_dt < datetime.now():
            raise ValueError("You can't reschedule to a date/time that has already passed.")
        self._assert_user_card_active(booking["user_id"])
        if self.has_conflict(booking["facility_id"], booking_date, start_time, end_time,
                              ignore_booking_id=booking_id):
            raise ValueError("New time slot conflicts with an existing booking.")
        self.db.conn.execute(
            "UPDATE bookings SET booking_date=?, start_time=?, end_time=? WHERE id=?",
            (booking_date, start_time, end_time, booking_id),
        )
        self.db.conn.commit()

    def cancel_booking(self, booking_id):
        self.update_status(booking_id, "Cancelled")

    def auto_complete_due_bookings(self, user_id=None):
        """Marks 'Approved' bookings 'Completed' as soon as their end time is
        in the past, checked against the real system clock - no reminders,
        schedulers, or extra services involved, just a plain datetime
        comparison each time this is called.

        Pass `user_id` to only touch (and only report back) that user's own
        bookings, which is what the student app uses so a session only ever
        notifies about that student's bookings. Admin calls this with no
        filter so every overdue booking system-wide gets closed out.

        Returns the list of bookings that were just completed (with facility
        and requester names joined in) so the caller can show a notification.
        """
        now = datetime.now()
        today = now.date().isoformat()
        now_hhmm = now.strftime("%H:%M")
        query = """
            SELECT b.*, f.name AS facility_name, u.name AS user_name
            FROM bookings b
            JOIN facilities f ON f.id = b.facility_id
            JOIN users u ON u.id = b.user_id
            WHERE b.status='Approved'
              AND (b.booking_date < ? OR (b.booking_date = ? AND b.end_time <= ?))
        """
        params = [today, today, now_hhmm]
        if user_id is not None:
            query += " AND b.user_id=?"
            params.append(user_id)
        due = self.db.conn.execute(query, params).fetchall()
        if due:
            self.db.conn.executemany(
                "UPDATE bookings SET status='Completed' WHERE id=?",
                [(row["id"],) for row in due],
            )
            self.db.conn.commit()
        return due

    def upcoming_bookings(self, days_ahead=1):
        """Extra feature: bookings starting within the next `days_ahead` day(s) -> for reminders."""
        today = date.today()
        limit = today + timedelta(days=days_ahead)
        return self.db.conn.execute(
            """
            SELECT b.*, f.name AS facility_name, u.name AS user_name
            FROM bookings b JOIN facilities f ON f.id=b.facility_id JOIN users u ON u.id=b.user_id
            WHERE b.status='Approved' AND b.booking_date BETWEEN ? AND ?
            ORDER BY b.booking_date, b.start_time
            """,
            (today.isoformat(), limit.isoformat()),
        ).fetchall()


# --------------------------------------------------------------------------
# MAINTENANCE MANAGER (module e)
# --------------------------------------------------------------------------
class MaintenanceManager:
    def __init__(self, db: Database, facility_manager: FacilityManager):
        self.db = db
        self.fm = facility_manager

    def log_issue(self, facility_id, description, reported_by, log_date=None):
        description = (description or "").strip()
        reported_by = (reported_by or "").strip()
        if not facility_id or not description or not reported_by:
            raise ValueError("Facility, description, and reporter are required.")
        log_date = log_date or date.today().isoformat()
        cur = self.db.conn.execute(
            "INSERT INTO maintenance_logs (facility_id, log_date, description, status, reported_by) "
            "VALUES (?,?,?, 'Reported', ?)",
            (facility_id, log_date, description, reported_by),
        )
        self.db.conn.commit()
        # Automatically flag facility as under maintenance
        self.fm.set_condition(facility_id, "Under Maintenance")
        return cur.lastrowid

    def update_status(self, log_id, status):
        self.db.conn.execute("UPDATE maintenance_logs SET status=? WHERE id=?", (status, log_id))
        self.db.conn.commit()
        if status == "Resolved":
            row = self.db.conn.execute(
                "SELECT facility_id FROM maintenance_logs WHERE id=?", (log_id,)
            ).fetchone()
            if row:
                self.fm.set_condition(row["facility_id"], "Good")

    def list_logs(self, facility_id=None, status=None):
        query = """
            SELECT m.*, f.name AS facility_name FROM maintenance_logs m
            JOIN facilities f ON f.id = m.facility_id WHERE 1=1
        """
        params = []
        if facility_id:
            query += " AND m.facility_id=?"
            params.append(facility_id)
        if status and status != "All":
            query += " AND m.status=?"
            params.append(status)
        query += " ORDER BY m.log_date DESC"
        return self.db.conn.execute(query, params).fetchall()


# --------------------------------------------------------------------------
# USAGE MANAGER (module e - usage logs / check-in-check-out)
# --------------------------------------------------------------------------
class UsageManager:
    def __init__(self, db: Database):
        self.db = db

    def check_in(self, facility_id, booking_id=None, notes=""):
        cur = self.db.conn.execute(
            "INSERT INTO usage_logs (facility_id, booking_id, check_in, notes) VALUES (?,?,?,?)",
            (facility_id, booking_id, datetime.now().isoformat(timespec="seconds"), notes),
        )
        self.db.conn.commit()
        return cur.lastrowid

    def check_out(self, usage_log_id):
        self.db.conn.execute(
            "UPDATE usage_logs SET check_out=? WHERE id=?",
            (datetime.now().isoformat(timespec="seconds"), usage_log_id),
        )
        self.db.conn.commit()

    def list_logs(self, facility_id=None):
        query = """
            SELECT u.*, f.name AS facility_name FROM usage_logs u
            JOIN facilities f ON f.id = u.facility_id WHERE 1=1
        """
        params = []
        if facility_id:
            query += " AND u.facility_id=?"
            params.append(facility_id)
        query += " ORDER BY u.check_in DESC"
        return self.db.conn.execute(query, params).fetchall()


# --------------------------------------------------------------------------
# AUTH MANAGER - admin-only login gate for the whole application
# --------------------------------------------------------------------------
class AuthManager:
    """
    Handles admin accounts and login verification. Passwords are never
    stored in plain text: each account gets a random salt and the password
    is hashed with PBKDF2-HMAC-SHA256 (100,000 iterations) before storage.
    A default admin account is seeded on first run so the app is usable
    out of the box; the sign-in screen shows those default credentials
    so whoever sets the app up can log in and (ideally) change them.
    """

    DEFAULT_USERNAME = "admin"
    DEFAULT_PASSWORD = "admin123"
    _ITERATIONS = 100_000

    def __init__(self, db: Database):
        self.db = db
        self._seed_default_admin()

    @classmethod
    def _hash(cls, password: str, salt_hex: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), cls._ITERATIONS
        ).hex()

    def _seed_default_admin(self):
        cur = self.db.conn.execute("SELECT COUNT(*) AS c FROM admins")
        if cur.fetchone()["c"] == 0:
            self.create_admin(self.DEFAULT_USERNAME, self.DEFAULT_PASSWORD)

    def create_admin(self, username, password):
        salt = secrets.token_hex(16)
        pw_hash = self._hash(password, salt)
        self.db.conn.execute(
            "INSERT INTO admins (username, salt, password_hash, created_at) VALUES (?,?,?,?)",
            (username, salt, pw_hash, datetime.now().isoformat(timespec="seconds")),
        )
        self.db.conn.commit()

    def verify_login(self, username, password):
        row = self.db.conn.execute(
            "SELECT * FROM admins WHERE username=?", (username,)
        ).fetchone()
        if row is None:
            return False
        return self._hash(password, row["salt"]) == row["password_hash"]

    def change_password(self, username, new_password):
        salt = secrets.token_hex(16)
        pw_hash = self._hash(new_password, salt)
        self.db.conn.execute(
            "UPDATE admins SET salt=?, password_hash=? WHERE username=?",
            (salt, pw_hash, username),
        )
        self.db.conn.commit()

    def list_admins(self):
        return self.db.conn.execute(
            "SELECT id, username, created_at FROM admins ORDER BY username"
        ).fetchall()

    def get_admin(self, username):
        return self.db.conn.execute(
            "SELECT * FROM admins WHERE username=?", (username,)
        ).fetchone()

    def update_profile_picture(self, username, path):
        self.db.conn.execute(
            "UPDATE admins SET profile_picture=? WHERE username=?", (path, username)
        )
        self.db.conn.commit()


# --------------------------------------------------------------------------
# STUDENT AUTH MANAGER - login gate for the student self-service portal
# --------------------------------------------------------------------------
class StudentAuthManager:
    """
    Handles sign-in for the student portal, kept separate from AuthManager
    (which only ever gates the staff/admin app). Students sign in with
    their Student ID + a password.

    Existing student records were created by staff (manually or via card
    scan) and never had a password set. Rather than require a separate
    "activate your account" step, the *first* successful sign-in for a
    Student ID with no password yet claims the account: whatever password
    is entered becomes that student's password from then on, matching a
    common self-service onboarding pattern.
    """

    def __init__(self, db: Database, user_manager: UserManager):
        self.db = db
        self.um = user_manager

    def find_student(self, student_id):
        user = self.um.find_by_student_id(student_id)
        if user and user["role"] == "Student":
            return user
        return None

    def needs_setup(self, student_id):
        user = self.find_student(student_id)
        return bool(user) and not self.um.has_password(user["id"])

    def verify_login(self, student_id, password):
        """Returns the user row on success, or None on failure. Claims an
        unset password on first sign-in, as described above."""
        user = self.find_student(student_id)
        if user is None:
            return None
        if not self.um.has_password(user["id"]):
            if len((password or "").strip()) < 6:
                return None
            self.um.set_password(user["id"], password)
            return self.um.get_user(user["id"])
        if self.um.verify_password(user["id"], password):
            return user
        return None