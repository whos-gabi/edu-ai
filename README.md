# EduAi — Orchestrator & Agentic RAG for School Insights

EduAi este un asistent inteligent autonom pentru monitorizarea situației școlare, combinând date structurate (note/absențe) cu date nestructurate (regulamente). Inspirat din MCP și RAG, folosește Azure OpenAI (GPT-4o) și Azure AI Search pentru un flux complet de raționament + tool calling.

## Arhitectură (pe scurt)
- **Core Agentic (Orchestrator):** agent cu Chain-of-Thought + Function Calling, decide când să apeleze unelte pentru validare elev și note/absențe.
- **MCP Layer:** server MCP propriu ca strat de securitate/abstractizare peste Gradebook API (catalog extern).
- **RAG:** Azure AI Search cu index vectorial peste regulamentul școlar; agentul extrage reguli relevante și le corelează cu situația elevului (ex: risc de exmatriculare).
- **Microservicii & Docker:** containere separate pentru logică (Agent + MCP Server) și interfață (ex. Telegram bot), comunicare pe rețea internă privată.
- **Interfață:** Telegram API pentru conversație în timp real.

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

## Flux de execuție (simplificat)
1) API `/chat` primește `{user_id, message}` (user_id = telefon/ID Telegram autentificat).
2) Istoricul conversației (per user) este inițializat cu SYSTEM_PROMPT + instrucțiuni de securitate (telefon furnizat de backend).
3) Mesajul este trimis la Azure OpenAI (GPT-4o) cu schema Tools (Function Calling).
4) Dacă modelul cere un tool:
   - `_dispatch_tool_call` suprascrie `phone = user_id` pentru uneltele sensibile.
   - Apelează `server.py` (Gradebook API + Azure Search).
   - Rezultatul este atașat ca mesaj `tool` și se face un nou apel la model până la răspuns final.
5) Răspunsul final este returnat la client (ex. Telegram bot).

## Microservicii & rulare
- **Docker:** imagine python:3.11-slim, uvicorn pe `0.0.0.0:8080`.
- **Dependențe:** `fastapi`, `uvicorn`, `openai`, `requests`, `python-dotenv`, `azure-search-documents`, `azure-identity`, `pydantic`.
- **Config:** variabile .env pentru Azure OpenAI (endpoint, key, deployment), Azure Search (endpoint, key, index), Gradebook API (base URL + key).

## Fișiere relevante
- `orchestrator/agent.py` — FastAPI, buclă de tool-calling, securizare phone-bound.
- `orchestrator/server.py` — unelte (grade/absențe/regulament/orar/subiecte).
- `orchestrator/prompts.py` — SYSTEM_PROMPT și descrieri de unelte (persona + protocoale).
- `orchestrator/Dockerfile`, `requirements.txt` — containerizare și deps.