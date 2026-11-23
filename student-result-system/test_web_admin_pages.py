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
    client = web_app.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "admin-test"
        session["role"] = "admin"
        session["must_change_password"] = False

    return client


def test_dashboard_quick_actions_link_to_admin_pages(admin_client):
    response = admin_client.get("/dashboard")

    assert response.status_code == 200
    assert b'href="/register" class="action-card"' in response.data
    assert b'href="/results" class="action-card"' in response.data
    assert b'href="/teachers" class="action-card"' in response.data
    assert b'href="/attendance" class="action-card"' in response.data


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

    response = admin_client.post("/teachers", data={
        "teacher_id": str(teacher["id"]),
        "class_name": "JSS 1",
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"JSS 1 assigned to teacher-test." in response.data
    assert database.get_teacher_classes(teacher["id"]) == ["JSS 1"]


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
