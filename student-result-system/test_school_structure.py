import sqlite3

import pytest

import database


@pytest.fixture
def school_database(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "school.db")
    database.initialize_database()
    return database


def test_school_structure_schema_initializes_idempotently(school_database):
    school_database.initialize_database()

    with school_database.get_connection() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert {
        "schools", "academic_years", "terms", "school_classes",
        "students", "enrollments", "school_memberships",
        "teacher_class_assignments", "student_results",
    } <= tables


def test_academic_year_and_term_dates_are_validated(school_database):
    school_id = school_database.create_school("ZAIEON Demo School", "zdemo")
    year_id = school_database.create_academic_year(
        school_id, "2026/2027", "2026-09-01", "2027-07-31", is_current=True
    )
    term_id = school_database.create_term(
        year_id, "First Term", 1, "2026-09-01", "2026-12-18"
    )

    assert year_id and term_id
    with pytest.raises(ValueError, match="within the academic year"):
        school_database.create_term(
            year_id, "Summer Term", 3, "2027-08-01", "2027-08-20"
        )
    with pytest.raises(ValueError, match="cannot overlap"):
        school_database.create_term(
            year_id, "Overlapping Term", 2, "2026-12-01", "2027-02-01"
        )
    with pytest.raises(ValueError, match="before its end date"):
        school_database.create_academic_year(
            school_id, "Invalid", "2027-07-31", "2026-09-01"
        )


def test_current_academic_year_is_unique_per_school(school_database):
    school_id = school_database.create_school("School A")
    first_year = school_database.create_academic_year(
        school_id, "2025/2026", "2025-09-01", "2026-07-31", is_current=True
    )
    second_year = school_database.create_academic_year(
        school_id, "2026/2027", "2026-09-01", "2027-07-31", is_current=True
    )

    with school_database.get_connection() as connection:
        current_ids = [
            row["id"] for row in connection.execute(
                "SELECT id FROM academic_years WHERE school_id = ? AND is_current = 1",
                (school_id,),
            )
        ]

    assert current_ids == [second_year]
    assert first_year != second_year


def test_enrollment_links_student_class_and_year_within_one_school(school_database):
    school_a = school_database.create_school("School A")
    school_b = school_database.create_school("School B")
    year_a = school_database.create_academic_year(
        school_a, "2026/2027", "2026-09-01", "2027-07-31"
    )
    class_a = school_database.create_class(
        school_a, "Primary 1 Blue", level="Primary 1", section="Blue"
    )
    class_b = school_database.create_class(school_b, "Primary 1 Blue")
    student_a = school_database.create_student(
        school_a, "REG-001", "Test Student"
    )
    student_b = school_database.create_student(
        school_b, "REG-001", "Another Student"
    )
    with pytest.raises(sqlite3.IntegrityError):
        school_database.create_student(school_a, "reg-001", "Duplicate")

    enrollment_id = school_database.enroll_student(
        student_a, class_a, year_a, "2026-09-02"
    )

    with pytest.raises(ValueError, match="belong to one school"):
        school_database.enroll_student(
            student_a, class_b, year_a, "2026-09-02"
        )

    with pytest.raises(sqlite3.IntegrityError):
        school_database.enroll_student(
            student_a, class_a, year_a, "2026-09-05"
        )

    assert enrollment_id > 0
    assert student_a != student_b
