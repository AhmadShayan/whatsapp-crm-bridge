"""
models.py — Pydantic models for WhatsApp Business API webhook payloads

Reference: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples
"""

from typing import Optional, List, Any
from pydantic import BaseModel, Field


# ── WhatsApp Webhook Payload Models ──────────────────────────────────────────

class WhatsAppProfile(BaseModel):
    name: str


class WhatsAppContact(BaseModel):
    profile: WhatsAppProfile
    wa_id: str


class WhatsAppTextContent(BaseModel):
    body: str


class WhatsAppImageContent(BaseModel):
    mime_type: Optional[str] = None
    sha256: Optional[str] = None
    id: Optional[str] = None
    caption: Optional[str] = None


class WhatsAppAudioContent(BaseModel):
    mime_type: Optional[str] = None
    sha256: Optional[str] = None
    id: Optional[str] = None
    voice: Optional[bool] = None


class WhatsAppDocumentContent(BaseModel):
    mime_type: Optional[str] = None
    sha256: Optional[str] = None
    id: Optional[str] = None
    filename: Optional[str] = None


class WhatsAppMessage(BaseModel):
    id: str
    from_: str = Field(alias="from")
    timestamp: str
    type: str  # "text", "image", "audio", "document", "sticker", "location", etc.
    text: Optional[WhatsAppTextContent] = None
    image: Optional[WhatsAppImageContent] = None
    audio: Optional[WhatsAppAudioContent] = None
    document: Optional[WhatsAppDocumentContent] = None

    model_config = {"populate_by_name": True}

    def get_text_body(self) -> str:
        """Return the message text regardless of content type."""
        if self.text:
            return self.text.body
        if self.image and self.image.caption:
            return f"[Image] {self.image.caption}"
        if self.image:
            return "[Image message]"
        if self.audio:
            return "[Audio message]"
        if self.document:
            name = self.document.filename or "document"
            return f"[Document: {name}]"
        return f"[{self.type} message]"


class WhatsAppStatus(BaseModel):
    id: str
    status: str  # "sent", "delivered", "read", "failed"
    timestamp: str
    recipient_id: str


class WhatsAppValue(BaseModel):
    messaging_product: str
    metadata: dict
    contacts: Optional[List[WhatsAppContact]] = None
    messages: Optional[List[WhatsAppMessage]] = None
    statuses: Optional[List[WhatsAppStatus]] = None


class WhatsAppChange(BaseModel):
    value: WhatsAppValue
    field: str


class WhatsAppEntry(BaseModel):
    id: str
    changes: List[WhatsAppChange]


class WhatsAppWebhookPayload(BaseModel):
    object: str
    entry: List[WhatsAppEntry]


# ── Application Response Models ───────────────────────────────────────────────

class ParsedMessage(BaseModel):
    """Normalised message ready for downstream processing."""
    phone: str
    display_name: str
    message_text: str
    message_type: str
    message_id: str
    timestamp: str
    raw_timestamp_unix: int


class SentimentResult(BaseModel):
    """Result from the AI sentiment analyser."""
    sentiment: str  # "positive" | "neutral" | "negative" | "urgent"
    score: int      # 0–10
    summary: str
    action_needed: bool


class ProcessedMessage(BaseModel):
    """Full processed message with sentiment, ready for Sheets logging."""
    parsed: ParsedMessage
    sentiment: SentimentResult


class WebhookVerifyResponse(BaseModel):
    challenge: str


class HealthResponse(BaseModel):
    status: str
    version: str = "1.0.0"
