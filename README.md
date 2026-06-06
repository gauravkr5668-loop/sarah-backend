# Sarah — Backend

Production-ready Flask backend for the **Sarah** receptionist system.

Receives Vapi end-of-call webhooks, extracts structured lead data, persists
it to SQLite, and forwards it to Make.com for downstream automation.

---

## Project Structure

```
veronica-ai/
├── app.py                        # WSGI entry point (Gunicorn target)
├── Procfile                      # Railway process definition
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variable template
├── .gitignore
├── README.md
└── app/
    ├── __init__.py               # App factory (create_app)
    ├── models/
    │   └── database.py           # SQLite schema + CRUD helpers
    ├── routes/
    │   ├── health.py             # GET  /
    │   └── webhooks.py           # POST /call-end
    └── services/
        ├── call_service.py       # Normalise raw Vapi payload
        ├── lead_service.py       # Extract lead fields from transcript
        └── make_service.py       # Forward lead to Make.com webhook
```

---

## Endpoints

| Method | Path        | Description                          |
|--------|-------------|--------------------------------------|
| GET    | `/`         | Health check — returns `{"status":"ok"}` |
| POST   | `/call-end` | Vapi end-of-call webhook receiver    |

---

## Environment Variables

| Variable          | Required | Description                                      |
|-------------------|----------|--------------------------------------------------|
| `PORT`            | Railway  | Injected automatically by Railway                |
| `MAKE_WEBHOOK_URL`| Yes      | Full HTTPS URL of your Make.com custom webhook   |
| `SECRET_TOKEN`    | Optional | Bearer token checked on `/call-end` requests     |
| `DATABASE_PATH`   | Optional | SQLite file path (default: `veronica.db`)        |
| `LOG_LEVEL`       | Optional | `DEBUG` / `INFO` / `WARNING` (default: `INFO`)   |

---

## Local Development

```bash
# 1. Clone and enter the project
git clone https://github.com/YOUR_USERNAME/veronica-ai.git
cd veronica-ai

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and fill in MAKE_WEBHOOK_URL and SECRET_TOKEN

# 5. Run locally
python app.py
# Server starts at http://localhost:5000

# 6. Test the health endpoint
curl http://localhost:5000/
# → {"service":"Sarah","status":"ok"}

# 7. Simulate a Vapi webhook
curl -X POST http://localhost:5000/call-end \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_SECRET_TOKEN" \
  -d '{
    "message": {
      "call": {
        "id": "test-call-001",
        "endedAt": "2024-01-01T10:00:00Z",
        "duration": 90,
        "endedReason": "customer-ended-call",
        "customer": { "number": "+61412345678" },
        "transcript": "AI: Thanks for calling. May I get your name?\nCustomer: Hi, my name is Sarah Johnson. I am calling from Parramatta. I have a burst pipe and need someone urgently today.",
        "summary": "Customer Sarah Johnson from Parramatta has a burst pipe emergency. Requires urgent same-day attendance."
      }
    }
  }'
```

---

## Deploy to Railway

### Option A — Railway CLI

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and initialise
railway login
railway init

# Set environment variables
railway variables set MAKE_WEBHOOK_URL=https://hook.eu1.make.com/YOUR_ID
railway variables set SECRET_TOKEN=your_long_random_secret
railway variables set DATABASE_PATH=/tmp/veronica.db
railway variables set LOG_LEVEL=INFO

# Deploy
railway up
```

### Option B — GitHub Integration (recommended)

1. Push this repo to GitHub.
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
3. Select your repository.
4. Add environment variables in the Railway dashboard under **Variables**.
5. Railway auto-detects the `Procfile` and deploys.

### Persistent Database on Railway

Railway's filesystem is ephemeral. For a persistent SQLite DB:

1. Add a **Railway Volume** to your service.
2. Mount it at `/data`.
3. Set `DATABASE_PATH=/data/veronica.db`.

---

## Vapi Webhook Configuration

1. In your Vapi dashboard, open your Assistant.
2. Go to **Advanced → Webhook**.
3. Set **Server URL** to:
   ```
   https://YOUR-RAILWAY-APP.up.railway.app/call-end
   ```
4. Set **Server URL Secret** to your `SECRET_TOKEN` value.
5. Enable the **End of Call Report** event.

---

## Make.com Setup

1. Create a new **Scenario** in Make.com.
2. Add a **Custom Webhook** as the trigger module.
3. Copy the webhook URL and paste it into `MAKE_WEBHOOK_URL`.
4. The payload Sarah sends looks like:

```json
{
  "call_id":     "vapi-call-abc123",
  "caller_name": "Sarah Johnson",
  "phone":       "+61412345678",
  "suburb":      "Parramatta",
  "service":     "Plumbing - Burst Pipe",
  "urgency":     "emergency",
  "summary":     "Customer has a burst pipe emergency requiring same-day attendance.",
  "source":      "Sarah"
}
```

5. Connect downstream modules: Gmail, Slack, HubSpot, Google Sheets, etc.

---

## Database Schema

```sql
CREATE TABLE calls (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT    NOT NULL,
    call_id      TEXT    UNIQUE,
    caller_name  TEXT,
    phone        TEXT,
    suburb       TEXT,
    service      TEXT,
    urgency      TEXT,
    summary      TEXT,
    transcript   TEXT,
    raw_json     TEXT
);
```

---

## License

MIT — built for Sarah.
