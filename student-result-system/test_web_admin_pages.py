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


@pytest.fixture
def teacher_client(admin_client):
    assert authentication.register_user(
        "teacher-test", "TeacherPassword123", "teacher"
    )
    connection = database.get_connection()
    try:
        teacher_id = connection.execute(
            "SELECT id FROM users WHERE username = ?", ("teacher-test",)
        ).fetchone()["id"]
    finally:
        connection.close()
    with admin_client.session_transaction() as session:
        school_id = session["school_id"]
    school = database.get_school_context(school_id)
    primary_one = next(
        row for row in database.get_school_classes(school_id)
        if row["name"] == "Primary 1"
    )
    database.assign_teacher_to_school_class(
        school_id, teacher_id, primary_one["id"], school["academic_year_id"]
    )
    with admin_client.session_transaction() as session:
        session["user_id"] = teacher_id
        session["username"] = "teacher-test"
        session["role"] = "teacher"
        session["must_change_password"] = False
    return admin_client, school, teacher_id, primary_one["id"]


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


def test_results_page_saves_valid_scores(admin_client):
    with admin_client.session_transaction() as session:
        school_id = session["school_id"]
    school = database.get_school_context(school_id)
    school_class = next(
        row for row in database.get_school_classes(school_id)
        if row["name"] == "Primary 1"
    )
    student_id = database.create_student(
        school_id, "REG-TEST-1", "Test Student"
    )
    database.enroll_student(
        student_id, school_class["id"], school["academic_year_id"],
        "2026-09-02"
    )
    term_id = database.create_term(
        school["academic_year_id"], "First Term", 1,
        "2026-09-01", "2026-12-18"
    )
    response = admin_client.post("/results", data={
        "reg_no": "REG-TEST-1",
        "term_id": str(term_id),
        "subject": ["Mathematics", "English", "Biology"],
        "score_Mathematics": "90",
        "score_English": "80",
        "score_Biology": "70",
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"Results saved for Test Student." in response.data
    results = database.get_results_for_term(
        school_id, school["academic_year_id"], term_id
    )
    assert results[0]["subjects"] == {
        "Biology": 70, "English": 80, "Mathematics": 90
    }
    assert results[0]["total"] == 240
    assert results[0]["average"] == 80
    assert results[0]["class_name"] == "Primary 1"
    assert main.students[0]["subjects"] == {}
    assert b"Grade" in admin_client.get(
        f"/results?term_id={term_id}"
    ).data

    updated = admin_client.post("/results", data={
        "reg_no": "REG-TEST-1",
        "term_id": str(term_id),
        "subject": ["Mathematics"],
        "score_Mathematics": "95",
    }, follow_redirects=True)
    assert b"Results saved for Test Student." in updated.data
    replaced = database.get_results_for_term(
        school_id, school["academic_year_id"], term_id
    )
    assert replaced[0]["subjects"] == {"Mathematics": 95}


def test_terms_page_creates_only_valid_current_year_terms(admin_client):
    response = admin_client.post("/terms", data={
        "name": "First Term",
        "sequence": "1",
        "start_date": "2026-09-01",
        "end_date": "2026-12-18",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Academic term added." in response.data
    assert b"First Term" in response.data

    overlapping = admin_client.post("/terms", data={
        "name": "Second Term",
        "sequence": "2",
        "start_date": "2026-12-18",
        "end_date": "2027-03-30",
    }, follow_redirects=True)
    assert b"Term dates cannot overlap another term." in overlapping.data


def test_admin_can_prepare_and_activate_academic_years(admin_client):
    with admin_client.session_transaction() as session:
        school_id = session["school_id"]
    original_year = database.get_school_context(school_id)

    overlapping = admin_client.post("/academic-years", data={
        "name": "Overlapping Year",
        "start_date": "2027-07-01",
        "end_date": "2028-06-30",
    }, follow_redirects=True)
    assert b"Academic year dates cannot overlap another year." in overlapping.data
    assert len(database.get_school_academic_years(school_id)) == 1

    created = admin_client.post("/academic-years", data={
        "name": "2027/2028",
        "start_date": "2027-09-01",
        "end_date": "2028-07-31",
    }, follow_redirects=True)
    assert created.status_code == 200
    assert b"Academic year added." in created.data
    assert b"2027/2028" in created.data
    assert database.get_school_context(school_id)["academic_year_id"] == original_year["academic_year_id"]

    planned_year = next(
        year for year in database.get_school_academic_years(school_id)
        if year["name"] == "2027/2028"
    )
    terms_page = admin_client.get(
        f"/terms?academic_year_id={planned_year['id']}"
    )
    assert terms_page.status_code == 200
    assert b"Add a term to 2027/2028" in terms_page.data

    add_term = admin_client.post("/terms", data={
        "academic_year_id": str(planned_year["id"]),
        "name": "First Term",
        "sequence": "1",
        "start_date": "2027-09-01",
        "end_date": "2027-12-17",
    }, follow_redirects=True)
    assert b"Academic term added." in add_term.data
    assert b"First Term" in add_term.data
    assert database.get_school_context(school_id)["academic_year_id"] == original_year["academic_year_id"]

    activated = admin_client.post("/academic-years", data={
        "action": "set-current",
        "academic_year_id": str(planned_year["id"]),
    }, follow_redirects=True)
    assert b"Current academic year updated." in activated.data
    current_year = database.get_school_context(school_id)
    assert current_year["academic_year_name"] == "2027/2028"
    assert current_year["academic_year_id"] == planned_year["id"]


def test_terms_route_rejects_an_academic_year_outside_the_school(admin_client):
    with admin_client.session_transaction() as session:
        school_id = session["school_id"]
    response = admin_client.post("/terms", data={
        "academic_year_id": "99999",
        "name": "Unauthorized Term",
        "sequence": "1",
        "start_date": "2026-09-01",
        "end_date": "2026-12-18",
    }, follow_redirects=True)
    assert b"Choose an academic year belonging to this school." in response.data
    assert database.get_terms_for_year(
        database.get_school_context(school_id)["academic_year_id"]
    ) == []


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


def test_teacher_can_enter_results_only_for_assigned_class(teacher_client):
    client, school, teacher_id, primary_one_id = teacher_client
    school_id = school["school_id"]
    primary_two = next(
        row for row in database.get_school_classes(school_id)
        if row["name"] == "Primary 2"
    )
    assigned_student_id = database.create_student(
        school_id, "REG-ASSIGNED", "Assigned Student"
    )
    unassigned_student_id = database.create_student(
        school_id, "REG-OTHER", "Other Class Student"
    )
    database.enroll_student(
        assigned_student_id, primary_one_id, school["academic_year_id"],
        "2026-09-03"
    )
    database.enroll_student(
        unassigned_student_id, primary_two["id"], school["academic_year_id"],
        "2026-09-03"
    )
    term_id = database.create_term(
        school["academic_year_id"], "First Term", 1,
        "2026-09-01", "2026-12-18"
    )

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert b"My Classes" in dashboard.data
    assert b"Primary 1" in dashboard.data

    results_page = client.get(
        f"/teacher/results?class_id={primary_one_id}&term_id={term_id}"
    )
    assert results_page.status_code == 200
    assert b"REG-ASSIGNED" in results_page.data
    assert b"REG-OTHER" not in results_page.data

    response = client.post("/teacher/results", data={
        "class_id": str(primary_one_id),
        "term_id": str(term_id),
        "reg_no": "REG-ASSIGNED",
        "subject": ["Mathematics", "English", "Biology"],
        "score_Mathematics": "91",
        "score_English": "82",
        "score_Biology": "73",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Results saved for Assigned Student." in response.data
    result_rows = database.get_results_for_term(
        school_id, school["academic_year_id"], term_id,
        teacher_id=teacher_id, class_id=primary_one_id
    )
    assert result_rows[0]["subjects"]["Mathematics"] == 91

    with pytest.raises(ValueError, match="only for classes assigned"):
        database.create_student_term_results(
            school_id, school["academic_year_id"], "REG-OTHER", term_id,
            {"Mathematics": 90}, teacher_id,
            teacher_id=teacher_id, class_id=primary_two["id"]
        )

    admin_results = client.get("/results")
    assert admin_results.status_code == 302


def test_secondary_score_form_uses_curriculum_subject_options(admin_client):
    with admin_client.session_transaction() as session:
        school_id = session["school_id"]
    school = database.get_school_context(school_id)
    jss_one = next(
        row for row in database.get_school_classes(school_id)
        if row["name"] == "JSS 1"
    )
    student_id = database.create_student(
        school_id, "REG-JSS-1", "Junior Student"
    )
    database.enroll_student(
        student_id, jss_one["id"], school["academic_year_id"], "2026-09-03"
    )
    term_id = database.create_term(
        school["academic_year_id"], "First Term", 1,
        "2026-09-01", "2026-12-18"
    )

    page = admin_client.get(f"/results?selected=REG-JSS-1&term_id={term_id}")
    assert page.status_code == 200
    assert b"Intermediate Science" in page.data
    assert b"Choose one Nigerian language" in page.data
    assert b"Horticulture and Crop Production" in page.data

    invalid = admin_client.post("/results", data={
        "reg_no": "REG-JSS-1",
        "term_id": str(term_id),
        "subject": ["Unlisted Subject"],
        "score_Unlisted Subject": "88",
    }, follow_redirects=True)
    assert b"Choose subjects from the list for this class level." in invalid.data
    assert database.get_results_for_term(
        school_id, school["academic_year_id"], term_id
    )[0]["subjects"] == {}

    saved = admin_client.post("/results", data={
        "reg_no": "REG-JSS-1",
        "term_id": str(term_id),
        "subject": ["English Studies", "Horticulture and Crop Production"],
        "score_English Studies": "88",
        "score_Horticulture and Crop Production": "92",
    }, follow_redirects=True)
    assert saved.status_code == 200
    result = database.get_results_for_term(
        school_id, school["academic_year_id"], term_id
    )[0]
    assert result["subjects"] == {
        "English Studies": 88,
        "Horticulture and Crop Production": 92,
    }

    ss_one = next(
        row for row in database.get_school_classes(school_id)
        if row["name"] == "SS 1"
    )
    senior_student_id = database.create_student(
        school_id, "REG-SS-1", "Senior Student"
    )
    database.enroll_student(
        senior_student_id, ss_one["id"], school["academic_year_id"],
        "2026-09-03"
    )
    senior_page = admin_client.get(
        f"/results?selected=REG-SS-1&term_id={term_id}"
    )
    assert b"General Mathematics" in senior_page.data
    assert b"Citizenship and Heritage Studies" in senior_page.data
    assert b"Accounting" in senior_page.data
    assert b"NERDC SSS offers 8" in senior_page.data


def test_admin_configures_offered_subjects_per_school_class(admin_client):
    with admin_client.session_transaction() as session:
        school_id = session["school_id"]
    school = database.get_school_context(school_id)
    jss_one = next(
        row for row in database.get_school_classes(school_id)
        if row["name"] == "JSS 1"
    )

    setup_page = admin_client.get(f"/subjects?class_id={jss_one['id']}")
    assert setup_page.status_code == 200
    assert b"Subjects offered in JSS 1" in setup_page.data
    assert b"name=\"subject\" value=\"Hausa\" checked" in setup_page.data

    saved_page = admin_client.post("/subjects", data={
        "class_id": str(jss_one["id"]),
        "subject": ["English Studies", "Yoruba", "Biology"],
    }, follow_redirects=True)
    assert saved_page.status_code == 200
    assert b"Subject offerings saved for JSS 1." in saved_page.data
    assert set(database.get_school_class_subjects(
        school_id, jss_one["id"]
    )) == {"English Studies", "Yoruba", "Biology"}

    student_id = database.create_student(
        school_id, "REG-CUSTOM-JSS", "Configured Subject Student"
    )
    database.enroll_student(
        student_id, jss_one["id"], school["academic_year_id"], "2026-09-03"
    )
    term_id = database.create_term(
        school["academic_year_id"], "First Term", 1,
        "2026-09-01", "2026-12-18"
    )

    score_page = admin_client.get(
        f"/results?selected=REG-CUSTOM-JSS&term_id={term_id}"
    )
    assert b"English Studies" in score_page.data
    assert b"Yoruba" in score_page.data
    assert b"Hausa" not in score_page.data

    rejected = admin_client.post("/results", data={
        "reg_no": "REG-CUSTOM-JSS",
        "term_id": str(term_id),
        "subject": ["Hausa"],
        "score_Hausa": "77",
    }, follow_redirects=True)
    assert b"Choose subjects from the list for this class level." in rejected.data

    accepted = admin_client.post("/results", data={
        "reg_no": "REG-CUSTOM-JSS",
        "term_id": str(term_id),
        "subject": ["English Studies"],
        "score_English Studies": "88",
    }, follow_redirects=True)
    assert b"Results saved for Configured Subject Student." in accepted.data
    assert database.get_results_for_term(
        school_id, school["academic_year_id"], term_id
    )[0]["subjects"] == {"English Studies": 88}

    database.save_school_class_subjects(
        school_id, jss_one["id"], ["Yoruba"]
    )
    historical_page = admin_client.get(
        f"/results?selected=REG-CUSTOM-JSS&term_id={term_id}"
    )
    assert b"Previously recorded subjects (no longer offered)" in historical_page.data
    assert b"English Studies" in historical_page.data
    historical_score = admin_client.post("/results", data={
        "reg_no": "REG-CUSTOM-JSS",
        "term_id": str(term_id),
        "subject": ["English Studies"],
        "score_English Studies": "89",
    }, follow_redirects=True)
    assert b"Results saved for Configured Subject Student." in historical_score.data
    assert database.get_results_for_term(
        school_id, school["academic_year_id"], term_id
    )[0]["subjects"] == {"English Studies": 89}

    primary_one = next(
        row for row in database.get_school_classes(school_id)
        if row["name"] == "Primary 1"
    )
    assert database.get_school_class_subjects(
        school_id, primary_one["id"]
    ) is None


def test_teacher_score_entry_obeys_class_subject_offerings(teacher_client):
    client, school, teacher_id, primary_one_id = teacher_client
    database.save_school_class_subjects(
        school["school_id"], primary_one_id, ["Mathematics"]
    )
    student_id = database.create_student(
        school["school_id"], "REG-TEACHER-SUBJECT", "Teacher Subject Student"
    )
    database.enroll_student(
        student_id, primary_one_id, school["academic_year_id"], "2026-09-03"
    )
    term_id = database.create_term(
        school["academic_year_id"], "First Term", 1,
        "2026-09-01", "2026-12-18"
    )

    page = client.get(
        f"/teacher/results?class_id={primary_one_id}&term_id={term_id}"
        "&selected=REG-TEACHER-SUBJECT"
    )
    assert page.status_code == 200
    assert b"Mathematics" in page.data
    assert b"value=\"English\"" not in page.data

    rejected = client.post("/teacher/results", data={
        "class_id": str(primary_one_id),
        "term_id": str(term_id),
        "reg_no": "REG-TEACHER-SUBJECT",
        "subject": ["English"],
        "score_English": "80",
    }, follow_redirects=True)
    assert b"Choose subjects from the list for this class level." in rejected.data
    assert database.get_results_for_term(
        school["school_id"], school["academic_year_id"], term_id,
        teacher_id=teacher_id, class_id=primary_one_id
    )[0]["subjects"] == {}


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


def test_legacy_import_requires_class_and_date_and_is_idempotent(admin_client):
    with admin_client.session_transaction() as session:
        school_id = session["school_id"]
    school = database.get_school_context(school_id)
    primary_one = next(
        school_class for school_class in database.get_school_classes(school_id)
        if school_class["name"] == "Primary 1"
    )

    preview = admin_client.get("/students/import-legacy")
    assert preview.status_code == 200
    assert b"Choose a class" in preview.data
    assert b"Enrollment date" in preview.data

    response = admin_client.post("/students/import-legacy", data={
        "class_id_0": str(primary_one["id"]),
        "enrollment_date_0": "2026-09-02",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"1 profiles created, 1 students enrolled" in response.data

    enrolled = database.get_students_for_year(
        school_id, school["academic_year_id"]
    )
    assert len(enrolled) == 1
    assert enrolled[0]["reg_no"] == "REG-TEST-1"
    assert enrolled[0]["class_name"] == "Primary 1"
    assert main.students[0]["subjects"] == {}

    term_id = database.create_term(
        school["academic_year_id"], "First Term", 1,
        "2026-09-01", "2026-12-18"
    )
    results_page = admin_client.get(f"/results?term_id={term_id}")
    assert results_page.status_code == 200
    assert b"REG-TEST-1" in results_page.data

    repeated = admin_client.post("/students/import-legacy", data={
        "class_id_0": str(primary_one["id"]),
        "enrollment_date_0": "2026-09-02",
    }, follow_redirects=True)
    assert b"All legacy students already have an enrollment" in repeated.data
    assert len(database.get_students_for_year(
        school_id, school["academic_year_id"]
    )) == 1


def test_legacy_import_rolls_back_invalid_class_mapping(admin_client):
    with admin_client.session_transaction() as session:
        school_id = session["school_id"]
    school = database.get_school_context(school_id)
    with pytest.raises(ValueError, match="active class"):
        database.import_legacy_students(school_id, school["academic_year_id"], [{
            "name": "Test Student",
            "reg_no": "REG-TEST-1",
            "class_id": "9999",
            "enrollment_date": "2026-09-02",
        }])
    assert database.get_students_for_year(
        school_id, school["academic_year_id"]
    ) == []


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
