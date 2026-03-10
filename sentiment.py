"""
sentiment.py — AI-powered sentiment analysis for WhatsApp messages

Uses Claude Haiku for fast, cost-effective sentiment classification
with urgency detection and action recommendations.
"""

import os
import json
import re
import logging
from typing import Optional
import anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a customer sentiment analyzer for a business WhatsApp inbox.

Analyze the customer message and return a JSON object with these exact fields:
- "sentiment": one of "positive", "neutral", "negative", "urgent"
  - Use "urgent" when the customer needs immediate help (angry + time-sensitive, outage, emergency)
  - Use "negative" for complaints or dissatisfaction without urgency
  - Use "positive" for praise, thanks, or satisfaction
  - Use "neutral" for questions, general inquiries, or ambiguous messages
- "score": integer from 0 (most negative/urgent) to 10 (most positive)
- "summary": a 1-sentence business-ready summary of what the customer wants or is expressing
- "action_needed": true if a human response is required today, false if it can wait

Respond ONLY with valid JSON. No markdown, no explanation."""


class SentimentAnalyzer:
    """
    Analyzes customer messages for sentiment, urgency, and required action.

    Usage:
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("My order hasn't arrived and I need it today!")
        # result.sentiment == "urgent"
        # result.score == 2
        # result.action_needed == True
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the analyzer.

        Args:
            api_key: Anthropic API key. Defaults to ANTHROPIC_API_KEY env var.
        """
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required. Set it in your .env file."
            )
        self.client = anthropic.Anthropic(api_key=key)

    def analyze(self, text: str) -> dict:
        """
        Analyze the sentiment of a message.

        Args:
            text: Customer message text.

        Returns:
            dict with keys: sentiment, score (int), summary, action_needed (bool)
        """
        if not text or text.strip() in ("[Image message]", "[Audio message]"):
            return {
                "sentiment": "neutral",
                "score": 5,
                "summary": "Non-text message received",
                "action_needed": False,
            }

        # Truncate very long messages
        truncated = text[:800] if len(text) > 800 else text

        try:
            message = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=250,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": truncated}],
            )
            raw = message.content[0].text.strip()
            return self._parse_response(raw)
        except anthropic.APIError as e:
            logger.error("Anthropic API error during sentiment analysis: %s", e)
            return self._fallback_sentiment(text)
        except Exception as e:
            logger.error("Unexpected error in sentiment analysis: %s", e)
            return self._fallback_sentiment(text)

    def _parse_response(self, raw: str) -> dict:
        """Parse and validate the JSON response from Claude."""
        # Strip markdown fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"```\s*$", "", raw, flags=re.MULTILINE).strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Could not parse sentiment JSON: %s", raw)
            return self._fallback_sentiment("")

        valid_sentiments = {"positive", "neutral", "negative", "urgent"}
        sentiment = data.get("sentiment", "neutral")
        if sentiment not in valid_sentiments:
            sentiment = "neutral"

        score = int(data.get("score", 5))
        score = max(0, min(10, score))

        return {
            "sentiment": sentiment,
            "score": score,
            "summary": str(data.get("summary", "Unable to summarize")),
            "action_needed": bool(data.get("action_needed", False)),
        }

    def _fallback_sentiment(self, text: str) -> dict:
        """Return a safe fallback when analysis fails."""
        # Basic keyword-based urgency detection as fallback
        urgent_keywords = ["urgent", "asap", "immediately", "emergency", "help", "broken", "not working"]
        is_urgent = any(kw in text.lower() for kw in urgent_keywords)

        return {
            "sentiment": "urgent" if is_urgent else "neutral",
            "score": 3 if is_urgent else 5,
            "summary": "AI analysis unavailable — manual review needed",
            "action_needed": True,
        }
