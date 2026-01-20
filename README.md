# EduAi — Asistent școlar inteligent

Asistent virtual pentru elevi: note, absențe, orar și regulamente, prin Telegram.

## Arhitectură

Trei servicii în Docker Compose:

1. **Gradebook API** (`api/gradebook-api`) — REST API pentru catalog (Node.js + Express + PostgreSQL)
2. **Orchestrator** (`orchestrator/`) — Agent AI cu tool calling (FastAPI + Azure OpenAI + Azure AI Search)
3. **Telegram Bot** (`bot/`) — Interfață pentru elevi (Node.js + Telegraf)

## Securitate

- Bot autentifică elevul prin telefon (verificare în gradebook + cod de 6 cifre)
- Orchestrator primește `{ phone, message }` și **leagă toate tool-urile de telefon server-side**
- LLM nu poate accesa date ale altui elev — `phone` este injectat de backend, nu de model

## Rulare

```bash
# Creează .env pentru fiecare serviciu (vezi sample.env în fiecare folder)
cp api/gradebook-api/sample.env api/gradebook-api/.env
cp orchestrator/sample.env orchestrator/.env
cp bot/sample.env bot/.env

# Start
docker compose up --build

#Stop
docker compose down
```

## Structură

```
api/gradebook-api/    → catalog API
orchestrator/         → agent AI + tools
bot/                  → Telegram bot
docker-compose.yml    → orchestrație
```
