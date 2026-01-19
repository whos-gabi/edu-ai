function apiKeyAuth(req, res, next) {
  const expected = process.env.API_KEY;
  if (!expected) {
    return res.status(500).json({ error: "Server misconfigured: API_KEY missing" });
  }
  const got = req.header("x-api-key");
  if (!got || got !== expected) {
    return res.status(401).json({ error: "Unauthorized" });
  }
  return next();
}

module.exports = { apiKeyAuth };

