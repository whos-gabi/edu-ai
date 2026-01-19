const express = require("express");
const {
  getStudentContextByPhone,
  getStudentSubjectsByClassId,
  getSubjectIdByName,
  getStudentAbsences,
  getStudentGrades,
  getStudentGradesSummary,
  getStudentAbsencesSummary,
  getStudentTimetable,
} = require("../queries");
const { normalizePhone, dayNameRo } = require("../utils");

const router = express.Router();

function notFound(res) {
  return res.status(404).json({ error: "not found" });
}

function computeAverageInt(values) {
  if (!values.length) return null;
  const sum = values.reduce((a, b) => a + b, 0);
  return sum / values.length;
}

// GET student data by phone number (includes class + homeroom teacher)
router.get("/by-phone", async (req, res) => {
  try {
    const phone = normalizePhone(req.query.phone);
    if (!phone) return res.status(400).json({ error: "phone is required" });

    const row = await getStudentContextByPhone(phone);
    if (!row) return notFound(res);

    return res.json({
      student: {
        userId: Number(row.student_user_id),
        username: row.student_username,
        email: row.student_email,
        firstName: row.student_first_name,
        lastName: row.student_last_name,
        phoneNumber: row.student_phone_number,
        dateOfBirth: row.student_date_of_birth,
      },
      class: row.class_id
        ? {
            classId: Number(row.class_id),
            name: row.class_name,
            academicYear: row.academic_year,
            gradeLevel: row.grade_level_id
              ? {
                  gradeLevelId: Number(row.grade_level_id),
                  numericLevel: Number(row.grade_numeric_level),
                  name: row.grade_name,
                }
              : null,
          }
        : null,
      homeroomTeacher: row.homeroom_teacher_user_id
        ? {
            userId: Number(row.homeroom_teacher_user_id),
            firstName: row.homeroom_teacher_first_name,
            lastName: row.homeroom_teacher_last_name,
            fullName: `${row.homeroom_teacher_first_name} ${row.homeroom_teacher_last_name}`.trim(),
          }
        : null,
    });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("GET /students/by-phone failed", e);
    return res.status(500).json({ error: "server error" });
  }
});

// GET student subjects by phone number
router.get("/subjects", async (req, res) => {
  try {
    const phone = normalizePhone(req.query.phone);
    if (!phone) return res.status(400).json({ error: "phone is required" });

    const ctx = await getStudentContextByPhone(phone);
    if (!ctx) return notFound(res);
    if (!ctx.class_id) return res.json({ class: null, subjects: [] });

    const subjects = await getStudentSubjectsByClassId(Number(ctx.class_id));
    return res.json({
      class: { classId: Number(ctx.class_id), name: ctx.class_name, academicYear: ctx.academic_year },
      subjects: subjects.map((s) => ({
        subjectId: Number(s.subject_id),
        subject: s.subject_name,
        code: s.subject_code,
        teacher: {
          userId: Number(s.teacher_user_id),
          firstName: s.teacher_first_name,
          lastName: s.teacher_last_name,
          fullName: `${s.teacher_first_name} ${s.teacher_last_name}`.trim(),
        },
      })),
    });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("GET /students/subjects failed", e);
    return res.status(500).json({ error: "server error" });
  }
});

// GET student absences for a subject (subject by name, not id)
router.get("/absences", async (req, res) => {
  try {
    const phone = normalizePhone(req.query.phone);
    const subjectName = (req.query.subject || "").toString().trim();
    if (!phone) return res.status(400).json({ error: "phone is required" });
    if (!subjectName) return res.status(400).json({ error: "subject is required" });

    const ctx = await getStudentContextByPhone(phone);
    if (!ctx) return notFound(res);

    const subjectId = await getSubjectIdByName(subjectName);
    if (!subjectId) return res.status(404).json({ error: "subject not found" });

    const absences = await getStudentAbsences(Number(ctx.student_user_id), subjectId);
    return res.json({
      student: { userId: Number(ctx.student_user_id), phoneNumber: ctx.student_phone_number },
      subject: { subjectId, name: subjectName },
      absences,
    });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("GET /students/absences failed", e);
    return res.status(500).json({ error: "server error" });
  }
});

