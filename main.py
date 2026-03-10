"""
main.py — WhatsApp CRM Bridge — FastAPI webhook server

Receives WhatsApp Business API webhook events, performs AI sentiment analysis,
and logs messages to Google Sheets for CRM visibility.

Run locally:
    uvicorn main:app --reload --port 8000

Endpoints:
    GET  /           — Health check
    GET  /webhook    — Meta webhook verification challenge
    POST /webhook    — Incoming WhatsApp messages
"""

import os
import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Query, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from dotenv import load_dotenv

from models import WhatsAppWebhookPayload, ParsedMessage, HealthResponse
from sentiment import SentimentAnalyzer
from sheets import SheetsLogger

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("whatsapp-crm-bridge")

# ── Configuration ─────────────────────────────────────────────────────────────

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET")

if not WHATSAPP_VERIFY_TOKEN:
    raise RuntimeError("WHATSAPP_VERIFY_TOKEN must be set in .env")
if not WHATSAPP_APP_SECRET:
    raise RuntimeError("WHATSAPP_APP_SECRET must be set in .env")

# ── Service Initialization ────────────────────────────────────────────────────

sentiment_analyzer: Optional[SentimentAnalyzer] = None
sheets_logger: Optional[SheetsLogger] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize external service clients on startup."""
    global sentiment_analyzer, sheets_logger

    logger.info("Initializing WhatsApp CRM Bridge...")

    try:
        sentiment_analyzer = SentimentAnalyzer()
        logger.info("Sentiment analyzer ready.")
    except ValueError as e:
        logger.error("Failed to initialize sentiment analyzer: %s", e)

    try:
        sheets_logger = SheetsLogger()
        logger.info("Google Sheets logger ready.")
    except (ValueError, FileNotFoundError) as e:
        logger.error("Failed to initialize Sheets logger: %s", e)

    logger.info("WhatsApp CRM Bridge is running.")
    yield
    logger.info("Shutting down.")


# ── FastAPI App ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="WhatsApp CRM Bridge",
    description=(
        "Receives WhatsApp Business API webhooks, analyzes message sentiment with Claude AI, "
        "and logs everything to Google Sheets."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)


# ── Signature Verification ────────────────────────────────────────────────────

def verify_signature(payload_body: bytes, signature_header: Optional[str]) -> bool:
    """
    Verify the X-Hub-Signature-256 header from Meta.

    Meta signs the payload with your app secret using HMAC-SHA256.
    Always verify to prevent spoofed webhook calls.
    """
    if not signature_header:
        return False

    if not signature_header.startswith("sha256="):
        return False

    expected_signature = signature_header[len("sha256="):]
    computed = hmac.new(
        WHATSAPP_APP_SECRET.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, expected_signature)


# ── Message Parsing ───────────────────────────────────────────────────────────

def parse_incoming_messages(payload: WhatsAppWebhookPayload) -> list[ParsedMessage]:
    """
    Extract all incoming messages from a WhatsApp webhook payload.

    Skips status updates (delivered, read receipts) — only processes new messages.
    """
    parsed = []

    for entry in payload.entry:
        for change in entry.changes:
            value = change.value

            if not value.messages:
                continue  # Status update, not a message

            # Build a phone → display name lookup from contacts
            contact_names: dict[str, str] = {}
            if value.contacts:
                for contact in value.contacts:
                    contact_names[contact.wa_id] = contact.profile.name

            for message in value.messages:
                phone = message.from_
                display_name = contact_names.get(phone, phone)
                text = message.get_text_body()

                parsed.append(
                    ParsedMessage(
                        phone=phone,
                        display_name=display_name,
                        message_text=text,
                        message_type=message.type,
                        message_id=message.id,
                        timestamp=datetime.fromtimestamp(
                            int(message.timestamp), tz=timezone.utc
                        ).isoformat(),
                        raw_timestamp_unix=int(message.timestamp),
                    )
                )

    return parsed


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="ok")


@app.get("/webhook")
async def webhook_verify(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """
    Meta webhook verification endpoint.

    When you set up a webhook in the Meta App Dashboard, Meta sends a GET request
    to verify your endpoint. This handler validates the verify token and echoes
    the challenge back.
    """
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verification successful.")
        return PlainTextResponse(content=hub_challenge or "")

    logger.warning(
        "Webhook verification failed. Mode: %s, Token match: %s",
        hub_mode,
        hub_verify_token == WHATSAPP_VERIFY_TOKEN,
    )
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def webhook_receive(request: Request):
    """
    Main webhook handler for incoming WhatsApp messages.

    Flow:
      1. Verify X-Hub-Signature-256 header
      2. Parse WhatsApp webhook payload
      3. Extract incoming messages (skip status updates)
      4. Run AI sentiment analysis on each message
      5. Log to Google Sheets
      6. Return 200 immediately (Meta requires fast responses)
    """
    # Always return 200 first if signature is valid — Meta will retry on non-200
    body = await request.body()

    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(body, signature):
        logger.warning("Invalid webhook signature — possible spoofed request")
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Parse payload
    try:
        import json
        payload_dict = json.loads(body)
        payload = WhatsAppWebhookPayload(**payload_dict)
    except Exception as e:
        logger.error("Failed to parse webhook payload: %s", e)
        # Return 200 anyway — malformed payloads shouldn't cause Meta to retry
        return JSONResponse(content={"status": "parse_error"}, status_code=200)

    # Extract messages
    messages = parse_incoming_messages(payload)

    if not messages:
        # Status updates (delivered/read receipts) — acknowledge and exit
        return JSONResponse(content={"status": "ok", "processed": 0})

    logger.info("Processing %d incoming message(s)", len(messages))

    processed_count = 0
    for msg in messages:
        # AI Sentiment Analysis
        sentiment_result = {"sentiment": "neutral", "score": 5, "summary": "", "action_needed": False}
        if sentiment_analyzer:
            try:
                sentiment_result = sentiment_analyzer.analyze(msg.message_text)
            except Exception as e:
                logger.error("Sentiment analysis failed for %s: %s", msg.phone, e)

        # Log to Google Sheets
        if sheets_logger:
            success = sheets_logger.append_message(
                phone=msg.phone,
                display_name=msg.display_name,
                message=msg.message_text,
                message_type=msg.message_type,
                sentiment=sentiment_result["sentiment"],
                score=sentiment_result["score"],
                action_needed=sentiment_result["action_needed"],
                summary=sentiment_result["summary"],
                message_id=msg.message_id,
                timestamp=msg.timestamp,
            )
            if success:
                processed_count += 1
                logger.info(
                    "Logged: %s | %s | %s (score: %d)",
                    msg.phone,
                    sentiment_result["sentiment"],
                    msg.message_text[:60],
                    sentiment_result["score"],
                )
        else:
            logger.warning("Sheets logger not available — message not logged")

    return JSONResponse(content={"status": "ok", "processed": processed_count})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
