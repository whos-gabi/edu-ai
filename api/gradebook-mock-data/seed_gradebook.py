#!/usr/bin/env python3
"""
Reset + seed the gradebook PostgreSQL database with realistic mock data.

Default behavior:
  - Drops schema public (CASCADE), recreates it
  - Applies ./schema.sql
  - Inserts a lot of Faker-based data in FK-safe order

Connection is configured via env vars or CLI args.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import os
import random
import sys
import unicodedata
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import psycopg2
from dotenv import load_dotenv
from faker import Faker
from psycopg2.extras import execute_values


@dataclasses.dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    dbname: str
    user: str
    password: str
    sslmode: str = "prefer"


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    if v is None:
        return default
    v = v.strip()
    return v if v else default


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Reset + seed gradebook DB with Faker data.")

    # DB config
    p.add_argument("--host", default=_env("DB_HOST", "localhost"))
    p.add_argument("--port", type=int, default=int(_env("DB_PORT", "5432") or "5432"))
    p.add_argument("--db", dest="dbname", default=_env("DB_NAME", "gradebook"))
    p.add_argument("--user", default=_env("DB_USER", "postgres"))
    p.add_argument("--password", default=_env("DB_PASSWORD", ""))
    p.add_argument("--sslmode", default=_env("DB_SSLMODE", "prefer"))

    # Behavior
    p.add_argument("--reset", action="store_true", help="Drop & recreate schema public before seeding.")
    p.add_argument(
        "--schema-file",
        default=os.path.join(os.path.dirname(__file__), "schema.sql"),
        help="Path to schema.sql to apply",
    )

    return p.parse_args()


def connect_db(cfg: DbConfig):
    return psycopg2.connect(
        host=cfg.host,
        port=cfg.port,
        dbname=cfg.dbname,
        user=cfg.user,
        password=cfg.password,
        sslmode=cfg.sslmode,
    )


def split_sql_statements(sql_text: str) -> List[str]:
    # Schema file is simple; we keep a minimal splitter that ignores empty chunks & SQL comments lines.
    lines: List[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        lines.append(line)
    sql_text = "\n".join(lines).strip()
    chunks = [c.strip() for c in sql_text.split(";")]
    return [c + ";" for c in chunks if c]


def apply_schema(cur, schema_file: str) -> None:
    with open(schema_file, "r", encoding="utf-8") as f:
        sql_text = f.read()
    for stmt in split_sql_statements(sql_text):
        cur.execute(stmt)


def reset_public_schema(cur) -> None:
    # Hard reset of all tables, sequences, etc.
    cur.execute("DROP SCHEMA IF EXISTS public CASCADE;")
    cur.execute("CREATE SCHEMA public;")
    cur.execute("GRANT ALL ON SCHEMA public TO CURRENT_USER;")
    cur.execute("GRANT ALL ON SCHEMA public TO public;")


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def round_to_quarter(x: float) -> float:
    return round(x * 4) / 4.0


def ascii_slug(s: str, *, allow_dot: bool = False) -> str:
    """
    Convert to lowercase ASCII and keep only [a-z0-9] (and '.' optionally).
    This avoids Romanian diacritics in usernames/emails.
    """
    s_norm = unicodedata.normalize("NFKD", s)
    s_ascii = s_norm.encode("ascii", "ignore").decode("ascii")
    s_ascii = s_ascii.lower()
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789" + ("." if allow_dot else ""))
    out = "".join(ch for ch in s_ascii if ch in allowed)
    out = out.strip(".")
    # collapse duplicate dots
    while ".." in out:
        out = out.replace("..", ".")
    return out or "user"


def romanian_phone_e164(rng: random.Random) -> str:
    """
    Strict Romanian E.164-like mobile format:
      +40 + 9 digits (mobile: +407XXXXXXXX)
    No spaces, no parentheses.
    """
    return "+40" + "7" + "".join(str(rng.randint(0, 9)) for _ in range(8))


def date_years_ago(d: dt.date, years: int) -> dt.date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        # Feb 29 -> Feb 28
        return d.replace(year=d.year - years, month=2, day=28)


def sample_dob_for_grade(today: dt.date, rng: random.Random, grade_num: int) -> dt.date:
    """
    Age sanity requirements (2026-based):
      - grade 11-12: age 18, maximum 19
      - grade 5: age 11, maximum 13
      - others: roughly grade+6, allow a small spread
    """
    if grade_num in (11, 12):
        min_age, max_age = 18, 19
    else:
        min_age = grade_num + 6
        max_age = grade_num + 8

    # older date = years_ago(max_age); younger date = years_ago(min_age)
    start = date_years_ago(today, max_age)
    end = date_years_ago(today, min_age)
    return random_date_between(rng, start, end)


def sample_grade_value(rng: random.Random) -> int:
    """
    Grade distribution requirements:
      - integer values in [1, 10]
      - 75% chance to be in [6, 10]
    """
    if rng.random() < 0.75:
        return rng.randint(6, 10)
    else:
        return rng.randint(1, 10)


def sample_absence_count(rng: random.Random) -> int:
    """
    Absence count requirements (per student per subject):
      - random in [0, 15]
      - 80% chance to be in [0, 4]
    """
    if rng.random() < 0.80:
        return rng.randint(0, 4)
    return rng.randint(0, 15)


def daterange_start_end_for_school_year(today: dt.date) -> Tuple[dt.date, dt.date]:
    # Typical school year: starts Sep 1. If today is before Sep 1, start is Sep 1 previous year.
    if today.month < 9:
        start = dt.date(today.year - 1, 9, 1)
    else:
        start = dt.date(today.year, 9, 1)
    return start, today


def random_date_between(rng: random.Random, start: dt.date, end: dt.date) -> dt.date:
    days = (end - start).days
    return start + dt.timedelta(days=rng.randint(0, max(days, 0)))


def random_date_for_weekday(rng: random.Random, start: dt.date, end: dt.date, weekday_1_to_7: int) -> dt.date:
    # Monday=1..Sunday=7
    if weekday_1_to_7 < 1 or weekday_1_to_7 > 7:
        return random_date_between(rng, start, end)
    target_py_weekday = weekday_1_to_7 - 1  # python Monday=0..Sunday=6
    base = random_date_between(rng, start, end)
    delta = target_py_weekday - base.weekday()
    candidate = base + dt.timedelta(days=delta)
    if candidate < start:
        candidate += dt.timedelta(days=7)
    if candidate > end:
        candidate -= dt.timedelta(days=7)
    if candidate < start or candidate > end:
        return random_date_between(rng, start, end)
    return candidate


def fetch_one_int(cur, query: str, params: Sequence[object] = ()) -> int:
    cur.execute(query, params)
    row = cur.fetchone()
    assert row is not None
    return int(row[0])


def fetch_role_ids(cur) -> Dict[str, int]:
    cur.execute('SELECT role_id, name FROM "roles";')
    return {name: int(role_id) for role_id, name in cur.fetchall()}


def insert_roles(cur) -> Dict[str, int]:
    rows = [("admin",), ("teacher",), ("student",)]
    execute_values(cur, 'INSERT INTO "roles" ("name") VALUES %s ON CONFLICT ("name") DO NOTHING', rows)
    return fetch_role_ids(cur)


def insert_grade_levels(cur) -> List[Tuple[int, int, str]]:
    # returns [(grade_level_id, numeric_level, name)]
    levels: List[Tuple[int, int, str]] = []
    for n in range(1, 13):
        name = f"Clasa {n}"
        levels.append((n, name))  # numeric_level, name
    execute_values(
        cur,
        'INSERT INTO "grade_levels" ("numeric_level","name") VALUES %s ON CONFLICT ("numeric_level") DO NOTHING',
        levels,
    )
    cur.execute('SELECT grade_level_id, numeric_level, COALESCE(name, \'\') FROM "grade_levels" ORDER BY numeric_level;')
    return [(int(a), int(b), str(c)) for a, b, c in cur.fetchall()]


@dataclasses.dataclass(frozen=True)
class SubjectDef:
    name: str
    code: str
    min_grade: int
    max_grade: int


def subject_catalog() -> List[SubjectDef]:
    return [
        SubjectDef("Limba română", "RO", 1, 12),
        SubjectDef("Matematică", "MATH", 1, 12),
        SubjectDef("Limba engleză", "EN", 1, 12),
        SubjectDef("Informatică", "CS", 3, 12),
        SubjectDef("Istorie", "HIST", 4, 12),
        SubjectDef("Geografie", "GEO", 4, 12),
        SubjectDef("Biologie", "BIO", 5, 12),
        SubjectDef("Fizică", "PHYS", 6, 12),
        SubjectDef("Chimie", "CHEM", 7, 12),
        SubjectDef("Educație fizică", "PE", 1, 12),
        SubjectDef("Muzică", "MUS", 1, 8),
        SubjectDef("Desen", "ART", 1, 8),
        SubjectDef("Religie", "REL", 1, 12),
    ]


def insert_subjects(cur, subjects: List[SubjectDef]) -> List[Tuple[int, str, str]]:
    rows = [(s.name, s.code) for s in subjects]
    execute_values(
        cur,
        'INSERT INTO "subjects" ("name","code") VALUES %s ON CONFLICT ("name") DO NOTHING',
        rows,
    )
    cur.execute('SELECT subject_id, name, COALESCE(code, \'\') FROM "subjects" ORDER BY subject_id;')
    return [(int(a), str(b), str(c)) for a, b, c in cur.fetchall()]


def hours_per_week_for_subject(rng: random.Random, subject_code: str, grade: int) -> int:
    # Roughly realistic distribution; tune as needed.
    core = {"RO": (3, 5), "MATH": (3, 5), "EN": (2, 4)}
    if subject_code in core:
        lo, hi = core[subject_code]
        if grade >= 9:
            hi = min(hi + 1, 6)
        return rng.randint(lo, hi)
    if subject_code == "PE":
        return rng.randint(1, 2)
    if subject_code in {"MUS", "ART"}:
        return 1
    if subject_code == "REL":
        return 1
    if subject_code == "CS":
        return rng.randint(1, 2) if grade <= 8 else rng.randint(1, 3)
    if subject_code in {"HIST", "GEO"}:
        return rng.randint(1, 2) if grade <= 8 else rng.randint(1, 3)
    if subject_code in {"BIO", "PHYS", "CHEM"}:
        return rng.randint(1, 2) if grade <= 8 else rng.randint(1, 3)
    return 1


def insert_curriculum_reqs(
    cur,
    rng: random.Random,
    grade_levels: List[Tuple[int, int, str]],
    subjects_db: List[Tuple[int, str, str]],
    subjects_def: List[SubjectDef],
) -> Dict[Tuple[int, int], int]:
    # returns dict: (grade_level_id, subject_id) -> hours_per_week
    subj_by_name = {s.name: s for s in subjects_def}
    rows: List[Tuple[int, int, int]] = []
    hours_map: Dict[Tuple[int, int], int] = {}
    for grade_level_id, numeric_level, _ in grade_levels:
        for subject_id, subject_name, subject_code in subjects_db:
            sdef = subj_by_name.get(subject_name)
            if sdef is None:
                continue
            if not (sdef.min_grade <= numeric_level <= sdef.max_grade):
                continue
            hours = hours_per_week_for_subject(rng, subject_code, numeric_level)
            rows.append((grade_level_id, subject_id, hours))
            hours_map[(grade_level_id, subject_id)] = hours
    execute_values(
        cur,
        'INSERT INTO "curriculum_reqs" ("grade_level_id","subject_id","required_hours_per_week") VALUES %s',
        rows,
        page_size=5000,
    )
    return hours_map


def insert_users(
    cur,
    rows: List[Tuple[int, str, str, str, str, str, Optional[str], dt.datetime]],
) -> List[int]:
    # rows: (role_id, username, email, password_hash, first_name, last_name, phone_number, created_at)
    sql = """
        INSERT INTO "users"
            ("role_id","username","email","password_hash","first_name","last_name","phone_number","created_at")
        VALUES %s
        RETURNING "user_id"
    """
    execute_values(cur, sql, rows, page_size=2000)
    return [int(r[0]) for r in cur.fetchall()]


def insert_teachers(cur, teacher_rows: List[Tuple[int, str, dt.date]]) -> None:
    # (user_id, specialization, hire_date)
    execute_values(
        cur,
        'INSERT INTO "teachers" ("user_id","specialization","hire_date") VALUES %s',
        teacher_rows,
        page_size=2000,
    )


def insert_classes(cur, class_rows: List[Tuple[str, int, Optional[int], str]]) -> List[int]:
    # (name, grade_level_id, homeroom_teacher_id, academic_year)
    sql = """
        INSERT INTO "classes" ("name","grade_level_id","homeroom_teacher_id","academic_year")
        VALUES %s
        RETURNING "class_id"
    """
    execute_values(cur, sql, class_rows, page_size=2000)
    return [int(r[0]) for r in cur.fetchall()]


def insert_students(cur, student_rows: List[Tuple[int, int, dt.date]]) -> None:
    # (user_id, class_id, date_of_birth)
    execute_values(
        cur,
        'INSERT INTO "students" ("user_id","class_id","date_of_birth") VALUES %s',
        student_rows,
        page_size=5000,
    )


def insert_class_courses(cur, rows: List[Tuple[int, int, int]]) -> List[int]:
    # (class_id, subject_id, teacher_id)
    sql = """
        INSERT INTO "class_courses" ("class_id","subject_id","teacher_id")
        VALUES %s
        RETURNING "course_id"
    """
    execute_values(cur, sql, rows, page_size=5000)
    return [int(r[0]) for r in cur.fetchall()]


def insert_timetable(cur, rows: List[Tuple[int, int, dt.time, dt.time, str]]) -> None:
    # (class_course_id, day_of_week, start_time, end_time, room)
    execute_values(
        cur,
        'INSERT INTO "timetable" ("class_course_id","day_of_week","start_time","end_time","room") VALUES %s',
        rows,
        page_size=5000,
    )


def insert_grades(cur, rows: List[Tuple[int, int, int, dt.date, Optional[str]]]) -> None:
    # (student_id, subject_id, grade_value, grade_date, comments)
    execute_values(
        cur,
        'INSERT INTO "grades" ("student_id","subject_id","grade_value","grade_date","comments") VALUES %s',
        rows,
        page_size=10000,
    )


def insert_absences(cur, rows: List[Tuple[int, int, Optional[int], dt.date, bool, Optional[str]]]) -> None:
    # (student_id, subject_id, timetable_id, absence_date, is_excused, reason)
    execute_values(
        cur,
        'INSERT INTO "absences" ("student_id","subject_id","timetable_id","absence_date","is_excused","reason") VALUES %s',
        rows,
        page_size=10000,
    )


def period_slots() -> List[Tuple[int, dt.time, dt.time]]:
    # 1..5 (Mon..Fri), 7 periods
    starts = [
        (8, 0),
        (9, 0),
        (10, 0),
        (11, 0),
        (12, 0),
        (13, 0),
        (14, 0),
    ]
    slots: List[Tuple[int, dt.time, dt.time]] = []
    for day in range(1, 6):
        for h, m in starts:
            s = dt.time(h, m)
            e = (dt.datetime.combine(dt.date.today(), s) + dt.timedelta(minutes=50)).time()
            slots.append((day, s, e))
    return slots


def main() -> int:
    load_dotenv(override=False)
    args = parse_args()

    cfg = DbConfig(
        host=args.host,
        port=args.port,
        dbname=args.dbname,
        user=args.user,
        password=args.password,
        sslmode=args.sslmode,
    )

    seed = int(_env("SEED", "42") or "42")
    classes_per_grade = int(_env("CLASSES_PER_GRADE", "3") or "3")
    students_per_class = int(_env("STUDENTS_PER_CLASS", "30") or "30")
    teachers_per_subject = int(_env("TEACHERS_PER_SUBJECT", "3") or "3")

    rng = random.Random(seed)
    # Ensure Romanian names (diacritics allowed in first_name/last_name fields)
    fake = Faker(["ro_RO"])
    Faker.seed(seed)

    today = dt.date.today()
    school_start, school_end = daterange_start_end_for_school_year(today)
    academic_year = f"{school_start.year}-{school_start.year + 1}"

    subjects_def = subject_catalog()

    common_password = "parola123"
    # Store only the hex digest (no "sha256:" prefix), as requested.
    common_password_hash = sha256_hex(common_password)

    if not args.password:
        print("ERROR: DB password is empty. Set DB_PASSWORD env var or --password.", file=sys.stderr)
        return 2

    with connect_db(cfg) as conn:
        with conn.cursor() as cur:
            if args.reset:
                print("Resetting schema public (DROP SCHEMA ... CASCADE)...")
                reset_public_schema(cur)
                conn.commit()

            print(f"Applying schema: {args.schema_file}")
            apply_schema(cur, args.schema_file)
            conn.commit()

            print("Seeding base dictionaries (roles, grade_levels, subjects, curriculum_reqs)...")
            role_ids = insert_roles(cur)
            grade_levels = insert_grade_levels(cur)
            subjects_db = insert_subjects(cur, subjects_def)
            hours_map = insert_curriculum_reqs(cur, rng, grade_levels, subjects_db, subjects_def)
            conn.commit()

            # Teachers
            print("Creating teachers...")
            subjects_by_code = {code: (sid, name) for sid, name, code in subjects_db}
            teacher_user_rows: List[Tuple[int, str, str, str, str, str, Optional[str], dt.datetime]] = []
            teacher_meta: List[Tuple[str, dt.date]] = []  # specialization, hire_date
            email_domains = ["liceu.ro", "scoala.ro", "edu.ro"]

            for _, subject_name, subject_code in subjects_db:
                for _i in range(teachers_per_subject):
                    first = fake.first_name()
                    last = fake.last_name()
                    username_base = ascii_slug(f"{first[:1]}{last}")
                    username = f"{username_base}{rng.randint(10, 9999)}"
                    email = f"{username}@{rng.choice(email_domains)}"
                    phone = romanian_phone_e164(rng)
                    created_at = fake.date_time_between(start_date="-3y", end_date="now")
                    teacher_user_rows.append(
                        (role_ids["teacher"], username, email, common_password_hash, first, last, phone, created_at)
                    )
                    hire_date = fake.date_between(start_date="-12y", end_date="-30d")
                    teacher_meta.append((subject_name, hire_date))

            teacher_user_ids = insert_users(cur, teacher_user_rows)
            teacher_rows = [(uid, spec, hire) for uid, (spec, hire) in zip(teacher_user_ids, teacher_meta)]
            insert_teachers(cur, teacher_rows)
            conn.commit()

            # Build teacher pools by subject specialization
            teacher_pool_by_subject: Dict[str, List[int]] = {}
            for uid, (spec, _hire) in zip(teacher_user_ids, teacher_meta):
                teacher_pool_by_subject.setdefault(spec, []).append(uid)

            # Classes
            print("Creating classes...")
            class_rows: List[Tuple[str, int, Optional[int], str]] = []
            class_grade_ids: List[int] = []
            for grade_level_id, numeric_level, _ in grade_levels:
                for idx in range(classes_per_grade):
                    suffix = chr(ord("A") + idx)
                    cname = f"{numeric_level}{suffix}"
                    homeroom = rng.choice(teacher_user_ids) if teacher_user_ids else None
                    class_rows.append((cname, grade_level_id, homeroom, academic_year))
                    class_grade_ids.append(grade_level_id)

            class_ids = insert_classes(cur, class_rows)
            conn.commit()

            # Students (users + students)
            print("Creating students...")
            student_user_rows: List[Tuple[int, str, str, str, str, str, Optional[str], dt.datetime]] = []
            student_rows: List[Tuple[int, int, dt.date]] = []

            # DOB: enforce realistic age ranges for 2026
            for class_id, grade_level_id in zip(class_ids, class_grade_ids):
                grade_num = next(gl[1] for gl in grade_levels if gl[0] == grade_level_id)
                # spread birthdays across a year
                for _i in range(students_per_class):
                    first = fake.first_name()
                    last = fake.last_name()
                    username_base = ascii_slug(f"{first}.{last}", allow_dot=True)
                    username = f"{username_base}{rng.randint(10, 9999)}"
                    email = f"{username}@{rng.choice(email_domains)}"
                    phone = romanian_phone_e164(rng)
                    created_at = fake.date_time_between(start_date="-2y", end_date="now")

                    dob = sample_dob_for_grade(today, rng, grade_num)

                    student_user_rows.append(
                        (role_ids["student"], username, email, common_password_hash, first, last, phone, created_at)
                    )
                    # user_id filled after insert
                    student_rows.append((0, class_id, dob))

            student_user_ids = insert_users(cur, student_user_rows)
            student_rows = [(uid, class_id, dob) for (uid, (zero, class_id, dob)) in zip(student_user_ids, student_rows)]
            insert_students(cur, student_rows)
            conn.commit()

            # Class courses + timetable
            print("Creating class_courses + timetable...")
            # Build subject list per grade_level_id
            subjects_for_grade_level: Dict[int, List[Tuple[int, str]]] = {}
            subj_def_by_name = {s.name: s for s in subjects_def}
            for grade_level_id, numeric_level, _ in grade_levels:
                allowed: List[Tuple[int, str]] = []
                for subject_id, subject_name, _code in subjects_db:
                    sdef = subj_def_by_name.get(subject_name)
                    if sdef and sdef.min_grade <= numeric_level <= sdef.max_grade:
                        allowed.append((subject_id, subject_name))
                subjects_for_grade_level[grade_level_id] = allowed

            class_courses_rows: List[Tuple[int, int, int]] = []
            course_meta: List[Tuple[int, int, str]] = []  # (class_id, subject_id, subject_name)

            for class_id, grade_level_id in zip(class_ids, class_grade_ids):
                for subject_id, subject_name in subjects_for_grade_level[grade_level_id]:
                    pool = teacher_pool_by_subject.get(subject_name)
                    teacher_id = rng.choice(pool) if pool else rng.choice(teacher_user_ids)
                    class_courses_rows.append((class_id, subject_id, teacher_id))
                    course_meta.append((class_id, subject_id, subject_name))

            course_ids = insert_class_courses(cur, class_courses_rows)
            conn.commit()

            # Timetable slots per class
            slots = period_slots()
            used_slots_by_class: Dict[int, set] = {cid: set() for cid in class_ids}

            timetable_rows: List[Tuple[int, int, dt.time, dt.time, str]] = []
            timetable_meta: List[Tuple[int, int, int, dt.time, dt.time]] = []  # timetable_id later: (class_id, subject_id, day, start, end)

            for course_id, (class_id, subject_id, _subject_name) in zip(course_ids, course_meta):
                grade_level_id = next(glid for cid, glid in zip(class_ids, class_grade_ids) if cid == class_id)
                hours = hours_map.get((grade_level_id, subject_id), 1)
                for _k in range(hours):
                    # pick a free slot for the class
                    for _attempt in range(200):
                        day, start_t, end_t = rng.choice(slots)
                        key = (day, start_t)
                        if key in used_slots_by_class[class_id]:
                            continue
                        used_slots_by_class[class_id].add(key)
                        room = f"{rng.choice(['A', 'B', 'C', 'Lab'])}{rng.randint(101, 320)}"
                        timetable_rows.append((course_id, day, start_t, end_t, room))
                        timetable_meta.append((class_id, subject_id, day, start_t, end_t))
                        break

            insert_timetable(cur, timetable_rows)
            conn.commit()

            # Build timetable_id lookup for absences
            cur.execute(
                'SELECT t.timetable_id, cc.class_id, cc.subject_id, t.day_of_week, t.start_time, t.end_time '
                'FROM "timetable" t '
                'JOIN "class_courses" cc ON cc.course_id = t.class_course_id;'
            )
            timetable_by_class_subject: Dict[Tuple[int, int], List[Tuple[int, int, dt.time, dt.time]]] = {}
            for tid, class_id, subject_id, dow, st, en in cur.fetchall():
                timetable_by_class_subject.setdefault((int(class_id), int(subject_id)), []).append(
                    (int(tid), int(dow), st, en)
                )

            # Grades + absences
            print("Creating grades + absences (this can be the largest part)...")

            # Map: student_id -> class_id
            cur.execute('SELECT "user_id","class_id" FROM "students";')
            student_class: Dict[int, int] = {int(sid): int(cid) for sid, cid in cur.fetchall()}

            # Map: class_id -> subjects
            cur.execute('SELECT cc.class_id, cc.subject_id FROM "class_courses" cc;')
            class_subjects: Dict[int, List[int]] = {}
            for cid, sid in cur.fetchall():
                class_subjects.setdefault(int(cid), []).append(int(sid))

            grades_rows: List[Tuple[int, int, int, dt.date, Optional[str]]] = []
            abs_rows: List[Tuple[int, int, Optional[int], dt.date, bool, Optional[str]]] = []

            excused_reasons = [
                "Adeverință medicală",
                "Problemă de familie",
                "Participare la concurs",
                "Programare medicală",
            ]
            unexcused_reasons = [None, None, None, "Întârziere", "Fără motiv"]

            for student_id, class_id in student_class.items():
                subject_ids = class_subjects.get(class_id, [])
                for subject_id in subject_ids:
                    # number of grades per subject/student
                    n_grades = rng.randint(5, 15)
                    for _g in range(n_grades):
                        val = sample_grade_value(rng)
                        gdate = random_date_between(rng, school_start, school_end)
                        comment = None
                        if rng.random() < 0.12:
                            comment = rng.choice(
                                ["Foarte bine", "Bine", "Poate mai mult", "Progres vizibil", "Necesită atenție"]
                            )
                        grades_rows.append((student_id, subject_id, int(val), gdate, comment))

                    # absences: weighted 0..15 per subject
                    n_abs = sample_absence_count(rng)
                    if n_abs > 0:
                        tt = timetable_by_class_subject.get((class_id, subject_id), [])
                        for _a in range(n_abs):
                            timetable_id = None
                            weekday = rng.randint(1, 5)
                            if tt:
                                timetable_id, weekday, _st, _en = rng.choice(tt)
                            adate = random_date_for_weekday(rng, school_start, school_end, weekday)
                            is_excused = rng.random() < 0.6
                            reason = rng.choice(excused_reasons) if is_excused else rng.choice(unexcused_reasons)
                            abs_rows.append((student_id, subject_id, timetable_id, adate, is_excused, reason))

                # flush big batches periodically
                if len(grades_rows) >= 50000:
                    insert_grades(cur, grades_rows)
                    grades_rows.clear()
                if len(abs_rows) >= 50000:
                    insert_absences(cur, abs_rows)
                    abs_rows.clear()

            if grades_rows:
                insert_grades(cur, grades_rows)
            if abs_rows:
                insert_absences(cur, abs_rows)
            conn.commit()

            # Summary
            print("\nDone. Row counts:")
            for t in ["roles", "users", "teachers", "grade_levels", "subjects", "curriculum_reqs", "classes", "students", "class_courses", "timetable", "grades", "absences"]:
                n = fetch_one_int(cur, f'SELECT COUNT(*) FROM "{t}";')
                print(f"  {t:16s} {n}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

