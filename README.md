# CivicSense

A multi-agent system that triages civic complaints (potholes, garbage, broken streetlights, water leaks), routes each one to the right department desk, drafts the formal complaint letter, and keeps following up until it is resolved. Overdue complaints are escalated automatically and the right people are emailed.

Built with LangGraph, Gemini, Django REST Framework and React as an Agentic AI project at BMS College of Engineering.

## How it works

A complaint (text, location, optional photo) goes through a LangGraph pipeline:

1. **Classifier** reads the text and photo and returns the issue type and severity.
2. **Duplicate check** compares the complaint against open ones in the same category, using separate similarity scores for the issue (0.70) and for the place (0.75).
3. **Router** looks up department rules (RAG over an in-memory vector store) and picks the department, desk and response deadline. The deadline is the smaller of the rule's SLA and a cap based on severity (24, 72 or 168 hours).
4. **Drafter** writes the formal complaint letter.
5. **Follow-up agent** is a second graph. Each run is one check of one complaint. It closes resolved complaints, sends a reminder at 25% of the escalation window, escalates through the chain (desk, head of department, commissioner's office) when a deadline is missed, and flags CRITICAL when the top level is overdue.

Complaints about unclear problems are sent back with a request for more details instead of being routed.

The agents only decide. The follow-up graph returns a list of events (reminder, escalation, critical, closed) and the Django layer (`complaints/notify.py`) sends the emails. This keeps the agent code free of mail settings and easy to test.

## Run with Docker (recommended)

You need Docker Desktop. A Gemini API key is only needed for real model runs.

1. Copy `.env.example` to `.env` and edit it:

```
GOOGLE_API_KEY=your-gemini-key
FAKE_LLM=1
FAKE_EMBEDDINGS=0
SECRET_KEY=any-long-random-string
```

   - `FAKE_LLM=1` uses a keyword classifier and a template letter, so no generation quota is used.
   - `FAKE_EMBEDDINGS=1` also replaces the embedding calls with an offline hashed bag of words. With both on, the whole system runs with no API key and no internet.
   - Never commit `.env` or `data/`. Both are in `.gitignore`.

2. Start everything:

```
docker compose up --build
```

   This starts three services: `backend` (API), `frontend` (React) and `scheduler` (runs the follow-up check every `FOLLOWUP_INTERVAL` seconds, default 300).

3. Create an official account (citizens register themselves in the app):

```
docker compose exec backend python manage.py create_official officer
```

4. Open http://localhost:5173 (use `localhost`, not `127.0.0.1`).

The database and uploaded photos are stored in `./data`, so they survive restarts.

## Accounts and roles

- **Citizen**: registers in the app, can report problems and sees only their own reports.
- **Official**: created with `create_official`, sees every complaint and is the only role that can mark a complaint resolved.

Login uses API tokens. Register and login are rate limited.

## Demo data

`seed_demo` creates demo users (`officer`, `priya`, `arjun`, `meera`, password `demo1234`) and runs nine sample complaints through the real triage pipeline. Some are backdated so the queue shows every follow-up stage: open, reminder sent, escalated, critical, closed, plus a duplicate and one that needs more details. `--reset` deletes all existing complaints first. Re-running without `--reset` skips complaints already seeded.

```
python manage.py seed_demo --reset          # Docker: docker compose exec backend python manage.py seed_demo --reset
```

## Email notifications

By default emails are printed to the backend console (`EMAIL_BACKEND` console), so nothing is sent by accident. To send real mail, set the `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` and `DEFAULT_FROM_EMAIL` lines in `.env` (see `.env.example`).

Who gets which email is set in `backend/directory.json` (commissioner address, and a head and desk addresses per department). The addresses in the repo are examples on `example.com`. A closed complaint also emails the citizen who filed it if they gave an address.

## Editing the department rules

Department rules (category, department, desk, SLA hours, description) live in `backend/rules.json`, not in code. Edit that file and restart. The file is validated on load and a clear error is raised if a field is missing.

## Run without Docker

Backend:

```
cd backend
pip install -r requirements.txt       # settings read ../.env (GOOGLE_API_KEY etc.)
python manage.py migrate
python manage.py create_official officer
python manage.py runserver
```

Scheduler, in a second terminal (or run one check by hand without `--loop`):

```
python manage.py run_followups --loop --interval 300
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

## Tests

```
cd backend
FAKE_LLM=1 FAKE_EMBEDDINGS=1 python manage.py test      # PowerShell: set the variables first
```

48 tests run in under a second with no network. They cover the agents (classifier, router SLA cap, duplicate thresholds, the follow-up graph), email recipients and content, the follow-up runner against the database, and the API (login, ownership, permissions, duplicates, photos, error handling).

## Configuration

All settings come from environment variables (see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `GOOGLE_API_KEY` | none | Gemini key, needed unless both fake modes are on |
| `FAKE_LLM` | `0` | Keyword classifier and template letter |
| `FAKE_EMBEDDINGS` | `0` | Offline hashed embeddings |
| `SECRET_KEY` | insecure dev key | Set a real one outside development |
| `DEBUG` | `1` | Set `0` in production |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma separated |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | Comma separated |
| `FOLLOWUP_INTERVAL` | `300` | Seconds between scheduler checks |
| `EMAIL_*` | console backend | SMTP settings for real mail |

## Project structure

```
backend/
  agents.py            all agent logic (both LangGraph graphs)
  rules.json           department rules (editable, no code change)
  directory.json       who is emailed at each escalation level
  complaints/          Django app: models, API, auth, follow-up runner, notifications, tests
  config/              Django settings and URLs
frontend/
  src/                 React app: login, report form, queue, complaint detail
steps/                 earlier step-by-step versions kept as learning history
docker-compose.yml
.env.example
```

## API

All endpoints except register and login need the header `Authorization: Token <token>`.

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/api/auth/register/` | anyone | Create a citizen account, returns a token |
| POST | `/api/auth/login/` | anyone | Returns a token |
| POST | `/api/auth/logout/` | signed in | Deletes the token |
| GET | `/api/auth/me/` | signed in | Current user and role |
| POST | `/api/complaints/` | signed in | Submit a complaint (multipart: text, location, photo) |
| GET | `/api/complaints/` | signed in | Officials see all, citizens see their own |
| GET | `/api/complaints/<id>/` | signed in | One complaint with assessment, letter and follow-up history |
| POST | `/api/complaints/<id>/resolve/` | officials | Mark as resolved |

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
- [x] Scheduled follow-up checks
- [x] Email for reminders and escalations
- [x] Login and roles
- [x] Automated tests
- [x] Rules and settings outside the code
- [ ] SMS notifications
- [ ] Map lookup for road type and ward from the location
- [ ] pgvector for duplicate search at scale
- [ ] Voice and multilingual intake

## Known limitations

- Department rules, desks, SLAs, escalation windows and email addresses are example values, not real municipal data.
- Text alone cannot tell the road type (main road or internal lane). A map lookup would fix this.
- Duplicate detection compares stored vectors in Python, which is O(n) per complaint. A vector database such as pgvector is the real fix at scale.
- Notifications are email only, and the default backend prints to the console. SMS is not implemented.
- `FAKE_LLM` and `FAKE_EMBEDDINGS` are for development and tests. They use crude keyword and hashing logic, and the fake classifier cannot read photos.
- The free Gemini tier allows about 20 generation requests per day per model.
- SQLite is shared by the backend and scheduler containers (a 20 second lock timeout is set). A production deployment should use PostgreSQL.
- Uploaded photos are served by Django without a login check while `DEBUG` is on. Serve media through a proper web server in production.
- The Django settings default to development values. Set `SECRET_KEY`, `DEBUG=0` and `ALLOWED_HOSTS` before any real deployment.
