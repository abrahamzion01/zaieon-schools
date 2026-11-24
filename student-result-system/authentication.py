
import hashlib
import secrets
import hmac
import sqlite3
from datetime import date

from database import get_connection, initialize_database


# Allowed account types
VALID_ROLES = ("student", "teacher", "admin")

# Password hashing settings
ITERATIONS = 600_000


def hash_password(password, salt):
    password_bytes = password.encode("utf-8")
    salt_bytes = bytes.fromhex(salt)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password_bytes,
        salt_bytes,
        ITERATIONS
    )

    return password_hash.hex()


def register_user(username, password, role, reg_no=None):
    username = username.strip()
    role = role.strip().lower()

    if not username or not password:
        return False

    if len(password) < 8:
        return False

    if role not in VALID_ROLES:
        return False

    if role == "student":
        if not reg_no or not reg_no.strip():
            return False
        reg_no = reg_no.strip()

    # Generate a random salt
    salt = secrets.token_hex(16)

    # Hash the password
    password_hash = hash_password(password, salt)

    initialize_database()
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
        INSERT INTO users (
            username,
            password_hash,
            salt,
            role,
            must_change_password
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        username,
        password_hash,
        salt,
        role,
        1 if role == "student" else 0
    ))

        user_id = cursor.lastrowid

        if role == "student":
            cursor.execute("""
                INSERT INTO student_accounts (user_id, reg_no)
                VALUES (?, ?)
            """, (user_id, reg_no))

        connection.commit()
        return True

    except Exception as error:
        print("Account registration error:", error)
        return False

    finally:
        connection.close()


def register_student_with_enrollment(username, password, registration_number,
                                     full_name, school_id, class_id,
                                     academic_year_id, enrollment_date=None):
    """Atomically create a student login, school profile, and enrollment."""
    username = (username or "").strip()
    registration_number = (registration_number or "").strip()
    full_name = (full_name or "").strip()
    if not username or len(password or "") < 8:
        return None
    if not registration_number or not full_name:
        return None

    try:
        enrolled_on = date.fromisoformat(enrollment_date or date.today().isoformat())
    except (TypeError, ValueError):
        return None

    salt = secrets.token_hex(16)
    password_hash = hash_password(password, salt)
    initialize_database()
    connection = get_connection()

    try:
        year = connection.execute("""
            SELECT school_id, start_date, end_date
            FROM academic_years WHERE id = ?
        """, (academic_year_id,)).fetchone()
        school_class = connection.execute(
            "SELECT school_id FROM school_classes WHERE id = ?", (class_id,)
        ).fetchone()
        if (year is None or school_class is None
                or year["school_id"] != school_id
                or school_class["school_id"] != school_id
                or not (date.fromisoformat(year["start_date"])
                        <= enrolled_on <= date.fromisoformat(year["end_date"]))):
            return None

        cursor = connection.execute("""
            INSERT INTO users (
                username, password_hash, salt, role, must_change_password
            ) VALUES (?, ?, ?, 'student', 1)
        """, (username, password_hash, salt))
        user_id = cursor.lastrowid

        connection.execute("""
            INSERT INTO student_accounts (user_id, reg_no) VALUES (?, ?)
        """, (user_id, registration_number))
        student_cursor = connection.execute("""
            INSERT INTO students (
                school_id, registration_number, full_name, user_id
            ) VALUES (?, ?, ?, ?)
        """, (school_id, registration_number, full_name, user_id))
        student_id = student_cursor.lastrowid
        connection.execute("""
            INSERT INTO school_memberships (school_id, user_id, role)
            VALUES (?, ?, 'student')
        """, (school_id, user_id))
        connection.execute("""
            INSERT INTO enrollments (
                school_id, student_id, class_id, academic_year_id,
                enrollment_date
            ) VALUES (?, ?, ?, ?, ?)
        """, (school_id, student_id, class_id, academic_year_id,
              enrolled_on.isoformat()))

        connection.commit()
        return user_id
    except sqlite3.IntegrityError:
        connection.rollback()
        return None
    finally:
        connection.close()


def login_user(username, password):
    username = username.strip()

    initialize_database()
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT * FROM users WHERE username = ?
        """, (username,))

        user = cursor.fetchone()

        if user is None:
            return None

        entered_hash = hash_password(password, user["salt"])

        if hmac.compare_digest(
            entered_hash,
            user["password_hash"]
        ):
                return {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"],
                "must_change_password": user["must_change_password"]
            }
        return None

    finally:
        connection.close()


def change_password(user_id, new_password):
    if not new_password or len(new_password) < 8:
        return False

    salt = secrets.token_hex(16)
    password_hash = hash_password(new_password, salt)

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            UPDATE users
            SET password_hash = ?,
                salt = ?,
                must_change_password = 0
            WHERE id = ?
        """, (password_hash, salt, user_id))

        connection.commit()

        return cursor.rowcount == 1

    finally:
        connection.close()