// GET student grades for a subject + average
router.get("/grades", async (req, res) => {
  try {
    const phone = normalizePhone(req.query.phone);
    const subjectName = (req.query.subject || "").toString().trim();
    if (!phone) return res.status(400).json({ error: "phone is required" });
    if (!subjectName) return res.status(400).json({ error: "subject is required" });

    const ctx = await getStudentContextByPhone(phone);
    if (!ctx) return notFound(res);

    const subjectId = await getSubjectIdByName(subjectName);
    if (!subjectId) return res.status(404).json({ error: "subject not found" });

    const grades = await getStudentGrades(Number(ctx.student_user_id), subjectId);
    const values = grades.map((g) => Number(g.grade_value)).filter((v) => Number.isFinite(v));
    const average = computeAverageInt(values);

    return res.json({
      student: { userId: Number(ctx.student_user_id), phoneNumber: ctx.student_phone_number },
      subject: { subjectId, name: subjectName },
      average,
      grades,
    });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("GET /students/grades failed", e);
    return res.status(500).json({ error: "server error" });
  }
});

// GET student grades total, with average for each subject
router.get("/grades/summary", async (req, res) => {
  try {
    const phone = normalizePhone(req.query.phone);
    if (!phone) return res.status(400).json({ error: "phone is required" });

    const ctx = await getStudentContextByPhone(phone);
    if (!ctx) return notFound(res);

    const rows = await getStudentGradesSummary(Number(ctx.student_user_id));
    const bySubject = new Map();
    for (const r of rows) {
      const key = Number(r.subject_id);
      if (!bySubject.has(key)) {
        bySubject.set(key, { subjectId: key, subject: r.subject_name, grades: [] });
      }
      bySubject.get(key).grades.push({
        gradeId: Number(r.grade_id),
        gradeValue: Number(r.grade_value),
        gradeDate: r.grade_date,
      });
    }

    const subjects = Array.from(bySubject.values()).map((s) => {
      const values = s.grades.map((g) => Number(g.gradeValue)).filter((v) => Number.isFinite(v));
      return { ...s, average: computeAverageInt(values) };
    });

    return res.json({
      student: { userId: Number(ctx.student_user_id), phoneNumber: ctx.student_phone_number },
      subjects,
    });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("GET /students/grades/summary failed", e);
    return res.status(500).json({ error: "server error" });
  }
});

// GET student absences total, grouped by subject
router.get("/absences/summary", async (req, res) => {
  try {
    const phone = normalizePhone(req.query.phone);
    if (!phone) return res.status(400).json({ error: "phone is required" });

    const ctx = await getStudentContextByPhone(phone);
    if (!ctx) return notFound(res);

    const rows = await getStudentAbsencesSummary(Number(ctx.student_user_id));
    const bySubject = new Map();
    for (const r of rows) {
      const key = Number(r.subject_id);
      if (!bySubject.has(key)) {
        bySubject.set(key, { subjectId: key, subject: r.subject_name, absences: [] });
      }
      bySubject.get(key).absences.push({
        absenceId: Number(r.absence_id),
        absenceDate: r.absence_date,
        isExcused: r.is_excused,
        reason: r.reason,
      });
    }

    const subjects = Array.from(bySubject.values()).map((s) => ({
      ...s,
      count: s.absences.length,
    }));

    return res.json({
      student: { userId: Number(ctx.student_user_id), phoneNumber: ctx.student_phone_number },
      subjects,
    });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("GET /students/absences/summary failed", e);
    return res.status(500).json({ error: "server error" });
  }
});

// GET student timetable, grouped by day name (Romanian)
router.get("/timetable", async (req, res) => {
  try {
    const phone = normalizePhone(req.query.phone);
    if (!phone) return res.status(400).json({ error: "phone is required" });

    const ctx = await getStudentContextByPhone(phone);
    if (!ctx) return notFound(res);
    if (!ctx.class_id) return res.json({ class: null, timetable: {} });

    const rows = await getStudentTimetable(Number(ctx.class_id));
    const timetable = {};
    for (const r of rows) {
      const day = dayNameRo(r.day_of_week);
      if (!timetable[day]) timetable[day] = [];
      timetable[day].push({
        subject: r.subject_name,
        startTime: r.start_time,
        endTime: r.end_time,
        teacher: `${r.teacher_first_name} ${r.teacher_last_name}`.trim(),
        room: r.room,
      });
    }

    return res.json({
      class: { classId: Number(ctx.class_id), name: ctx.class_name, academicYear: ctx.academic_year },
      timetable,
    });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("GET /students/timetable failed", e);
    return res.status(500).json({ error: "server error" });
  }
});

module.exports = router;

