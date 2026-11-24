
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import date

# Location of the database folder
DATABASE_DIR = Path(__file__).parent / "database"

# Location of the database file
DATABASE_PATH = DATABASE_DIR / "school.db"


def get_connection():
    DATABASE_DIR.mkdir(exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    # Enable foreign-key enforcement
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


@contextmanager
def _connection_scope():
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teacher_classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            class_name TEXT NOT NULL,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (teacher_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            UNIQUE(teacher_id, class_name)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL
                CHECK(role IN ('student', 'teacher', 'admin'))
        )
    """)


    # Add password-change tracking to existing databases
    columns = [
        column["name"]
        for column in cursor.execute("PRAGMA table_info(users)").fetchall()
    ]

    if "must_change_password" not in columns:
        cursor.execute("""
            ALTER TABLE users
            ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0
        """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_accounts (
            user_id INTEGER PRIMARY KEY,
            reg_no TEXT UNIQUE NOT NULL,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)

    # Core school structure. These tables are additive so existing users,
    # attendance, and JSON student records remain untouched during rollout.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (length(trim(name)) > 0)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS academic_years (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            is_current INTEGER NOT NULL DEFAULT 0
                CHECK (is_current IN (0, 1)),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (school_id, name),
            UNIQUE (school_id, id),
            CHECK (start_date <= end_date),
            FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS one_current_year_per_school
        ON academic_years(school_id)
        WHERE is_current = 1
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS terms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academic_year_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            sequence INTEGER NOT NULL CHECK (sequence > 0),
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (academic_year_id, name),
            UNIQUE (academic_year_id, sequence),
            CHECK (start_date <= end_date),
            FOREIGN KEY (academic_year_id)
                REFERENCES academic_years(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS school_classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            level TEXT,
            section TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1
                CHECK (is_active IN (0, 1)),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (school_id, name),
            UNIQUE (school_id, id),
            CHECK (length(trim(name)) > 0),
            FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            registration_number TEXT NOT NULL,
            full_name TEXT NOT NULL,
            user_id INTEGER UNIQUE,
            is_active INTEGER NOT NULL DEFAULT 1
                CHECK (is_active IN (0, 1)),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (school_id, id),
            CHECK (length(trim(registration_number)) > 0),
            CHECK (length(trim(full_name)) > 0),
            FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS unique_student_registration_per_school
        ON students(school_id, lower(registration_number))
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS school_memberships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'teacher', 'student')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (school_id, user_id),
            FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teacher_class_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            academic_year_id INTEGER NOT NULL,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (school_id, teacher_id, class_id, academic_year_id),
            FOREIGN KEY (school_id, teacher_id)
                REFERENCES school_memberships(school_id, user_id)
                ON DELETE CASCADE,
            FOREIGN KEY (school_id, class_id)
                REFERENCES school_classes(school_id, id) ON DELETE CASCADE,
            FOREIGN KEY (school_id, academic_year_id)
                REFERENCES academic_years(school_id, id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            academic_year_id INTEGER NOT NULL,
            enrollment_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'completed', 'withdrawn')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (student_id, academic_year_id),
            FOREIGN KEY (school_id, student_id)
                REFERENCES students(school_id, id) ON DELETE CASCADE,
            FOREIGN KEY (school_id, class_id)
                REFERENCES school_classes(school_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (school_id, academic_year_id)
                REFERENCES academic_years(school_id, id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reg_no TEXT NOT NULL,
            class_name TEXT NOT NULL,
            attendance_date TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK(status IN ('Present', 'Absent', 'Late')),
            marked_by INTEGER NOT NULL,
            FOREIGN KEY (marked_by) REFERENCES users(id),
            UNIQUE(reg_no, attendance_date)
        )
    """)

    connection.commit()
    connection.close()


def _validated_date(value, field_name):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a valid YYYY-MM-DD date.") from error


def create_school(name, code=None):
    """Create a school tenant and return its database ID."""
    name = (name or "").strip()
    code = (code or "").strip().upper() or None
    if not name:
        raise ValueError("School name is required.")

    with _connection_scope() as connection:
        cursor = connection.execute(
            "INSERT INTO schools (name, code) VALUES (?, ?)", (name, code)
        )
        return cursor.lastrowid


