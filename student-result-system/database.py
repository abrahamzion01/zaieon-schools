
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
        CREATE TABLE IF NOT EXISTS school_class_subjects (
            school_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (school_id, class_id, subject),
            CHECK (length(trim(subject)) > 0),
            FOREIGN KEY (school_id, class_id)
                REFERENCES school_classes(school_id, id) ON DELETE CASCADE
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
        CREATE TABLE IF NOT EXISTS student_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id INTEGER NOT NULL,
            term_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            score REAL NOT NULL CHECK (score >= 0 AND score <= 100),
            recorded_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (enrollment_id, term_id, subject),
            CHECK (length(trim(subject)) > 0),
            FOREIGN KEY (enrollment_id) REFERENCES enrollments(id) ON DELETE CASCADE,
            FOREIGN KEY (term_id) REFERENCES terms(id) ON DELETE CASCADE,
            FOREIGN KEY (recorded_by) REFERENCES users(id)
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
        overlap = connection.execute("""
            SELECT 1 FROM academic_years
            WHERE school_id = ?
              AND NOT (end_date < ? OR start_date > ?)
            LIMIT 1
        """, (school_id, start.isoformat(), end.isoformat())).fetchone()
        if overlap:
            raise ValueError("Academic year dates cannot overlap another year.")
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


def get_school_academic_years(school_id):
    """Return all academic years belonging to one school."""
    with _connection_scope() as connection:
        return connection.execute("""
            SELECT id, name, start_date, end_date, is_current
            FROM academic_years
            WHERE school_id = ?
            ORDER BY start_date DESC, id DESC
        """, (school_id,)).fetchall()


def get_school_academic_year(school_id, academic_year_id):
    """Return one year scoped to a school, or None if it belongs elsewhere."""
    with _connection_scope() as connection:
        return connection.execute("""
            SELECT id AS academic_year_id, name AS academic_year_name,
                   start_date, end_date, is_current
            FROM academic_years
            WHERE school_id = ? AND id = ?
        """, (school_id, academic_year_id)).fetchone()


def set_current_academic_year(school_id, academic_year_id):
    """Make a school's existing academic year current without affecting others."""
    with _connection_scope() as connection:
        year = connection.execute("""
            SELECT id FROM academic_years
            WHERE school_id = ? AND id = ?
        """, (school_id, academic_year_id)).fetchone()
        if year is None:
            raise ValueError("Choose an academic year belonging to this school.")
        connection.execute(
            "UPDATE academic_years SET is_current = 0 WHERE school_id = ?",
            (school_id,),
        )
        connection.execute("""
            UPDATE academic_years SET is_current = 1
            WHERE school_id = ? AND id = ?
        """, (school_id, academic_year_id))


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


def promote_students_to_year(school_id, source_year_id, target_year_id,
                             promotions, enrollment_date):
    """Enroll selected prior-year students in their new-year classes atomically."""
    enrolled_on = _validated_date(enrollment_date, "Enrollment date")
    promotions = list(promotions)
    if not promotions:
        raise ValueError("Select at least one student to enroll in the current year.")

    student_ids = []
    normalized = []
    for promotion in promotions:
        try:
            student_id = int(promotion["student_id"])
            class_id = int(promotion["class_id"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Choose a destination class for every selected student.") from error
        student_ids.append(student_id)
        normalized.append((student_id, class_id))
    if len(student_ids) != len(set(student_ids)):
        raise ValueError("A student can only be selected once per promotion batch.")

    with _connection_scope() as connection:
        source_year = connection.execute("""
            SELECT id, end_date FROM academic_years
            WHERE school_id = ? AND id = ? AND is_current = 0
        """, (school_id, source_year_id)).fetchone()
        target_year = connection.execute("""
            SELECT id, start_date, end_date FROM academic_years
            WHERE school_id = ? AND id = ? AND is_current = 1
        """, (school_id, target_year_id)).fetchone()
        if source_year is None:
            raise ValueError("Choose a previous academic year in this school.")
        if target_year is None:
            raise ValueError("Promotions must target this school's current academic year.")
        if source_year["end_date"] >= target_year["start_date"]:
            raise ValueError("Choose an academic year that ended before the current year began.")
        if not (date.fromisoformat(target_year["start_date"]) <= enrolled_on
                <= date.fromisoformat(target_year["end_date"])):
            raise ValueError("Enrollment date must fall within the current academic year.")

        for student_id, class_id in normalized:
            source_enrollment = connection.execute("""
                SELECT 1 FROM enrollments
                JOIN students ON students.id = enrollments.student_id
                             AND students.school_id = enrollments.school_id
                WHERE enrollments.school_id = ?
                  AND enrollments.academic_year_id = ?
                  AND enrollments.student_id = ?
                  AND enrollments.status = 'active'
                  AND students.is_active = 1
            """, (school_id, source_year_id, student_id)).fetchone()
            if source_enrollment is None:
                raise ValueError("A selected student is not active in the chosen previous year.")

            target_enrollment = connection.execute("""
                SELECT 1 FROM enrollments
                WHERE school_id = ? AND academic_year_id = ? AND student_id = ?
            """, (school_id, target_year_id, student_id)).fetchone()
            if target_enrollment:
                raise ValueError("A selected student is already enrolled in the current year.")

            destination = connection.execute("""
                SELECT 1 FROM school_classes
                WHERE school_id = ? AND id = ? AND is_active = 1
            """, (school_id, class_id)).fetchone()
            if destination is None:
                raise ValueError("Choose an active destination class in this school.")

            connection.execute("""
                INSERT INTO enrollments (
                    school_id, student_id, class_id, academic_year_id,
                    enrollment_date, status
                ) VALUES (?, ?, ?, ?, ?, 'active')
            """, (school_id, student_id, class_id, target_year_id,
                  enrolled_on.isoformat()))

    return len(normalized)


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


def get_school_class_subjects(school_id, class_id):
    """Return a class's saved subject list, or None before it is configured."""
    with _connection_scope() as connection:
        class_exists = connection.execute("""
            SELECT 1 FROM school_classes
            WHERE school_id = ? AND id = ? AND is_active = 1
        """, (school_id, class_id)).fetchone()
        if class_exists is None:
            raise ValueError("Choose an active class in this school.")
        subjects = connection.execute("""
            SELECT subject FROM school_class_subjects
            WHERE school_id = ? AND class_id = ?
            ORDER BY subject COLLATE NOCASE
        """, (school_id, class_id)).fetchall()
        return [row["subject"] for row in subjects] or None


def save_school_class_subjects(school_id, class_id, subjects):
    """Replace the offered subjects for one class within the selected school."""
    subjects = list(dict.fromkeys(
        subject.strip() for subject in subjects
        if isinstance(subject, str) and subject.strip()
    ))
    if not subjects:
        raise ValueError("Choose at least one subject for this class.")

    with _connection_scope() as connection:
        class_exists = connection.execute("""
            SELECT 1 FROM school_classes
            WHERE school_id = ? AND id = ? AND is_active = 1
        """, (school_id, class_id)).fetchone()
        if class_exists is None:
            raise ValueError("Choose an active class in this school.")
        connection.execute("""
            DELETE FROM school_class_subjects
            WHERE school_id = ? AND class_id = ?
        """, (school_id, class_id))
        connection.executemany("""
            INSERT INTO school_class_subjects (school_id, class_id, subject)
            VALUES (?, ?, ?)
        """, [(school_id, class_id, subject) for subject in subjects])


def preview_legacy_student_import(school_id, academic_year_id, records):
    """Return legacy students with duplicate and class-mapping information."""
    with _connection_scope() as connection:
        year = connection.execute("""
            SELECT start_date, end_date FROM academic_years
            WHERE id = ? AND school_id = ?
        """, (academic_year_id, school_id)).fetchone()
        if year is None:
            raise ValueError("The current academic year could not be found.")

        classes = connection.execute("""
            SELECT id, name FROM school_classes
            WHERE school_id = ? AND is_active = 1
        """, (school_id,)).fetchall()
        class_ids = {row["name"].casefold(): row["id"] for row in classes}
        preview = []
        for index, record in enumerate(records):
            registration = str(record.get("reg_no", "")).strip()
            name = str(record.get("name", "")).strip()
            student = None
            if registration:
                student = connection.execute("""
                    SELECT students.id,
                           enrollments.id AS enrollment_id,
                           school_classes.name AS enrolled_class
                    FROM students
                    LEFT JOIN enrollments
                      ON enrollments.student_id = students.id
                     AND enrollments.academic_year_id = ?
                    LEFT JOIN school_classes
                      ON school_classes.id = enrollments.class_id
                    WHERE students.school_id = ?
                      AND lower(students.registration_number) = lower(?)
                """, (academic_year_id, school_id, registration)).fetchone()
            status = "enrolled" if student and student["enrollment_id"] else (
                "profile" if student else "new"
            )
            preview.append({
                "index": index,
                "name": name,
                "reg_no": registration,
                "status": status,
                "class_name": student["enrolled_class"] if student and student["enrollment_id"] else None,
                "suggested_class_id": class_ids.get(
                    str(record.get("class_name", "")).strip().casefold()
                ),
            })
        return preview


def import_legacy_students(school_id, academic_year_id, records):
    """Create missing student profiles and current-year enrollments atomically."""
    prepared = []
    seen = set()
    for record in records:
        registration = str(record.get("reg_no", "")).strip()
        name = str(record.get("name", "")).strip()
        if not registration or not name or not any(character.isalpha() for character in name):
            raise ValueError("Every imported record needs a name and registration number.")
        key = registration.casefold()
        if key in seen:
            raise ValueError(f"The legacy file contains duplicate registration number {registration}.")
        seen.add(key)
        try:
            class_id = int(record.get("class_id", ""))
        except (TypeError, ValueError) as error:
            raise ValueError(f"Choose a class for {name}.") from error
        enrolled_on = _validated_date(record.get("enrollment_date"), "Enrollment date")
        prepared.append((registration, name, class_id, enrolled_on))

    with _connection_scope() as connection:
        year = connection.execute("""
            SELECT start_date, end_date FROM academic_years
            WHERE id = ? AND school_id = ?
        """, (academic_year_id, school_id)).fetchone()
        if year is None:
            raise ValueError("The current academic year could not be found.")
        year_start = date.fromisoformat(year["start_date"])
        year_end = date.fromisoformat(year["end_date"])

        for registration, name, class_id, enrolled_on in prepared:
            school_class = connection.execute("""
                SELECT id FROM school_classes
                WHERE id = ? AND school_id = ? AND is_active = 1
            """, (class_id, school_id)).fetchone()
            if school_class is None:
                raise ValueError(f"Choose an active class in this school for {name}.")
            if not year_start <= enrolled_on <= year_end:
                raise ValueError(f"Enrollment date for {name} must be within the current academic year.")

        created = 0
        enrolled = 0
        skipped = 0
        for registration, name, class_id, enrolled_on in prepared:
            student = connection.execute("""
                SELECT id, user_id FROM students
                WHERE school_id = ? AND lower(registration_number) = lower(?)
            """, (school_id, registration)).fetchone()
            if student is None:
                account = connection.execute("""
                    SELECT student_accounts.user_id
                    FROM student_accounts
                    JOIN users ON users.id = student_accounts.user_id
                    WHERE users.role = 'student'
                      AND lower(student_accounts.reg_no) = lower(?)
                """, (registration,)).fetchone()
                user_id = account["user_id"] if account else None
                if user_id is not None:
                    linked_student = connection.execute(
                        "SELECT school_id, registration_number FROM students WHERE user_id = ?",
                        (user_id,),
                    ).fetchone()
                    if linked_student is not None:
                        raise ValueError(
                            f"The login for {registration} is already linked to another student profile."
                        )
                cursor = connection.execute("""
                    INSERT INTO students (
                        school_id, registration_number, full_name, user_id
                    ) VALUES (?, ?, ?, ?)
                """, (school_id, registration, name, user_id))
                student_id = cursor.lastrowid
                created += 1
                if user_id is not None:
                    membership = connection.execute("""
                        SELECT role FROM school_memberships
                        WHERE school_id = ? AND user_id = ?
                    """, (school_id, user_id)).fetchone()
                    if membership and membership["role"] != "student":
                        raise ValueError(
                            f"The login for {registration} already has another role in this school."
                        )
                    if membership is None:
                        connection.execute("""
                            INSERT INTO school_memberships (school_id, user_id, role)
                            VALUES (?, ?, 'student')
                        """, (school_id, user_id))
            else:
                student_id = student["id"]

            existing_enrollment = connection.execute("""
                SELECT id FROM enrollments
                WHERE student_id = ? AND academic_year_id = ?
            """, (student_id, academic_year_id)).fetchone()
            if existing_enrollment:
                skipped += 1
                continue

            connection.execute("""
                INSERT INTO enrollments (
                    school_id, student_id, class_id, academic_year_id,
                    enrollment_date
                ) VALUES (?, ?, ?, ?, ?)
            """, (school_id, student_id, class_id, academic_year_id,
                  enrolled_on.isoformat()))
            enrolled += 1

        return {"created": created, "enrolled": enrolled, "skipped": skipped}


def get_terms_for_year(academic_year_id):
    with _connection_scope() as connection:
        return connection.execute("""
            SELECT id, name, sequence, start_date, end_date
            FROM terms
            WHERE academic_year_id = ?
            ORDER BY sequence, start_date
        """, (academic_year_id,)).fetchall()


def create_student_term_results(school_id, academic_year_id, registration_number,
                                term_id, scores, recorded_by, teacher_id=None,
                                class_id=None, replace_existing=False):
    """Save a full subject score set for a student's current-year enrollment."""
    with _connection_scope() as connection:
        enrollment = connection.execute("""
            SELECT enrollments.id, enrollments.class_id,
                   students.id AS student_id,
                   students.full_name, students.registration_number
            FROM enrollments
            JOIN students ON students.id = enrollments.student_id
                         AND students.school_id = enrollments.school_id
            WHERE enrollments.school_id = ?
              AND enrollments.academic_year_id = ?
              AND enrollments.status = 'active'
              AND lower(students.registration_number) = lower(?)
        """, (school_id, academic_year_id, registration_number)).fetchone()
        term = connection.execute("""
            SELECT terms.id FROM terms
            JOIN academic_years
              ON academic_years.id = terms.academic_year_id
            WHERE terms.id = ?
              AND academic_years.school_id = ?
              AND academic_years.id = ?
        """, (term_id, school_id, academic_year_id)).fetchone()
        if enrollment is None:
            raise ValueError("Choose a student enrolled in the current academic year.")
        if term is None:
            raise ValueError("Choose a term in the current academic year.")
        if class_id is not None and enrollment["class_id"] != class_id:
            raise ValueError("Choose a student in the selected class.")
        if teacher_id is not None:
            assignment = connection.execute("""
                SELECT 1 FROM teacher_class_assignments
                WHERE school_id = ? AND teacher_id = ? AND class_id = ?
                  AND academic_year_id = ?
            """, (school_id, teacher_id, enrollment["class_id"],
                  academic_year_id)).fetchone()
            if assignment is None:
                raise ValueError("You can enter results only for classes assigned to you.")

        if replace_existing:
            connection.execute("""
                DELETE FROM student_results
                WHERE enrollment_id = ? AND term_id = ?
            """, (enrollment["id"], term_id))

        for subject, score in scores.items():
            connection.execute("""
                INSERT INTO student_results (
                    enrollment_id, term_id, subject, score, recorded_by
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(enrollment_id, term_id, subject) DO UPDATE SET
                    score = excluded.score,
                    recorded_by = excluded.recorded_by,
                    updated_at = CURRENT_TIMESTAMP
            """, (enrollment["id"], term_id, subject, score, recorded_by))
        return {"name": enrollment["full_name"],
                "reg_no": enrollment["registration_number"]}


def get_students_for_year(school_id, academic_year_id, teacher_id=None,
                          class_id=None):
    with _connection_scope() as connection:
        return connection.execute("""
            SELECT students.id AS student_id, enrollments.id AS enrollment_id,
                   students.full_name AS name,
                   students.registration_number AS reg_no,
                   school_classes.id AS class_id,
                   school_classes.name AS class_name
            FROM enrollments
            JOIN students ON students.id = enrollments.student_id
                         AND students.school_id = enrollments.school_id
            JOIN school_classes ON school_classes.id = enrollments.class_id
                                AND school_classes.school_id = enrollments.school_id
            WHERE enrollments.school_id = ?
              AND enrollments.academic_year_id = ?
              AND enrollments.status = 'active'
              AND students.is_active = 1
              AND (? IS NULL OR enrollments.class_id = ?)
              AND (? IS NULL OR EXISTS (
                    SELECT 1 FROM teacher_class_assignments
                    WHERE teacher_class_assignments.school_id = enrollments.school_id
                      AND teacher_class_assignments.teacher_id = ?
                      AND teacher_class_assignments.class_id = enrollments.class_id
                      AND teacher_class_assignments.academic_year_id = enrollments.academic_year_id
              ))
            ORDER BY school_classes.sort_order, school_classes.name,
                     students.full_name
        """, (school_id, academic_year_id, class_id, class_id,
              teacher_id, teacher_id)).fetchall()


def get_results_for_term(school_id, academic_year_id, term_id,
                         teacher_id=None, class_id=None):
    """Return enrolled students with their subject marks and term totals."""
    with _connection_scope() as connection:
        rows = connection.execute("""
            SELECT enrollments.id AS enrollment_id,
                   students.full_name AS name,
                   students.registration_number AS reg_no,
                   school_classes.id AS class_id,
                   school_classes.name AS class_name,
                   student_results.subject, student_results.score
            FROM enrollments
            JOIN students ON students.id = enrollments.student_id
                         AND students.school_id = enrollments.school_id
            JOIN school_classes ON school_classes.id = enrollments.class_id
                                AND school_classes.school_id = enrollments.school_id
            LEFT JOIN student_results
              ON student_results.enrollment_id = enrollments.id
             AND student_results.term_id = ?
            WHERE enrollments.school_id = ?
              AND enrollments.academic_year_id = ?
              AND enrollments.status = 'active'
              AND students.is_active = 1
              AND (? IS NULL OR enrollments.class_id = ?)
              AND (? IS NULL OR EXISTS (
                    SELECT 1 FROM teacher_class_assignments
                    WHERE teacher_class_assignments.school_id = enrollments.school_id
                      AND teacher_class_assignments.teacher_id = ?
                      AND teacher_class_assignments.class_id = enrollments.class_id
                      AND teacher_class_assignments.academic_year_id = enrollments.academic_year_id
              ))
            ORDER BY school_classes.sort_order, school_classes.name,
                     students.full_name, student_results.subject
        """, (term_id, school_id, academic_year_id,
              class_id, class_id, teacher_id, teacher_id)).fetchall()

    results = {}
    for row in rows:
        result = results.setdefault(row["enrollment_id"], {
            "name": row["name"], "reg_no": row["reg_no"],
            "class_id": row["class_id"],
            "class_name": row["class_name"], "subjects": {},
        })
        if row["subject"] is not None:
            result["subjects"][row["subject"]] = row["score"]
    for result in results.values():
        scores = list(result["subjects"].values())
        result["total"] = sum(scores) if scores else None
        result["average"] = sum(scores) / len(scores) if scores else None
        result["grade"] = None
    return list(results.values())


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


def get_teacher_class_assignments(school_id, academic_year_id,
                                  teacher_id=None):
    with _connection_scope() as connection:
        return connection.execute("""
            SELECT users.id AS teacher_id, users.username,
                   school_classes.id AS class_id,
                   school_classes.name AS class_name
            FROM teacher_class_assignments
            JOIN users ON users.id = teacher_class_assignments.teacher_id
            JOIN school_classes ON school_classes.id = teacher_class_assignments.class_id
            WHERE teacher_class_assignments.school_id = ?
              AND teacher_class_assignments.academic_year_id = ?
              AND (? IS NULL OR teacher_class_assignments.teacher_id = ?)
            ORDER BY users.username, school_classes.sort_order,
                     school_classes.name
        """, (school_id, academic_year_id, teacher_id, teacher_id)).fetchall()


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
