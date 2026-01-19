const { Pool } = require("pg");

function getEnv(name, fallback) {
  const v = process.env[name];
  if (v === undefined || v === null) return fallback;
  const s = String(v).trim();
  return s.length ? s : fallback;
}

function requireEnv(name) {
  const v = getEnv(name, null);
  if (!v) throw new Error(`Missing required env var: ${name}`);
  return v;
}

const pool = new Pool({
  host: requireEnv("DB_HOST"),
  port: Number(getEnv("DB_PORT", "5432")),
  database: requireEnv("DB_NAME"),
  user: requireEnv("DB_USER"),
  password: requireEnv("DB_PASSWORD"),
  ssl: (() => {
    const mode = getEnv("DB_SSLMODE", "disable");
    // Only enable SSL when explicitly required.
    if (mode === "require" || mode === "verify-ca" || mode === "verify-full") {
      return { rejectUnauthorized: false };
    }
    return false;
  })(),
});

async function query(text, params) {
  return pool.query(text, params);
}

module.exports = {
  pool,
  query,
  getEnv,
  requireEnv,
};

