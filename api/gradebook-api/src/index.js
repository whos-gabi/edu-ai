require("dotenv").config();

const express = require("express");
const { apiKeyAuth } = require("./auth");
const { getEnv } = require("./db");
const studentsRouter = require("./routes/students");

const app = express();
app.disable("x-powered-by");

// Health (still protected, per requirement "accepta doar acel api key")
app.get("/health", apiKeyAuth, (req, res) => res.json({ ok: true }));

// All routes require x-api-key
app.use(apiKeyAuth);
app.use(express.json({ limit: "256kb" }));

app.use("/students", studentsRouter);

app.use((req, res) => {
  res.status(404).json({ error: "not found" });
});

const port = Number(getEnv("PORT", "8080"));
app.listen(port, "0.0.0.0", () => {
  // eslint-disable-next-line no-console
  console.log(`gradebook-api listening on :${port}`);
});

