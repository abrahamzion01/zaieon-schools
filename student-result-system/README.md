# ZAIEON Schools

### Empowering Schools. Developing Futures.

ZAIEON Schools is a Python-based school management desktop application designed to help primary and secondary schools manage student information, academic results, teacher assignments and essential school operations.

The project is being developed with a focus on simplifying school administration, improving academic record management and creating a connected digital environment for schools.

## Current Features

- Student registration and record management.
- Student identification using unique registration numbers.
- Examination score entry and validation.
- JSS and SSS score entry using grouped NERDC subject choices and electives.
- School-specific subject offerings configurable for each class.
- Automatic calculation of total and average scores.
- Automatic grade assignment.
- Individual student result viewing.
- Student search functionality.
- Best and lowest performing student identification.
- Administrator, teacher and student authentication.
- Teacher class assignment.
- Class-based attendance management.
- Attendance reports by academic-year date range with per-student attendance rates.
- Create and activate school academic years, with terms prepared per year.
- Enroll returning students into current-year classes with next-class suggestions.
- Carry selected teacher-class assignments into a new academic year.
- Persistent data storage.

## School Structure

The system supports the Nigerian primary and secondary school structure:

- Primary 1–6
- JSS 1–3
- SS 1–3

## User Roles

**Administrator**
- Manage school operations.
- Manage student records.
- Manage teacher accounts and class assignments.

**Teacher**
- Access assigned classes.
- Enter and update term results for assigned classes.
- Support academic and attendance management.

**Student**
- Access personal academic information and relevant school records.

## Technologies

- Python 3
- Tkinter – Desktop graphical user interface.
- SQLite – Database management.
- JSON – Student record storage.
- Pytest – Automated testing.

## Data Model Foundation

SQLite now includes school-scoped records for schools, academic years, terms,
classes, students, and yearly class enrollments. Registration numbers are unique
within each school, enrollment links are constrained to the same school, and
term and enrollment dates are checked against their academic year.

The first administrator sets up the school and current academic year in the web
app. New student registration now creates the login, student profile, and class
enrollment together; teacher assignments are linked to a school, class, and
academic year. Existing `students.json` records and legacy attendance and
teacher-class tables are preserved. Web results are stored in SQLite per
student enrollment and academic term; result entry is limited to students
enrolled in the school's current academic year. The admin can review and import
legacy JSON students by assigning a class and confirming each enrollment date.
The JSON file is left intact, and its old scores are not assigned a term because
the source records do not identify one.

## Project Structure

```text
student-result-system/
│
├── gui.py
├── database.py
├── students.json
├── test_authentication.py
├── backup/
└── README.md
```

## Installation and Setup

### 1. Clone the repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
```

### 2. Enter the project directory

```bash
cd student-result-system
```

### 3. Run the application

```bash
python gui.py
```

Python 3 is required. Tkinter is also required for the graphical interface.

## Project Vision
