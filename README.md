# EduAi — Asistent școlar inteligent

EduAi este un asistent inteligent autonom pentru monitorizarea situației școlare, ce combina date structurate (note/absențe) cu date nestructurate (regulamente). Inspirat din MCP și RAG, folosește Azure OpenAI (GPT-4o) și Azure AI Search pentru un flux complet de raționament + tool calling.

## Flux de execuție (simplificat)
1) API `/chat` primește `{user_id, message}` (user_id = telefon/ID Telegram autentificat).
2) Istoricul conversației (per user) este inițializat cu SYSTEM_PROMPT + instrucțiuni de securitate (telefon furnizat de backend).
3) Mesajul este trimis la Azure OpenAI (GPT-4o) cu schema Tools (Function Calling).
4) Dacă modelul cere un tool:
   - `_dispatch_tool_call` suprascrie `phone = user_id` pentru uneltele sensibile.
   - Apelează `server.py` (Gradebook API + Azure Search).
   - Rezultatul este atașat ca mesaj `tool` și se face un nou apel la model până la răspuns final.
5) Răspunsul final este returnat la client (ex. Telegram bot).

## Arhitectură

Trei servicii în Docker Compose:

1. **Gradebook API** (`api/gradebook-api`) — REST API pentru catalog (Node.js + Express + PostgreSQL)
2. **Orchestrator** (`orchestrator/`) — Agent AI cu tool calling (FastAPI + Azure OpenAI + Azure AI Search)
  - **Core Agentic (Orchestrator):** agent cu Chain-of-Thought + Function Calling, decide când să apeleze unelte pentru validare elev și note/absențe.
  - **MCP Layer:** server MCP propriu ca strat de securitate/abstractizare peste Gradebook API (catalog extern).
  - **RAG:** Azure AI Search cu index vectorial peste regulamentul școlar; agentul extrage reguli relevante și le corelează cu situația elevului (ex: risc de exmatriculare).
  - **Microservicii & Docker:** containere separate pentru logică (Agent + MCP Server) și interfață (ex. Telegram bot), comunicare pe rețea internă privată.
  - **Interfață:** Telegram API pentru conversație în timp real.
3. **Telegram Bot** (`bot/`) — Interfață pentru elevi (Node.js + Telegraf)

## Securitate

- Bot autentifică elevul prin telefon (verificare în gradebook + cod de 6 cifre)
- Orchestrator primește `{ phone, message }` și **leagă toate tool-urile de telefon server-side**
- LLM nu poate accesa date ale altui elev — `phone` este injectat de backend, nu de model

## Puncte cheie implementate
- **Tooling securizat:** `PHONE_BOUND_TOOLS = {"get_student", "get_subjects", "get_timetable", "get_grades", "check_absences"}`.  
  - LLM poate decide ce unealtă să apeleze, dar telefonul este impus server-side:
    ```python
    if name in PHONE_BOUND_TOOLS:
        args["phone"] = user_id
    ```
    Orice telefon “inventat” de model este suprascris cu identitatea autentificată (`user_id`).
- **Protecție prompt-injection & halucinații:** utilizatorul nu poate forța acces la alt telefon; LLM nu are voie să “ghicească” numere. Backend-ul pune telefonul real înainte de execuția uneltelor.
- **Confidențialitate (GDPR):** telefonul nu este expus în prompt; rămâne pe server, LLM vede doar un user_id abstract.
- **Istorie sigură:** reparație de istoric pentru a evita stări inconsistente (assistant tool_calls fără mesaje tool).
- **RAG disciplinat:** întrebările despre reguli folosesc `search_regulations`; întrebările factuale folosesc uneltele de note/absențe.

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