def create_academic_year(school_id, name, start_date, end_date, is_current=False):
    """Create a school's academic year, optionally making it the current year."""
    name = (name or "").strip()
    start = _validated_date(start_date, "Start date")
    end = _validated_date(end_date, "End date")
    if not name:
        raise ValueError("Academic year name is required.")
    if start > end:
        raise ValueError("Academic year start date must be before its end date.")

    with _connection_scope() as connection:
        if is_current:
            connection.execute(
                "UPDATE academic_years SET is_current = 0 WHERE school_id = ?",
                (school_id,),
            )
        cursor = connection.execute("""
            INSERT INTO academic_years (
                school_id, name, start_date, end_date, is_current
            ) VALUES (?, ?, ?, ?, ?)
        """, (school_id, name, start.isoformat(), end.isoformat(), int(is_current)))
        return cursor.lastrowid


def create_term(academic_year_id, name, sequence, start_date, end_date):
    """Add a term whose dates fall within its academic year."""
    name = (name or "").strip()
    start = _validated_date(start_date, "Term start date")
    end = _validated_date(end_date, "Term end date")
    if not name:
        raise ValueError("Term name is required.")
    if start > end:
        raise ValueError("Term start date must be before its end date.")
    try:
        sequence = int(sequence)
    except (TypeError, ValueError) as error:
        raise ValueError("Term sequence must be a positive integer.") from error
    if sequence < 1:
        raise ValueError("Term sequence must be a positive integer.")

    with _connection_scope() as connection:
        year = connection.execute("""
            SELECT start_date, end_date FROM academic_years WHERE id = ?
        """, (academic_year_id,)).fetchone()
        if year is None:
            raise ValueError("Academic year does not exist.")
        if start < date.fromisoformat(year["start_date"]) or end > date.fromisoformat(year["end_date"]):
            raise ValueError("Term dates must fall within the academic year.")
        overlap = connection.execute("""
            SELECT 1 FROM terms
            WHERE academic_year_id = ?
              AND NOT (end_date < ? OR start_date > ?)
            LIMIT 1
        """, (academic_year_id, start.isoformat(), end.isoformat())).fetchone()
        if overlap:
            raise ValueError("Term dates cannot overlap another term.")
        cursor = connection.execute("""
            INSERT INTO terms (
                academic_year_id, name, sequence, start_date, end_date
            ) VALUES (?, ?, ?, ?, ?)
        """, (academic_year_id, name, sequence, start.isoformat(), end.isoformat()))
        return cursor.lastrowid


def create_class(school_id, name, level=None, section=None, sort_order=0):
    """Create a class or stream belonging to a school."""
    name = (name or "").strip()
    level = (level or "").strip() or None
    section = (section or "").strip() or None
    if not name:
        raise ValueError("Class name is required.")
    try:
        sort_order = int(sort_order)
    except (TypeError, ValueError) as error:
        raise ValueError("Class sort order must be an integer.") from error

    with _connection_scope() as connection:
        cursor = connection.execute("""
            INSERT INTO school_classes (
                school_id, name, level, section, sort_order
            ) VALUES (?, ?, ?, ?, ?)
        """, (school_id, name, level, section, sort_order))
        return cursor.lastrowid


