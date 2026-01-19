const { query } = require("./db");

async function getStudentContextByPhone(phone) {
  const sql = `
    SELECT
      u.user_id AS student_user_id,
      u.username AS student_username,
      u.email AS student_email,
      u.first_name AS student_first_name,
      u.last_name AS student_last_name,
      u.phone_number AS student_phone_number,
      s.date_of_birth AS student_date_of_birth,

      c.class_id,
      c.name AS class_name,
      c.academic_year,

      gl.grade_level_id,
      gl.numeric_level AS grade_numeric_level,
      gl.name AS grade_name,

      ht.user_id AS homeroom_teacher_user_id,
      htu.first_name AS homeroom_teacher_first_name,
      htu.last_name AS homeroom_teacher_last_name
    FROM "users" u
    JOIN "students" s ON s.user_id = u.user_id
    LEFT JOIN "classes" c ON c.class_id = s.class_id
    LEFT JOIN "grade_levels" gl ON gl.grade_level_id = c.grade_level_id
    LEFT JOIN "teachers" ht ON ht.user_id = c.homeroom_teacher_id
    LEFT JOIN "users" htu ON htu.user_id = ht.user_id
    WHERE u.phone_number = $1
    LIMIT 1;
  `;
  const r = await query(sql, [phone]);
  if (!r.rows.length) return null;
  return r.rows[0];
}

async function getStudentSubjectsByClassId(classId) {
  const sql = `
    SELECT
      sub.subject_id,
      sub.name AS subject_name,
      sub.code AS subject_code,
      tu.user_id AS teacher_user_id,
      tu.first_name AS teacher_first_name,
      tu.last_name AS teacher_last_name
    FROM "class_courses" cc
    JOIN "subjects" sub ON sub.subject_id = cc.subject_id
    JOIN "teachers" t ON t.user_id = cc.teacher_id
    JOIN "users" tu ON tu.user_id = t.user_id
    WHERE cc.class_id = $1
    ORDER BY sub.name ASC, tu.last_name ASC, tu.first_name ASC;
  `;
  const r = await query(sql, [classId]);
  return r.rows;
}

async function getSubjectIdByName(subjectName) {
  const sql = `SELECT subject_id FROM "subjects" WHERE name = $1 LIMIT 1;`;
  const r = await query(sql, [subjectName]);
  return r.rows.length ? Number(r.rows[0].subject_id) : null;
}

async function getStudentAbsences(studentUserId, subjectId) {
  const sql = `
    SELECT
      a.absence_id,
      a.absence_date,
      a.is_excused,
      a.reason
    FROM "absences" a
    WHERE a.student_id = $1 AND a.subject_id = $2
    ORDER BY a.absence_date DESC, a.absence_id DESC;
  `;
  const r = await query(sql, [studentUserId, subjectId]);
  return r.rows;
}

async function getStudentGrades(studentUserId, subjectId) {
  const sql = `
    SELECT
      g.grade_id,
      g.grade_value,
      g.grade_date,
      g.comments
    FROM "grades" g
    WHERE g.student_id = $1 AND g.subject_id = $2
    ORDER BY g.grade_date DESC, g.grade_id DESC;
  `;
  const r = await query(sql, [studentUserId, subjectId]);
  return r.rows;
}

async function getStudentGradesSummary(studentUserId) {
  // Per subject: list grades + average.
  // We return one row per grade; grouping is done in JS for a clean response.
  const sql = `
    SELECT
      sub.subject_id,
      sub.name AS subject_name,
      g.grade_id,
      g.grade_value,
      g.grade_date
    FROM "grades" g
    JOIN "subjects" sub ON sub.subject_id = g.subject_id
    WHERE g.student_id = $1
    ORDER BY sub.name ASC, g.grade_date DESC, g.grade_id DESC;
  `;
  const r = await query(sql, [studentUserId]);
  return r.rows;
}

async function getStudentAbsencesSummary(studentUserId) {
  // Per subject: list absences + count (grouping done in JS).
  const sql = `
    SELECT
      sub.subject_id,
      sub.name AS subject_name,
      a.absence_id,
      a.absence_date,
      a.is_excused,
      a.reason
    FROM "absences" a
    JOIN "subjects" sub ON sub.subject_id = a.subject_id
    WHERE a.student_id = $1
    ORDER BY sub.name ASC, a.absence_date DESC, a.absence_id DESC;
  `;
  const r = await query(sql, [studentUserId]);
  return r.rows;
}

async function getStudentTimetable(classId) {
  const sql = `
    SELECT
      t.day_of_week,
      t.start_time,
      t.end_time,
      t.room,
      sub.name AS subject_name,
      tu.first_name AS teacher_first_name,
      tu.last_name AS teacher_last_name
    FROM "timetable" t
    JOIN "class_courses" cc ON cc.course_id = t.class_course_id
    JOIN "subjects" sub ON sub.subject_id = cc.subject_id
    JOIN "teachers" te ON te.user_id = cc.teacher_id
    JOIN "users" tu ON tu.user_id = te.user_id
    WHERE cc.class_id = $1
    ORDER BY t.day_of_week ASC, t.start_time ASC, sub.name ASC;
  `;
  const r = await query(sql, [classId]);
  return r.rows;
}

module.exports = {
  getStudentContextByPhone,
  getStudentSubjectsByClassId,
  getSubjectIdByName,
  getStudentAbsences,
  getStudentGrades,
  getStudentGradesSummary,
  getStudentAbsencesSummary,
  getStudentTimetable,
};

