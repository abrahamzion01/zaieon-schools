
from datetime import date
from functools import wraps

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
import main
import secrets

app = Flask(__name__)
app.secret_key = "change-this-to-a-secure-random-secret-before-deployment"
main.load_students()

SCHOOL_CLASSES = [
    "Primary 1", "Primary 2", "Primary 3",
    "Primary 4", "Primary 5", "Primary 6",
    "JSS 1", "JSS 2", "JSS 3",
    "SS 1", "SS 2", "SS 3"
]


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

    return render_template("dashboard.html")


@app.route("/results", methods=["GET", "POST"])
@admin_required
def manage_results():
    if request.method == "POST":
        registration = request.form.get("reg_no", "").strip()
        student = next(
            (record for record in main.students
             if record.get("reg_no", "").lower() == registration.lower()),
            None
        )

        if student is None:
            flash("Select a registered student before entering scores.")
            return redirect(url_for("manage_results"))

        scores = {}
        try:
            for subject in main.SUBJECTS:
                score = float(request.form.get(subject, ""))
                if not 0 <= score <= 100:
                    raise ValueError
                scores[subject] = score
        except ValueError:
            flash("Enter a valid score from 0 to 100 for every subject.")
            return redirect(url_for("manage_results", selected=registration))

        total = sum(scores.values())
        average = total / len(main.SUBJECTS)
        student.update({
            "subjects": scores,
            "total": total,
            "average": average,
            "grade": main.calculate_grade(average)
        })
        main.save_students()
        flash(f"Results saved for {student['name']}.")
        return redirect(url_for("manage_results", selected=registration))

    selected_reg = request.args.get("selected", "")
    selected_student = next(
        (record for record in main.students
         if record.get("reg_no", "").lower() == selected_reg.lower()),
        None
    )

    return render_template(
        "admin_section.html",
        page="results",
        page_title="Manage Results",
        page_description="Enter scores and review student performance.",
        students=main.students,
        subjects=main.SUBJECTS,
        selected_reg=selected_reg,
        selected_student=selected_student
    )


@app.route("/teachers", methods=["GET", "POST"])
@admin_required
def manage_teachers():
    database.initialize_database()
    teachers = database.get_teachers()

    if request.method == "POST":
        try:
            teacher_id = int(request.form.get("teacher_id", ""))
        except ValueError:
            teacher_id = None

        class_name = request.form.get("class_name", "")
        teacher = next(
            (record for record in teachers if record["id"] == teacher_id),
            None
        )

        if teacher is None or class_name not in SCHOOL_CLASSES:
            flash("Choose a valid teacher and class.")
        elif database.assign_teacher_to_class(teacher_id, class_name):
            flash(f"{class_name} assigned to {teacher['username']}.")
        else:
            flash("That teacher already has this class assigned.")

        return redirect(url_for("manage_teachers"))

    connection = database.get_connection()
    try:
        assignments = connection.execute("""
            SELECT users.username, teacher_classes.class_name
            FROM teacher_classes
            JOIN users ON users.id = teacher_classes.teacher_id
            ORDER BY users.username, teacher_classes.class_name
        """).fetchall()
    finally:
        connection.close()

    return render_template(
        "admin_section.html",
        page="teachers",
        page_title="Manage Teachers",
        page_description="Review teachers and assign their classes.",
        teachers=teachers,
        classes=SCHOOL_CLASSES,
        assignments=assignments
    )


@app.route("/attendance")
@admin_required
def attendance_overview():
    attendance_date = request.args.get("date", date.today().isoformat())
    try:
        date.fromisoformat(attendance_date)
    except ValueError:
        attendance_date = date.today().isoformat()
        flash("Choose a valid attendance date.")

    selected_class = request.args.get("class_name", "")
    if selected_class and selected_class not in SCHOOL_CLASSES:
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
        classes=SCHOOL_CLASSES,
        attendance_date=attendance_date,
        selected_class=selected_class,
        attendance_records=records
    )

@app.route("/register", methods=["GET", "POST"])
def register_student():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        flash("You are not authorized to register students.")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        registration = request.form.get("reg_no", "").strip()
        student_class = request.form.get("class_name", "").strip()
        username = request.form.get("username", "").strip()

        school_classes = [
            "Primary 1", "Primary 2", "Primary 3",
            "Primary 4", "Primary 5", "Primary 6",
            "JSS 1", "JSS 2", "JSS 3",
            "SS 1", "SS 2", "SS 3"
        ]

        if not all([name, registration, student_class, username]):
            flash("Please complete all fields.")
            return redirect(url_for("register_student"))

        if not any(character.isalpha() for character in name):
            flash("Please enter a valid student name.")
            return redirect(url_for("register_student"))

        if student_class not in school_classes:
            flash("Please select a valid class.")
            return redirect(url_for("register_student"))

        if any(
            student.get("reg_no", "").lower() == registration.lower()
            for student in main.students
        ):
            flash("That registration number already exists.")
            return redirect(url_for("register_student"))

        temporary_password = secrets.token_urlsafe(9)

        registered = authentication.register_user(
            username,
            temporary_password,
            "student",
            registration
        )

        if not registered:
            flash("Account creation failed. Check the username and registration number.")
            return redirect(url_for("register_student"))

        main.students.append({
            "name": name,
            "reg_no": registration,
            "class_name": student_class,
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
            username=username
        )

    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
