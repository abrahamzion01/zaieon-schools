
from datetime import date
from functools import wraps
import sqlite3

from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, session
)

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import authentication
import database
import curriculum
import main
import secrets

app = Flask(__name__)
app.secret_key = "change-this-to-a-secure-random-secret-before-deployment"
main.load_students()

STANDARD_CLASSES = [
    "Primary 1", "Primary 2", "Primary 3",
    "Primary 4", "Primary 5", "Primary 6",
    "JSS 1", "JSS 2", "JSS 3",
    "SS 1", "SS 2", "SS 3"
]


def _scores_for_selected_subjects(allowed_subjects):
    selected = list(dict.fromkeys(request.form.getlist("subject")))
    if not selected:
        raise ValueError("Select at least one subject for this student.")
    if not set(selected) <= set(allowed_subjects):
        raise ValueError("Choose subjects from the list for this class level.")

    scores = {}
    for subject in selected:
        try:
            score = float(request.form.get(f"score_{subject}", ""))
        except ValueError as error:
            raise ValueError(f"Enter a score for {subject}.") from error
        if not 0 <= score <= 100:
            raise ValueError(f"{subject} score must be between 0 and 100.")
        scores[subject] = score
    return scores


def _subject_groups_for_school_class(school_id, class_id, class_name,
                                     previously_recorded=()):
    groups, defaults = curriculum.subject_groups_for_class(
        class_name, main.SUBJECTS
    )
    catalog = curriculum.flatten_subject_groups(groups)
    if class_id is None:
        return groups, defaults, set(catalog)
    configured = database.get_school_class_subjects(school_id, class_id)
    offered = set(catalog if configured is None else configured)
    filtered_groups = []
    for group in groups:
        subjects = [subject for subject in group["subjects"] if subject in offered]
        if subjects:
            filtered_groups.append({"name": group["name"], "subjects": subjects})
    historical = list(dict.fromkeys(
        subject for subject in previously_recorded if subject not in offered
    ))
    if historical:
        filtered_groups.append({
            "name": "Previously recorded subjects (no longer offered)",
            "subjects": historical,
        })
    allowed = offered | set(historical)
    return filtered_groups, [subject for subject in defaults if subject in offered], allowed


def _saved_subjects_for_student(school_id, academic_year_id, term_id,
                                class_id, registration):
    if not term_id:
        return []
    results = database.get_results_for_term(
        school_id, academic_year_id, term_id, class_id=class_id
    )
    student = next((row for row in results
                    if row["reg_no"].casefold() == registration.casefold()), None)
    return list(student["subjects"]) if student else []


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))

        if session.get("role") != "admin":
            flash("You are not authorized to access this page.")
            return redirect(url_for("dashboard"))

        if session.get("must_change_password"):
            return "Password change page coming next."

        memberships = database.get_school_memberships(session["user_id"])
        if not memberships:
            if database.get_school_count() == 0:
                return redirect(url_for("school_setup"))
            flash("This administrator account is not linked to a school.")
            return redirect(url_for("dashboard"))

        school_ids = {membership["school_id"] for membership in memberships}
        school_id = session.get("school_id")
        if school_id not in school_ids:
            if len(school_ids) == 1:
                school_id = next(iter(school_ids))
                session["school_id"] = school_id
            else:
                return redirect(url_for("select_school"))

        if database.get_school_context(school_id) is None:
            flash("Set a current academic year before using school records.")
            return redirect(url_for("dashboard"))

        return view(*args, **kwargs)

    return wrapped


