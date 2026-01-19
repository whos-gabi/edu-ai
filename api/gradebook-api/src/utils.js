function normalizePhone(phone) {
  if (phone === undefined || phone === null) return null;
  let s = String(phone).trim();
  if (!s) return null;
  // Remove common separators
  s = s.replace(/[()\s-]/g, "");
  if (!s) return null;
  // Normalize Romanian numbers to +40...
  if (s.startsWith("00")) {
    s = "+" + s.slice(2);
  }
  if (s.startsWith("40") && !s.startsWith("+")) {
    s = "+" + s;
  }
  if (s.startsWith("0") && s.length >= 10) {
    s = "+40" + s.slice(1);
  }
  return s;
}

function dayNameRo(dayOfWeek) {
  switch (Number(dayOfWeek)) {
    case 1:
      return "Luni";
    case 2:
      return "Marți";
    case 3:
      return "Miercuri";
    case 4:
      return "Joi";
    case 5:
      return "Vineri";
    case 6:
      return "Sâmbătă";
    case 7:
      return "Duminică";
    default:
      return String(dayOfWeek);
  }
}

module.exports = {
  normalizePhone,
  dayNameRo,
};

