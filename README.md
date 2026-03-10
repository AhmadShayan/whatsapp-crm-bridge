# WhatsApp CRM Bridge

> A FastAPI webhook server that receives WhatsApp Business API messages, runs AI sentiment analysis with Claude, and logs everything to Google Sheets — giving your team a real-time CRM view of every customer conversation.

## What It Does

```
WhatsApp message received
        ↓
FastAPI webhook (signature verified)
        ↓
Claude Haiku sentiment analysis
 → sentiment: urgent / negative / neutral / positive
 → score: 0–10
 → summary: "Customer reports login error, needs immediate help"
 → action_needed: true
        ↓
Google Sheets row appended
 Timestamp | Phone | Name | Message | Sentiment | Score | Action | Summary
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Run locally

```bash
uvicorn main:app --reload --port 8000
```

### 4. Expose with ngrok (for Meta webhook testing)

```bash
ngrok http 8000
# Copy the https:// URL for Meta App Dashboard
```

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `GET` | `/webhook` | Meta webhook verification challenge |
| `POST` | `/webhook` | Incoming WhatsApp messages |
| `GET` | `/docs` | Interactive API docs (Swagger UI) |

---

## Google Sheets Output

The bridge automatically creates a "WhatsApp Messages" worksheet with these columns:

| Timestamp | Phone | Display Name | Message | Type | Sentiment | Score | Action Needed | Summary | Message ID |
|---|---|---|---|---|---|---|---|---|---|
| 2026-03-10T09:15:00Z | +92304... | John Smith | My order hasn't arrived... | text | urgent | 2 | Yes | Customer needs urgent... | wamid.xxx |

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `WHATSAPP_VERIFY_TOKEN` | Yes | Your custom token for Meta webhook verification |
| `WHATSAPP_APP_SECRET` | Yes | Meta app secret (used to verify request signatures) |
| `ANTHROPIC_API_KEY` | Yes | From [console.anthropic.com](https://console.anthropic.com) |
| `GOOGLE_SHEETS_ID` | Yes | The ID from your Google Sheet URL |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Yes | Path to downloaded service account JSON file |
| `PORT` | No | Server port (default: 8000) |

---

## Setup Guides

### Meta WhatsApp Business API Setup

1. Go to [developers.facebook.com](https://developers.facebook.com) → Create App → Business
2. Add **WhatsApp** product
3. Under **Webhooks**, enter your server URL: `https://your-domain.com/webhook`
4. Set your `WHATSAPP_VERIFY_TOKEN` (any secret string you choose)
5. Subscribe to the `messages` field
6. Copy your App Secret from **App Settings → Basic**

### Google Sheets Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → Enable **Google Sheets API** and **Google Drive API**
3. Create a **Service Account** → Download JSON key
4. Create a new Google Sheet → Share it with the service account email (`...@....iam.gserviceaccount.com`) with **Editor** access
5. Copy the Sheet ID from the URL

---

## Docker Deployment

```bash
# Build and run with Docker Compose
cd deploy
docker-compose up -d

# View logs
docker-compose logs -f whatsapp-crm-bridge
```

For production, sit this behind nginx with SSL — Meta requires HTTPS for webhooks.

---

## Sentiment Categories

| Sentiment | Score Range | Example | Action Needed |
|---|---|---|---|
| `urgent` | 0–3 | "IT'S BROKEN AND I HAVE A DEMO IN 1 HOUR" | Always |
| `negative` | 1–5 | "I'm quite disappointed with the service" | Usually |
| `neutral` | 4–7 | "What are your business hours?" | Sometimes |
| `positive` | 7–10 | "Thank you so much, this was perfect!" | Rarely |

---

## Architecture

```
main.py          FastAPI app, webhook routes, signature verification
models.py        Pydantic models for WhatsApp payload parsing
sentiment.py     Claude Haiku AI sentiment analyzer
sheets.py        Google Sheets logger (gspread)
deploy/
  Dockerfile     Python 3.11 slim container
  docker-compose.yml
```

---

## Requirements

- Python 3.11+
- Anthropic API key
- WhatsApp Business API access (Meta Business Account)
- Google Cloud service account with Sheets API enabled

---

## License

MIT

---

> Built by [Ahmasoft](https://ahmasoft.com) — AI Automation Agency