def teacher_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if session.get("role") != "teacher":
            flash("This page is for teachers.")
            return redirect(url_for("dashboard"))
        if session.get("must_change_password"):
            return "Password change page coming next."

        memberships = [
            row for row in database.get_school_memberships(session["user_id"])
            if row["role"] == "teacher"
        ]
        if not memberships:
            flash("Ask a school administrator to assign you to a class first.")
            return redirect(url_for("dashboard"))
        school_ids = {row["school_id"] for row in memberships}
        school_id = session.get("school_id")
        if school_id not in school_ids:
            if len(school_ids) == 1:
                school_id = next(iter(school_ids))
                session["school_id"] = school_id
            else:
                return redirect(url_for("select_school"))
        if database.get_school_context(school_id) is None:
            flash("The school has not set a current academic year yet.")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = authentication.login_user(username, password)

        if user is None:
            flash("Invalid username or password.")
            return redirect(url_for("login"))

        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        session["must_change_password"] = bool(
            user["must_change_password"]
        )

        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["must_change_password"]:
        return "Password change page coming next."

    role = session["role"]

    if role == "teacher":
        memberships = [
            row for row in database.get_school_memberships(session["user_id"])
            if row["role"] == "teacher"
        ]
        school_ids = {membership["school_id"] for membership in memberships}
        school_id = session.get("school_id")
        if school_id not in school_ids:
            if len(school_ids) == 1:
                school_id = next(iter(school_ids))
                session["school_id"] = school_id
            elif len(school_ids) > 1:
                return redirect(url_for("select_school"))

        school = database.get_school_context(school_id) if school_id else None
        assignments = database.get_teacher_class_assignments(
            school_id, school["academic_year_id"], session["user_id"]
        ) if school else []
        return render_template(
            "teacher_dashboard.html", school=school, assignments=assignments
        )

    if role == "admin":
        memberships = database.get_school_memberships(session["user_id"])
        if not memberships:
            if database.get_school_count() == 0:
                return redirect(url_for("school_setup"))
            return render_template(
                "school_setup.html", already_configured=True,
                classes=STANDARD_CLASSES
            )
        school_ids = {membership["school_id"] for membership in memberships}
        if session.get("school_id") not in school_ids:
            if len(school_ids) == 1:
                session["school_id"] = next(iter(school_ids))
            else:
                return redirect(url_for("select_school"))

    return render_template("dashboard.html")


