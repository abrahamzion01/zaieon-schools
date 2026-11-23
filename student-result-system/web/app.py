
from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, session
)

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import authentication
import main
import secrets

app = Flask(__name__)
app.secret_key = "change-this-to-a-secure-random-secret-before-deployment"
main.load_students()


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
