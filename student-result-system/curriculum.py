"""Subject choices based on the NERDC secondary curriculum offerings."""

JUNIOR_CORE = [
    "English Studies",
    "Mathematics",
    "Intermediate Science",
    "Physical & Health Education",
    "Digital Technologies",
    "Nigerian History",
    "Social and Citizenship Studies",
    "Cultural & Creative Arts",
    "Business Studies",
]

JUNIOR_GROUPS = [
    {"name": "Core subjects", "subjects": JUNIOR_CORE},
    {"name": "Choose one Nigerian language", "subjects": ["Hausa", "Igbo", "Yoruba"]},
    {"name": "Religious studies (choose one)", "subjects": [
        "Christian Religious Studies", "Islamic Studies",
    ]},
    {"name": "Choose one trade subject", "subjects": [
        "Solar Photovoltaic Installation and Maintenance",
        "Fashion Design and Garment Making",
        "Livestock Farming",
        "Beauty and Cosmetology",
        "Computer Hardware and GSM Repairs",
        "Horticulture and Crop Production",
    ]},
    {"name": "Optional languages", "subjects": ["French", "Arabic Language"]},
]

SENIOR_CORE = [
    "English Language",
    "General Mathematics",
    "Citizenship and Heritage Studies",
    "Digital Technologies",
]

SENIOR_GROUPS = [
    {"name": "Core and compulsory subjects", "subjects": SENIOR_CORE},
    {"name": "Science", "subjects": [
        "Biology", "Chemistry", "Physics", "Agriculture",
        "Further Mathematics", "Physical Education", "Health Education",
        "Foods & Nutrition", "Geography", "Technical Drawing",
    ]},
    {"name": "Humanities", "subjects": [
        "Nigerian History", "Government", "Christian Religious Studies",
        "Islamic Studies", "Hausa", "Igbo", "Yoruba", "French", "Arabic",
        "Visual Arts", "Music", "Literature in English", "Home Management",
        "Catering Craft",
    ]},
    {"name": "Business", "subjects": [
        "Accounting", "Commerce", "Marketing", "Economics",
    ]},
    {"name": "Choose one trade subject", "subjects": [
        "Solar Photovoltaic Installation and Maintenance",
        "Fashion Design and Garment Making",
        "Livestock Farming",
        "Beauty and Cosmetology",
        "Computer Hardware and GSM Repairs",
        "Horticulture and Crop Production",
    ]},
]

LEGACY_SECONDARY_SUBJECTS = ["English", "Mathematics", "Biology"]


def subject_groups_for_class(class_name, primary_subjects):
    """Return grouped choices and defaults for the student's class level."""
    normalized = (class_name or "").strip().casefold()
    if normalized.startswith("jss"):
        groups = [dict(group, subjects=list(group["subjects"])) for group in JUNIOR_GROUPS]
        defaults = list(JUNIOR_CORE)
    elif normalized.startswith(("ss", "senior secondary")):
        groups = [dict(group, subjects=list(group["subjects"])) for group in SENIOR_GROUPS]
        defaults = list(SENIOR_CORE)
    else:
        return [{"name": "Subjects", "subjects": list(primary_subjects)}], list(primary_subjects)

    offered = {subject for group in groups for subject in group["subjects"]}
    legacy = [subject for subject in LEGACY_SECONDARY_SUBJECTS if subject not in offered]
    if legacy:
        groups.append({"name": "Previously used subjects", "subjects": legacy})
    return groups, defaults


def subject_guidance_for_class(class_name):
    normalized = (class_name or "").strip().casefold()
    if normalized.startswith("jss"):
        return (
            "NERDC JSS offers 12–14 subjects: the core subjects, one Nigerian "
            "language, one religious studies subject, and one trade subject. "
            "French and Arabic are optional."
        )
    if normalized.startswith(("ss", "senior secondary")):
        return (
            "NERDC SSS offers 8–9 subjects: five core subjects, including one "
            "trade subject, plus 3–4 electives from the fields below."
        )
    return "Select the subjects this student takes and enter a score for each checked subject."


def flatten_subject_groups(groups):
    return [subject for group in groups for subject in group["subjects"]]