@app.route("/school-setup", methods=["GET", "POST"])
def school_setup():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "admin":
        flash("Only an administrator can set up a school.")
        return redirect(url_for("dashboard"))
    if database.get_school_memberships(session["user_id"]):
        return redirect(url_for("dashboard"))

    already_configured = database.get_school_count() > 0
    if request.method == "POST" and not already_configured:
        try:
            database.setup_initial_school(
                session["user_id"],
                request.form.get("school_name", ""),
                request.form.get("school_code", ""),
                request.form.get("year_name", ""),
                request.form.get("start_date", ""),
                request.form.get("end_date", ""),
                STANDARD_CLASSES,
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            flash(str(error))
        else:
            flash("School setup is complete. You can now register students and assign teachers.")
            return redirect(url_for("dashboard"))

    return render_template(
        "school_setup.html",
        already_configured=already_configured,
        classes=STANDARD_CLASSES,
    )


@app.route("/select-school", methods=["GET", "POST"])
def select_school():
    if "user_id" not in session:
        return redirect(url_for("login"))
    role = session.get("role")
    if role not in {"admin", "teacher"}:
        flash("Your account cannot select a school workspace.")
        return redirect(url_for("dashboard"))

    memberships = [
        row for row in database.get_school_memberships(session["user_id"])
        if row["role"] == role
    ]
    if request.method == "POST":
        try:
            school_id = int(request.form.get("school_id", ""))
        except ValueError:
            school_id = None
        if school_id not in {row["school_id"] for row in memberships}:
            flash("Choose a school linked to your account.")
        else:
            session["school_id"] = school_id
            return redirect(url_for("dashboard"))

    return render_template("select_school.html", schools=memberships)


@app.route("/results", methods=["GET", "POST"])
@admin_required
def manage_results():
    school_id = session["school_id"]
    school = database.get_school_context(school_id)
    terms = database.get_terms_for_year(school["academic_year_id"])
    students = database.get_students_for_year(
        school_id, school["academic_year_id"]
    )

    if request.method == "POST":
        registration = request.form.get("reg_no", "").strip()
        selected_term = request.form.get("term_id", "")
        if not terms:
            flash("Set up an academic term before entering results.")
            return redirect(url_for("manage_terms"))

        enrolled_student = next(
            (student for student in students
             if student["reg_no"].casefold() == registration.casefold()),
            None,
        )
        if enrolled_student is None:
            flash("Choose a student enrolled in the current academic year.")
            return redirect(url_for("manage_results", term_id=selected_term))
        previous_subjects = _saved_subjects_for_student(
            school_id, school["academic_year_id"], selected_term,
            enrolled_student["class_id"], registration,
        )
        _, _, allowed_subjects = _subject_groups_for_school_class(
            school_id, enrolled_student["class_id"],
            enrolled_student["class_name"], previous_subjects,
        )
        try:
            scores = _scores_for_selected_subjects(allowed_subjects)
        except ValueError as error:
            flash(str(error))
            return redirect(url_for(
                "manage_results", selected=registration, term_id=selected_term
            ))

        try:
            student = database.create_student_term_results(
                school_id, school["academic_year_id"], registration,
                selected_term, scores, session["user_id"],
                replace_existing=True
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            flash(str(error) or "Unable to save these results.")
            return redirect(url_for(
                "manage_results", selected=registration, term_id=selected_term
            ))
        flash(f"Results saved for {student['name']}.")
        return redirect(url_for(
            "manage_results", selected=registration, term_id=selected_term
        ))

    selected_reg = request.args.get("selected", "")
    try:
        selected_term_id = int(request.args.get("term_id", ""))
    except ValueError:
        selected_term_id = None
    if selected_term_id not in {term["id"] for term in terms}:
        selected_term_id = terms[0]["id"] if terms else None
    results = database.get_results_for_term(
        school_id, school["academic_year_id"], selected_term_id
    ) if selected_term_id else []
    selected_student = next(
        (student for student in results
         if student["reg_no"].lower() == selected_reg.lower()),
        None
    )
    selected_enrollment = next(
        (student for student in students
         if student["reg_no"].casefold() == selected_reg.casefold()),
        None,
    )
    subject_groups, default_subjects, _ = _subject_groups_for_school_class(
        school_id,
        selected_enrollment["class_id"] if selected_enrollment else None,
        selected_enrollment["class_name"] if selected_enrollment else "",
        selected_student["subjects"].keys() if selected_student else (),
    )
    subject_guidance = curriculum.subject_guidance_for_class(
        selected_enrollment["class_name"] if selected_enrollment else ""
    )
    for student in results:
        if student["average"] is not None:
            student["grade"] = main.calculate_grade(student["average"])

    return render_template(
        "admin_section.html",
        page="results",
        page_title="Manage Results",
        page_description="Enter scores and review student performance.",
        academic_year_name=school["academic_year_name"],
        students=students,
        terms=terms,
        selected_term_id=selected_term_id,
        results=results,
        subject_groups=subject_groups,
        default_subjects=default_subjects,
        subject_guidance=subject_guidance,
        selected_reg=selected_reg,
        selected_student=selected_student
    )


@app.route("/subjects", methods=["GET", "POST"])
@admin_required
def manage_subjects():
    school_id = session["school_id"]
    classes = database.get_school_classes(school_id)
    selected_class_id = request.args.get("class_id", "")
    if request.method == "POST":
        selected_class_id = request.form.get("class_id", "")
    try:
        selected_class_id = int(selected_class_id)
    except (TypeError, ValueError):
        selected_class_id = (
            None if request.method == "POST"
            else classes[0]["id"] if classes else None
        )
    selected_class = next(
        (school_class for school_class in classes
         if school_class["id"] == selected_class_id),
        None,
    )

    if request.method == "POST":
        if selected_class is None:
            flash("Choose an active class in this school.")
        else:
            groups, _ = curriculum.subject_groups_for_class(
                selected_class["name"], main.SUBJECTS
            )
            allowed = set(curriculum.flatten_subject_groups(groups))
            selected_subjects = list(dict.fromkeys(
                request.form.getlist("subject")
            ))
            if not selected_subjects:
                flash("Choose at least one subject for this class.")
            elif not set(selected_subjects) <= allowed:
                flash("Choose subjects from the list for this class level.")
            else:
                database.save_school_class_subjects(
                    school_id, selected_class_id, selected_subjects
                )
                flash(f"Subject offerings saved for {selected_class['name']}.")
                return redirect(url_for(
                    "manage_subjects", class_id=selected_class_id
                ))

    subject_groups = []
    configured = False
    if selected_class:
        subject_groups, _ = curriculum.subject_groups_for_class(
            selected_class["name"], main.SUBJECTS
        )
        saved_subjects = database.get_school_class_subjects(
            school_id, selected_class_id
        )
        configured = saved_subjects is not None
        selected_subjects = set(
            saved_subjects if configured
            else curriculum.flatten_subject_groups(subject_groups)
        )
    else:
        selected_subjects = set()

    school = database.get_school_context(school_id)
    return render_template(
        "admin_section.html",
        page="subjects",
        page_title="Subject Offerings",
        page_description=f"Choose the subjects offered in each class at {school['school_name']}.",
        classes=classes,
        selected_class=selected_class,
        selected_class_id=selected_class_id,
        subject_groups=subject_groups,
        selected_subjects=selected_subjects,
        subject_settings_saved=configured,
    )


@app.route("/teacher/results", methods=["GET", "POST"])
@teacher_required
def teacher_results():
    school_id = session["school_id"]
    school = database.get_school_context(school_id)
    academic_year_id = school["academic_year_id"]
    teacher_id = session["user_id"]
    assignments = database.get_teacher_class_assignments(
        school_id, academic_year_id, teacher_id
    )
    assigned_class_ids = {assignment["class_id"] for assignment in assignments}
    terms = database.get_terms_for_year(academic_year_id)

    if request.method == "POST":
        registration = request.form.get("reg_no", "").strip()
        try:
            class_id = int(request.form.get("class_id", ""))
            term_id = int(request.form.get("term_id", ""))
        except ValueError:
            class_id = term_id = None
        if class_id not in assigned_class_ids:
            flash("Choose one of your assigned classes.")
            return redirect(url_for("teacher_results"))
        if term_id not in {term["id"] for term in terms}:
            flash("Choose a term in the current academic year.")
            return redirect(url_for("teacher_results", class_id=class_id))

        assignment = next(
            assignment for assignment in assignments
            if assignment["class_id"] == class_id
        )
        previous_subjects = _saved_subjects_for_student(
            school_id, academic_year_id, term_id, class_id, registration
        )
        _, _, allowed_subjects = _subject_groups_for_school_class(
            school_id, class_id, assignment["class_name"], previous_subjects
        )
        try:
            scores = _scores_for_selected_subjects(allowed_subjects)
        except ValueError as error:
            flash(str(error))
            return redirect(url_for(
                "teacher_results", class_id=class_id, term_id=term_id,
                selected=registration
            ))

        try:
            student = database.create_student_term_results(
                school_id, academic_year_id, registration, term_id, scores,
                teacher_id, teacher_id=teacher_id, class_id=class_id,
                replace_existing=True
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            flash(str(error) or "Unable to save these results.")
        else:
            flash(f"Results saved for {student['name']}.")
        return redirect(url_for(
            "teacher_results", class_id=class_id, term_id=term_id,
            selected=registration
        ))

    try:
        selected_class_id = int(request.args.get("class_id", ""))
    except ValueError:
        selected_class_id = None
    if selected_class_id not in assigned_class_ids:
        selected_class_id = assignments[0]["class_id"] if assignments else None
    selected_assignment = next(
        (assignment for assignment in assignments
         if assignment["class_id"] == selected_class_id),
        None,
    )
    try:
        selected_term_id = int(request.args.get("term_id", ""))
    except ValueError:
        selected_term_id = None
    if selected_term_id not in {term["id"] for term in terms}:
        selected_term_id = terms[0]["id"] if terms else None

    students = database.get_students_for_year(
        school_id, academic_year_id, teacher_id, selected_class_id
    ) if selected_class_id else []
    results = database.get_results_for_term(
        school_id, academic_year_id, selected_term_id,
        teacher_id, selected_class_id
    ) if selected_class_id and selected_term_id else []
    selected_reg = request.args.get("selected", "")
    selected_student = next(
        (student for student in results
         if student["reg_no"].lower() == selected_reg.lower()),
        None,
    )
    subject_groups, default_subjects, _ = _subject_groups_for_school_class(
        school_id,
        selected_class_id,
        selected_assignment["class_name"] if selected_assignment else "",
        selected_student["subjects"].keys() if selected_student else (),
    )
    subject_guidance = curriculum.subject_guidance_for_class(
        selected_assignment["class_name"] if selected_assignment else ""
    )
    for student in results:
        if student["average"] is not None:
            student["grade"] = main.calculate_grade(student["average"])

    return render_template(
        "teacher_results.html",
        school=school,
        assignments=assignments,
        terms=terms,
        students=students,
        results=results,
        subject_groups=subject_groups,
        default_subjects=default_subjects,
        subject_guidance=subject_guidance,
        selected_class_id=selected_class_id,
        selected_term_id=selected_term_id,
        selected_reg=selected_reg,
        selected_student=selected_student,
    )


@app.route("/terms", methods=["GET", "POST"])
@admin_required
def manage_terms():
    school = database.get_school_context(session["school_id"])
    if request.method == "POST":
        try:
            database.create_term(
                school["academic_year_id"],
                request.form.get("name", ""),
                request.form.get("sequence", ""),
                request.form.get("start_date", ""),
                request.form.get("end_date", ""),
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            message = str(error)
            if isinstance(error, sqlite3.IntegrityError):
                message = "That term name or sequence is already in use."
            flash(message)
        else:
            flash("Academic term added.")
            return redirect(url_for("manage_terms"))

    return render_template(
        "admin_section.html",
        page="terms",
        page_title="Academic Terms",
        page_description=f"Set terms for {school['academic_year_name']}.",
        academic_year=school,
        terms=database.get_terms_for_year(school["academic_year_id"]),
    )


@app.route("/students/import-legacy", methods=["GET", "POST"])
@admin_required
def import_legacy_students():
    school_id = session["school_id"]
    school = database.get_school_context(school_id)
    classes = database.get_school_classes(school_id)
    records = main.students if isinstance(main.students, list) else []

    if request.method == "POST":
        preview = database.preview_legacy_student_import(
            school_id, school["academic_year_id"], records
        )
        pending = [record for record in preview if record["status"] != "enrolled"]
        import_records = []
        for record in pending:
            index = record["index"]
            legacy_record = records[index]
            import_records.append({
                "reg_no": legacy_record.get("reg_no"),
                "name": legacy_record.get("name"),
                "class_id": request.form.get(f"class_id_{index}", ""),
                "enrollment_date": request.form.get(f"enrollment_date_{index}", ""),
            })
        try:
            counts = database.import_legacy_students(
                school_id, school["academic_year_id"], import_records
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            flash(str(error) or "The legacy students could not be imported.")
        else:
            flash(
                f"Import complete: {counts['created']} profiles created, "
                f"{counts['enrolled']} students enrolled, "
                f"{counts['skipped']} already enrolled and skipped."
            )
            return redirect(url_for("import_legacy_students"))

    preview = database.preview_legacy_student_import(
        school_id, school["academic_year_id"], records
    )
    return render_template(
        "admin_section.html",
        page="legacy_import",
        page_title="Import Legacy Students",
        page_description="Review students from the existing student records file.",
        legacy_students=preview,
        classes=classes,
        academic_year=school,
    )


@app.route("/teachers", methods=["GET", "POST"])
@admin_required
def manage_teachers():
    database.initialize_database()
    school_id = session["school_id"]
    school = database.get_school_context(school_id)
    classes = database.get_school_classes(school_id)
    teachers = database.get_teachers_for_school(school_id)

    if request.method == "POST":
        try:
            teacher_id = int(request.form.get("teacher_id", ""))
            class_id = int(request.form.get("class_id", ""))
        except ValueError:
            teacher_id = None
            class_id = None

        teacher = next(
            (record for record in teachers if record["id"] == teacher_id),
            None
        )
        school_class = next(
            (record for record in classes if record["id"] == class_id), None
        )

        if teacher is None or school_class is None:
            flash("Choose a valid teacher and class.")
        else:
            try:
                database.assign_teacher_to_school_class(
                    school_id, teacher_id, class_id, school["academic_year_id"]
                )
            except sqlite3.IntegrityError:
                flash("That teacher already has this class assigned for the current year.")
            except ValueError as error:
                flash(str(error))
            else:
                flash(f"{school_class['name']} assigned to {teacher['username']}.")

        return redirect(url_for("manage_teachers"))

    assignments = database.get_teacher_class_assignments(
        school_id, school["academic_year_id"]
    )

    return render_template(
        "admin_section.html",
        page="teachers",
        page_title="Manage Teachers",
        page_description="Review teachers and assign their classes.",
        teachers=teachers,
        classes=classes,
        assignments=assignments
    )


@app.route("/attendance")
@admin_required
def attendance_overview():
    school_id = session["school_id"]
    classes = database.get_school_classes(school_id)
    class_names = {school_class["name"] for school_class in classes}
    attendance_date = request.args.get("date", date.today().isoformat())
    try:
        date.fromisoformat(attendance_date)
    except ValueError:
        attendance_date = date.today().isoformat()
        flash("Choose a valid attendance date.")

    selected_class = request.args.get("class_name", "")
    if selected_class and selected_class not in class_names:
        selected_class = ""
        flash("Choose a valid class.")

    database.initialize_database()
    connection = database.get_connection()
    try:
        records = connection.execute("""
            SELECT attendance.reg_no, attendance.class_name,
                   attendance.status, users.username AS marked_by
            FROM attendance
            LEFT JOIN users ON users.id = attendance.marked_by
            WHERE attendance.attendance_date = ?
              AND (? = '' OR attendance.class_name = ?)
            ORDER BY attendance.class_name, attendance.reg_no
        """, (attendance_date, selected_class, selected_class)).fetchall()
    finally:
        connection.close()

    return render_template(
        "admin_section.html",
        page="attendance",
        page_title="Attendance",
        page_description="Review attendance records by date and class.",
        classes=classes,
        attendance_date=attendance_date,
        selected_class=selected_class,
        attendance_records=records
    )

@app.route("/register", methods=["GET", "POST"])
@admin_required
def register_student():
    school_id = session["school_id"]
    school = database.get_school_context(school_id)
    classes = database.get_school_classes(school_id)
    enrollment_date_default = min(
        max(date.today(), date.fromisoformat(school["start_date"])),
        date.fromisoformat(school["end_date"]),
    ).isoformat()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        registration = request.form.get("reg_no", "").strip()
        username = request.form.get("username", "").strip()
        enrollment_date = request.form.get("enrollment_date", "").strip()
        try:
            enrolled_on = date.fromisoformat(enrollment_date)
        except ValueError:
            enrolled_on = None
        try:
            class_id = int(request.form.get("class_id", ""))
        except ValueError:
            class_id = None
        school_class = next(
            (record for record in classes if record["id"] == class_id), None
        )

        if (not all([name, registration, username]) or school_class is None
                or enrolled_on is None):
            flash("Please complete all fields.")
            return redirect(url_for("register_student"))

        if not (date.fromisoformat(school["start_date"])
                <= enrolled_on <= date.fromisoformat(school["end_date"])):
            flash("Enrollment date must fall within the current academic year.")
            return redirect(url_for("register_student"))

        if not any(character.isalpha() for character in name):
            flash("Please enter a valid student name.")
            return redirect(url_for("register_student"))

        if any(
            student.get("reg_no", "").lower() == registration.lower()
            for student in main.students
        ):
            flash("That registration number already exists.")
            return redirect(url_for("register_student"))

        temporary_password = secrets.token_urlsafe(9)

        user_id = authentication.register_student_with_enrollment(
            username,
            temporary_password,
            registration,
            name,
            school_id,
            class_id,
            school["academic_year_id"],
            enrolled_on.isoformat()
        )

        if user_id is None:
            flash("Account creation failed. Check the username and registration number.")
            return redirect(url_for("register_student"))

        main.students.append({
            "name": name,
            "reg_no": registration,
            "class_name": school_class["name"],
            "subjects": {},
            "total": None,
            "average": None,
            "grade": None
        })

        main.save_students()

        return render_template(
            "register.html",
            temporary_password=temporary_password,
            student_name=name,
            username=username,
            classes=classes,
            enrollment_date_default=enrollment_date_default
        )

    return render_template(
        "register.html",
        classes=classes,
        enrollment_date_default=enrollment_date_default,
    )

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
