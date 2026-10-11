# CivicSense

A multi-agent system that triages civic complaints (potholes, garbage, broken streetlights, water leaks), routes each one to the right department desk, drafts the formal complaint letter, and keeps following up until it is resolved.

Built with LangGraph, Gemini, Django REST Framework and React as an Agentic AI project at BMS College of Engineering.

## How it works

A complaint (text, location, optional photo) goes through a LangGraph pipeline:

1. **Classifier** reads the text and photo and returns the issue type and severity.
2. **Duplicate check** compares the complaint against open ones in the same category, using separate similarity scores for the issue and for the place.
3. **Router** looks up department rules (RAG over an in-memory vector store) and picks the department, desk and response deadline. The deadline is the smaller of the rule's SLA and a cap based on severity.
4. **Drafter** writes the formal complaint letter.
5. **Follow-up agent** runs on a schedule. It closes resolved complaints, sends reminders, and escalates through the chain (desk, head of department, commissioner's office) when a deadline is missed.

Complaints about unclear problems are sent back with a request for more details instead of being routed.

## Run with Docker (recommended)

You need Docker Desktop and a Gemini API key.

1. Create a `.env` file in the repo root:

```
   GOOGLE_API_KEY=your-gemini-key
   FAKE_LLM=1
```

   `FAKE_LLM=1` uses a keyword classifier and a template letter, so the free-tier quota is not used. Embeddings still call Gemini, so the key is required. Set `FAKE_LLM=0` to use the real model.

2. Start everything:

```
   docker compose up --build
```

3. Open http://localhost:5173 (use `localhost`, not `127.0.0.1`).

The database and uploaded photos are stored in `./data`, so they survive restarts.

Run the follow-up check (reminders and escalations) manually:

```
docker compose exec backend python manage.py run_followups
```

## Run without Docker

Backend:

```
cd backend
pip install -r requirements.txt
set GOOGLE_API_KEY=your-gemini-key      # PowerShell: $env:GOOGLE_API_KEY="..."
python manage.py migrate
python manage.py runserver
```

Frontend:

```
cd frontend
npm install
npm run dev
```

Command-line demos of the agents (no server needed):

```
python agents.py            # classify, route and draft a few sample complaints
python agents.py followup   # simulate the escalation chain over time
```

## Project structure

```
backend/
  agents.py            all agent logic (both LangGraph graphs)
  complaints/          Django app: models, API, follow-up runner, management command
  config/              Django settings and URLs
frontend/
  src/                 React app: report form, officials' queue, complaint detail
steps/                 earlier step-by-step versions kept as learning history
docker-compose.yml
```

## API

| Method | Path | What it does |
|---|---|---|
| POST | `/api/complaints/` | Submit a complaint (multipart: text, location, photo) |
| GET | `/api/complaints/` | List complaints |
| GET | `/api/complaints/<id>/` | One complaint with assessment, letter and follow-up history |
| POST | `/api/complaints/<id>/resolve/` | Mark as resolved |

## Roadmap

- [x] LangGraph pipeline with shared state
- [x] Conditional routing for unclear complaints
- [x] LLM classifier with structured output
- [x] Letter drafting
- [x] Photo understanding
- [x] RAG over department rules
- [x] Duplicate detection
- [x] Follow-up and escalation agent
- [x] Django REST API
- [x] React dashboard
- [x] Docker setup
- [ ] Email and SMS for reminders and escalations
- [ ] Map lookup for road type and ward from the location
- [ ] pgvector for duplicate search at scale
- [ ] Voice and multilingual intake

## Known limitations

- Department rules, desks, SLAs and escalation windows are example values, not real municipal data.
- Text alone cannot tell the road type (main road or internal lane). A map lookup would fix this.
- Duplicate detection compares stored vectors in Python, which is O(n) per complaint. A vector database such as pgvector is the real fix at scale.
- Reminders and escalations are written to the complaint's history as log lines. No email or SMS is sent yet.
- `FAKE_LLM` mode cannot read photos.
- The free Gemini tier allows about 20 generation requests per day per model.
- The Django settings are for development (default secret key, debug on).