def create_student(school_id, registration_number, full_name, user_id=None):
    """Create a student's school record; registration numbers are school-scoped."""
    registration_number = (registration_number or "").strip()
    full_name = (full_name or "").strip()
    if not registration_number:
        raise ValueError("Registration number is required.")
    if not full_name:
        raise ValueError("Student name is required.")

    with _connection_scope() as connection:
        if user_id is not None:
            user = connection.execute(
                "SELECT role FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if user is None or user["role"] != "student":
                raise ValueError("A student profile can only link to a student account.")
        cursor = connection.execute("""
            INSERT INTO students (
                school_id, registration_number, full_name, user_id
            ) VALUES (?, ?, ?, ?)
        """, (school_id, registration_number, full_name, user_id))
        return cursor.lastrowid


def enroll_student(student_id, class_id, academic_year_id, enrollment_date):
    """Enroll a student in a class for an academic year."""
    enrolled_on = _validated_date(enrollment_date, "Enrollment date")

    with _connection_scope() as connection:
        student = connection.execute(
            "SELECT school_id FROM students WHERE id = ?", (student_id,)
        ).fetchone()
        school_class = connection.execute(
            "SELECT school_id FROM school_classes WHERE id = ?", (class_id,)
        ).fetchone()
        year = connection.execute("""
            SELECT school_id, start_date, end_date
            FROM academic_years WHERE id = ?
        """, (academic_year_id,)).fetchone()

        if student is None or school_class is None or year is None:
            raise ValueError("Student, class, and academic year must exist.")
        if len({student["school_id"], school_class["school_id"], year["school_id"]}) != 1:
            raise ValueError("Student, class, and academic year must belong to one school.")
        if not (date.fromisoformat(year["start_date"]) <= enrolled_on <= date.fromisoformat(year["end_date"])):
            raise ValueError("Enrollment date must fall within the academic year.")

        cursor = connection.execute("""
            INSERT INTO enrollments (
                school_id, student_id, class_id, academic_year_id, enrollment_date
            ) VALUES (?, ?, ?, ?, ?)
        """, (student["school_id"], student_id, class_id, academic_year_id,
              enrolled_on.isoformat()))
        return cursor.lastrowid


def setup_initial_school(admin_id, name, code, year_name, start_date, end_date,
                         class_names):
    """Create the first school, current year, classes, and admin membership."""
    name = (name or "").strip()
    code = (code or "").strip().upper() or None
    year_name = (year_name or "").strip()
    start = _validated_date(start_date, "Academic year start date")
    end = _validated_date(end_date, "Academic year end date")
    class_names = list(dict.fromkeys(
        class_name.strip() for class_name in class_names if class_name.strip()
    ))
    if not name or not year_name:
        raise ValueError("School and academic year names are required.")
    if start > end:
        raise ValueError("Academic year start date must be before its end date.")
    if not class_names:
        raise ValueError("Add at least one class to continue.")

    with _connection_scope() as connection:
        admin = connection.execute(
            "SELECT role FROM users WHERE id = ?", (admin_id,)
        ).fetchone()
        if admin is None or admin["role"] != "admin":
            raise ValueError("Only an administrator can set up a school.")
        if connection.execute("SELECT 1 FROM schools LIMIT 1").fetchone():
            raise ValueError("A school has already been configured.")

        cursor = connection.execute(
            "INSERT INTO schools (name, code) VALUES (?, ?)", (name, code)
        )
        school_id = cursor.lastrowid
        year_cursor = connection.execute("""
            INSERT INTO academic_years (
                school_id, name, start_date, end_date, is_current
            ) VALUES (?, ?, ?, ?, 1)
        """, (school_id, year_name, start.isoformat(), end.isoformat()))
        academic_year_id = year_cursor.lastrowid

        for sort_order, class_name in enumerate(class_names):
            prefix = class_name.split(maxsplit=1)[0]
            level = {
                "Primary": "Primary",
                "JSS": "Junior Secondary",
                "SS": "Senior Secondary",
            }.get(prefix)
            connection.execute("""
                INSERT INTO school_classes (school_id, name, level, sort_order)
                VALUES (?, ?, ?, ?)
            """, (school_id, class_name, level, sort_order))

        connection.execute("""
            INSERT INTO school_memberships (school_id, user_id, role)
            VALUES (?, ?, 'admin')
        """, (school_id, admin_id))
        return {"school_id": school_id, "academic_year_id": academic_year_id}


def get_school_memberships(user_id):
    with _connection_scope() as connection:
        return connection.execute("""
            SELECT schools.id AS school_id, schools.name AS school_name,
                   school_memberships.role
            FROM school_memberships
            JOIN schools ON schools.id = school_memberships.school_id
            WHERE school_memberships.user_id = ?
            ORDER BY schools.name
        """, (user_id,)).fetchall()


def get_school_context(school_id):
    with _connection_scope() as connection:
        return connection.execute("""
            SELECT schools.id AS school_id, schools.name AS school_name,
                   academic_years.id AS academic_year_id,
                   academic_years.name AS academic_year_name,
                   academic_years.start_date, academic_years.end_date
            FROM schools
            JOIN academic_years ON academic_years.school_id = schools.id
            WHERE schools.id = ? AND academic_years.is_current = 1
        """, (school_id,)).fetchone()


def get_school_count():
    with _connection_scope() as connection:
        return connection.execute("SELECT COUNT(*) FROM schools").fetchone()[0]


def get_school_classes(school_id):
    with _connection_scope() as connection:
        return connection.execute("""
            SELECT id, name, level, section
            FROM school_classes
            WHERE school_id = ? AND is_active = 1
            ORDER BY sort_order, name
        """, (school_id,)).fetchall()


def get_teachers_for_school(school_id):
    with _connection_scope() as connection:
        return connection.execute("""
            SELECT id, username FROM users
            WHERE role = 'teacher'
            ORDER BY username
        """).fetchall()


def assign_teacher_to_school_class(school_id, teacher_id, class_id,
                                   academic_year_id):
    """Assign a teacher to a class for this school's academic year."""
    with _connection_scope() as connection:
        teacher = connection.execute(
            "SELECT role FROM users WHERE id = ?", (teacher_id,)
        ).fetchone()
        if teacher is None or teacher["role"] != "teacher":
            raise ValueError("Choose a valid teacher account.")

        membership = connection.execute("""
            SELECT role FROM school_memberships
            WHERE school_id = ? AND user_id = ?
        """, (school_id, teacher_id)).fetchone()
        if membership is None:
            connection.execute("""
                INSERT INTO school_memberships (school_id, user_id, role)
                VALUES (?, ?, 'teacher')
            """, (school_id, teacher_id))
        elif membership["role"] != "teacher":
            raise ValueError("The selected account is not a teacher in this school.")
        cursor = connection.execute("""
            INSERT INTO teacher_class_assignments (
                school_id, teacher_id, class_id, academic_year_id
            ) VALUES (?, ?, ?, ?)
        """, (school_id, teacher_id, class_id, academic_year_id))
        return cursor.lastrowid


def get_teacher_class_assignments(school_id, academic_year_id):
    with _connection_scope() as connection:
        return connection.execute("""
            SELECT users.username, school_classes.name AS class_name
            FROM teacher_class_assignments
            JOIN users ON users.id = teacher_class_assignments.teacher_id
            JOIN school_classes ON school_classes.id = teacher_class_assignments.class_id
            WHERE teacher_class_assignments.school_id = ?
              AND teacher_class_assignments.academic_year_id = ?
            ORDER BY users.username, school_classes.sort_order,
                     school_classes.name
        """, (school_id, academic_year_id)).fetchall()


def get_teachers():
    connection = get_connection()

    teachers = connection.execute("""
        SELECT id, username
        FROM users
        WHERE role = 'teacher'
        ORDER BY username
    """).fetchall()

    connection.close()
    return teachers


def assign_teacher_to_class(teacher_id, class_name):
    connection = get_connection()

    try:
        connection.execute("""
            INSERT INTO teacher_classes (teacher_id, class_name)
            VALUES (?, ?)
        """, (teacher_id, class_name))

        connection.commit()
        return True

    except sqlite3.IntegrityError:
        return False

    finally:
        connection.close()


def get_teacher_classes(teacher_id):
    connection = get_connection()

    classes = connection.execute("""
        SELECT class_name
        FROM teacher_classes
        WHERE teacher_id = ?
        ORDER BY class_name
    """, (teacher_id,)).fetchall()

    connection.close()

    return [row["class_name"] for row in classes]

if __name__ == "__main__":
    initialize_database()
    print("School database created successfully!")


def get_student_reg_no(user_id):
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            "SELECT reg_no FROM student_accounts WHERE user_id = ?",
            (user_id,)
        )

        result = cursor.fetchone()

        if result:
            return result["reg_no"]

        return None

    finally:
        connection.close()
