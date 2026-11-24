import json

import pytest

import authentication
import database
import main
from web import app as web_app


@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "school.db")
    monkeypatch.setattr(main, "DATABASE_FILE", str(tmp_path / "students.json"))
    monkeypatch.setattr(main, "students", [{
        "name": "Test Student",
        "reg_no": "REG-TEST-1",
        "class_name": "Primary 1",
        "subjects": {},
        "total": None,
        "average": None,
        "grade": None,
    }])
    monkeypatch.setitem(web_app.app.config, "TESTING", True)

    database.initialize_database()
    assert authentication.register_user(
        "admin-test", "AdministratorPassword123", "admin"
    )
    connection = database.get_connection()
    try:
        admin_id = connection.execute(
            "SELECT id FROM users WHERE username = ?", ("admin-test",)
        ).fetchone()["id"]
    finally:
        connection.close()
    setup = database.setup_initial_school(
        admin_id,
        "Test School",
        "TEST",
        "2026/2027",
        "2026-09-01",
        "2027-07-31",
        [
            "Primary 1", "Primary 2", "Primary 3", "Primary 4", "Primary 5",
            "Primary 6", "JSS 1", "JSS 2", "JSS 3", "SS 1", "SS 2", "SS 3",
        ],
    )
    client = web_app.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = admin_id
        session["username"] = "admin-test"
        session["role"] = "admin"
        session["must_change_password"] = False
        session["school_id"] = setup["school_id"]

    return client


def test_dashboard_quick_actions_link_to_admin_pages(admin_client):
    response = admin_client.get("/dashboard")

    assert response.status_code == 200
    assert b'href="/register" class="action-card"' in response.data
    assert b'href="/results" class="action-card"' in response.data
    assert b'href="/teachers" class="action-card"' in response.data
    assert b'href="/attendance" class="action-card"' in response.data


def test_first_admin_sets_up_school_and_academic_year(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "school.db")
    monkeypatch.setattr(main, "DATABASE_FILE", str(tmp_path / "students.json"))
    database.initialize_database()
    assert authentication.register_user(
        "first-admin", "AdministratorPassword123", "admin"
    )
    connection = database.get_connection()
    try:
        admin_id = connection.execute(
            "SELECT id FROM users WHERE username = ?", ("first-admin",)
        ).fetchone()["id"]
    finally:
        connection.close()

    client = web_app.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = admin_id
        session["username"] = "first-admin"
        session["role"] = "admin"
        session["must_change_password"] = False

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 302
    assert dashboard.headers["Location"].endswith("/school-setup")

    setup = client.post("/school-setup", data={
        "school_name": "Example Primary and Secondary School",
        "school_code": "exs",
        "year_name": "2026/2027",
        "start_date": "2026-09-01",
        "end_date": "2027-07-31",
    }, follow_redirects=True)

    assert setup.status_code == 200
    assert b"School setup is complete." in setup.data
    with client.session_transaction() as session:
        school_id = session["school_id"]
    classes = database.get_school_classes(school_id)
    assert len(classes) == 12
    assert classes[0]["level"] == "Primary"
    assert classes[6]["level"] == "Junior Secondary"
    assert classes[9]["level"] == "Senior Secondary"
    assert database.get_school_context(school_id)["academic_year_name"] == "2026/2027"


def test_results_page_saves_valid_scores(admin_client, tmp_path):
    response = admin_client.post("/results", data={
        "reg_no": "REG-TEST-1",
        "Mathematics": "90",
        "English": "80",
        "Biology": "70",
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"Results saved for Test Student." in response.data
    assert main.students[0]["total"] == 240
    assert main.students[0]["average"] == 80
    assert main.students[0]["grade"] == "A"

    saved_students = json.loads((tmp_path / "students.json").read_text())
    assert saved_students[0]["subjects"]["Mathematics"] == 90


def test_teacher_page_assigns_a_class(admin_client):
    assert authentication.register_user(
        "teacher-test", "TeacherPassword123", "teacher"
    )
    teacher = database.get_teachers()[0]
    teacher_page = admin_client.get("/teachers")
    assert b'name="class_id"' in teacher_page.data
    with admin_client.session_transaction() as session:
        school_id = session["school_id"]
    school = database.get_school_context(school_id)
    school_class = next(
        row for row in database.get_school_classes(school_id)
        if row["name"] == "JSS 1"
    )

    response = admin_client.post("/teachers", data={
        "teacher_id": str(teacher["id"]),
        "class_id": str(school_class["id"]),
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"JSS 1 assigned to teacher-test." in response.data
    assignments = database.get_teacher_class_assignments(
        school_id, school["academic_year_id"]
    )
    assert [row["class_name"] for row in assignments] == ["JSS 1"]


def test_registration_creates_school_profile_and_year_enrollment(admin_client, tmp_path):
    with admin_client.session_transaction() as session:
        school_id = session["school_id"]
    school = database.get_school_context(school_id)
    school_class = next(
        row for row in database.get_school_classes(school_id)
        if row["name"] == "Primary 1"
    )
    register_page = admin_client.get("/register")
    assert b'name="class_id"' in register_page.data
    assert b"Primary 1" in register_page.data
    response = admin_client.post("/register", data={
        "name": "New Student",
        "reg_no": "REG-NEW-1",
        "class_id": str(school_class["id"]),
        "enrollment_date": "2026-11-24",
        "username": "student-new-1",
    })

    assert response.status_code == 200
    assert b"Student registered successfully!" in response.data
    saved_students = json.loads((tmp_path / "students.json").read_text())
    assert saved_students[-1]["class_name"] == "Primary 1"

    connection = database.get_connection()
    try:
        profile = connection.execute("""
            SELECT students.id, students.school_id, students.user_id,
                   enrollments.class_id, enrollments.academic_year_id,
                   users.must_change_password, school_memberships.role
            FROM students
            JOIN enrollments ON enrollments.student_id = students.id
            JOIN users ON users.id = students.user_id
            JOIN school_memberships
              ON school_memberships.user_id = students.user_id
             AND school_memberships.school_id = students.school_id
            WHERE students.registration_number = ?
        """, ("REG-NEW-1",)).fetchone()
    finally:
        connection.close()

    assert profile["school_id"] == school_id
    assert profile["class_id"] == school_class["id"]
    assert profile["academic_year_id"] == school["academic_year_id"]
    assert profile["must_change_password"] == 1
    assert profile["role"] == "student"


def test_attendance_page_filters_by_date_and_class(admin_client):
    assert authentication.register_user(
        "attendance-teacher", "AttendancePassword123", "teacher"
    )
    teacher_id = database.get_teachers()[0]["id"]
    connection = database.get_connection()
    try:
        connection.execute("""
            INSERT INTO attendance (
                reg_no, class_name, attendance_date, status, marked_by
            ) VALUES (?, ?, ?, ?, ?)
        """, ("REG-TEST-1", "Primary 1", "2026-11-23", "Present", teacher_id))
        connection.commit()
    finally:
        connection.close()

    response = admin_client.get(
        "/attendance?date=2026-11-23&class_name=Primary+1"
    )

    assert response.status_code == 200
    assert b"REG-TEST-1" in response.data
    assert b"Present" in response.data
    assert b"attendance-teacher" in response.data


def test_admin_pages_redirect_anonymous_visitors_to_login():
    client = web_app.app.test_client()

    for path in ("/results", "/teachers", "/attendance"):
        response = client.get(path)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")
