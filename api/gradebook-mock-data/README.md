## gradebook-mock-data

Script Python care **resetează** baza de date Postgres (`schema public`) și apoi inserează **multe date realiste** cu Faker pentru schema din `schema.sql` (derivată din `EduAPI_DB (2).sql`).

### Ce face (pe scurt)

- **Reset** (opțional, dar recomandat): `DROP SCHEMA public CASCADE;` + recreare `public`
- **Re-creează schema** rulând `schema.sql`
- Inserează date în ordinea corectă pentru FK-uri:
  - `roles`
  - `grade_levels`, `subjects`, `curriculum_reqs`
  - `users` (profesori) + `teachers`
  - `classes`
  - `users` (elevi) + `students`
  - `class_courses`
  - `timetable`
  - `grades`, `absences`
- La final afișează **numărul total de rânduri** pe fiecare tabel.

### Ce diferențe are schema față de fișierul inițial

În `schema.sql` am făcut 3 ajustări necesare:

- **`users.phone_number`**: câmp nou (`VARCHAR(30)`) – cerința ta “users vrea să aibă și nr de telefon”.
- **`timetable.day_of_week`**: `SMALLINT` (1=Mon..7=Sun) în loc de `BLOB` (Postgres nu suportă `BLOB`).
- **`absences.timetable_id`**: devine **nullable**, fiindcă FK-ul e `ON DELETE SET NULL` (altfel Postgres respinge schema).

### Ce date inserează (realistic)

- **users**
  - roluri: `admin`, `teacher`, `student`
  - `username`/`email` unice
  - `password_hash` este un hash simplu (format `sha256:<hex>`) doar pentru mock data
  - `phone_number` din Faker (`ro_RO`)
- **teachers**
  - câte N profesori per materie (`--teachers-per-subject`)
  - `specialization` = numele materiei (ex. “Matematică”)
  - `hire_date` random în ultimii ~12 ani
- **grade_levels**
  - clasele 1..12
- **subjects**
  - set “școală” (RO, MATH, EN, CS, HIST, GEO, BIO, PHYS, CHEM, PE, MUS, ART, REL)
  - apar/nu apar în funcție de intervalul de clase (ex: Chimie de la clasa 7+)
- **curriculum_reqs**
  - ore/săptămână per clasă/materie (distribuție “aprox realistă”)
- **classes**
  - per nivel: `--classes-per-grade` (ex. 5A, 5B, 5C)
  - `academic_year` set automat la anul școlar curent (ex. 2025-2026)
- **students**
  - per clasă: `--students-per-class`
  - `date_of_birth` aproximat în funcție de clasă (vârstă ~ clasa + 6)
- **timetable**
  - construiește un orar (Luni–Vineri) pe intervale de 50 min
  - alocă orele în funcție de `curriculum_reqs.required_hours_per_week`
- **grades**
  - pentru fiecare elev/materie inserează **5..15** note
  - valori **2..10** (din 0.25 în 0.25), cu **75% șansă** să fie în **[6..10]**
  - date între începutul anului școlar și “azi”
- **absences**
  - per elev/materie: **0..15** absențe, cu **80% șansă** să fie în **[0..4]**
  - `is_excused` ~60% true + reason realist

### Câte rânduri inserează (implicit)

Implicit:

- `CLASSES_PER_GRADE=3` → 12*3 = **36** clase
- `STUDENTS_PER_CLASS=30` → 36*30 = **1080** elevi
- `TEACHERS_PER_SUBJECT=3` și ~13 materii → ~**39** profesori

La final scriptul îți afișează exact count-urile pe fiecare tabel (după inserare).

### Rulare

1) Instalează dependențele:

```bash
cd /root/MLDevOps/gradebook-mock-data
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Setează variabilele de mediu (recomandat: copy din `env.example`):

```bash
export DB_HOST=45.137.148.238
export DB_PORT=5433
export DB_NAME=gradebook
export DB_USER=edu_admin
export DB_PASSWORD='...'
```

3) Rulează reset + seed:

```bash
python seed_gradebook.py --reset
```

Opțional (volum mai mare / alt seed):

```bash
export SEED=123
export CLASSES_PER_GRADE=4
export STUDENTS_PER_CLASS=30
export TEACHERS_PER_SUBJECT=6
python seed_gradebook.py --reset
```

### Atenție

- `--reset` face **wipe total** pe `public` (DROP SCHEMA ... CASCADE). Rulează-l doar dacă vrei reset complet.
