"""
sheets.py — Google Sheets integration for WhatsApp CRM logging

Appends incoming WhatsApp messages with sentiment analysis to a Google Sheet.
Uses gspread with service account authentication.

Sheet column structure:
  Timestamp | Phone | Name | Message | Type | Sentiment | Score | Action Needed | Summary
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Google API scopes required
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

# Expected sheet header row (will be created if sheet is empty)
HEADER_ROW = [
    "Timestamp",
    "Phone",
    "Display Name",
    "Message",
    "Message Type",
    "Sentiment",
    "Score",
    "Action Needed",
    "Summary",
    "Message ID",
]


class SheetsLogger:
    """
    Appends WhatsApp messages with AI sentiment analysis to Google Sheets.

    Usage:
        logger = SheetsLogger()
        logger.append_message(
            phone="+1234567890",
            display_name="John Smith",
            message="I need help with my order",
            message_type="text",
            sentiment="urgent",
            score=2,
            action_needed=True,
            summary="Customer needs urgent order assistance",
            message_id="wamid.xxx",
            timestamp="2026-03-10T09:00:00Z"
        )
    """

    def __init__(
        self,
        sheet_id: Optional[str] = None,
        service_account_path: Optional[str] = None,
    ):
        """
        Initialize the Sheets logger.

        Args:
            sheet_id: Google Sheets document ID. Defaults to GOOGLE_SHEETS_ID env var.
            service_account_path: Path to service account JSON. Defaults to GOOGLE_SERVICE_ACCOUNT_JSON env var.
        """
        self.sheet_id = sheet_id or os.getenv("GOOGLE_SHEETS_ID")
        if not self.sheet_id:
            raise ValueError("GOOGLE_SHEETS_ID is required.")

        sa_path = service_account_path or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not sa_path:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON path is required.")

        self._client = self._authenticate(sa_path)
        self._worksheet: Optional[gspread.Worksheet] = None

    def _authenticate(self, service_account_path: str) -> gspread.Client:
        """Authenticate with Google Sheets API using a service account."""
        if not os.path.exists(service_account_path):
            raise FileNotFoundError(
                f"Service account file not found: {service_account_path}. "
                "Download it from Google Cloud Console → IAM → Service Accounts."
            )

        creds = Credentials.from_service_account_file(service_account_path, scopes=SCOPES)
        return gspread.authorize(creds)

    def _get_worksheet(self) -> gspread.Worksheet:
        """
        Get (or create) the 'WhatsApp Messages' worksheet.
        Adds a header row if the sheet is empty.
        """
        if self._worksheet is not None:
            return self._worksheet

        spreadsheet = self._client.open_by_key(self.sheet_id)

        # Try to open existing sheet, create if not found
        try:
            ws = spreadsheet.worksheet("WhatsApp Messages")
        except gspread.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(
                title="WhatsApp Messages", rows=1000, cols=len(HEADER_ROW)
            )
            logger.info("Created 'WhatsApp Messages' worksheet.")

        # Add header row if sheet is empty
        if ws.row_count == 0 or not ws.row_values(1):
            ws.append_row(HEADER_ROW, value_input_option="USER_ENTERED")
            logger.info("Added header row to worksheet.")

        self._worksheet = ws
        return ws

    def append_message(
        self,
        phone: str,
        display_name: str,
        message: str,
        message_type: str,
        sentiment: str,
        score: int,
        action_needed: bool,
        summary: str,
        message_id: str = "",
        timestamp: Optional[str] = None,
    ) -> bool:
        """
        Append a processed WhatsApp message row to Google Sheets.

        Args:
            phone: Customer's phone number (E.164 format).
            display_name: Customer's WhatsApp display name.
            message: Message text content.
            message_type: WhatsApp message type (text, image, audio, etc.).
            sentiment: AI-classified sentiment (positive/neutral/negative/urgent).
            score: Sentiment score 0–10.
            action_needed: Whether human action is required today.
            summary: AI-generated summary of the message.
            message_id: WhatsApp message ID (for deduplication).
            timestamp: ISO 8601 timestamp. Defaults to current UTC time.

        Returns:
            True if appended successfully, False on error.
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        row = [
            timestamp,
            phone,
            display_name,
            message[:500] if len(message) > 500 else message,  # Truncate long messages
            message_type,
            sentiment,
            score,
            "Yes" if action_needed else "No",
            summary,
            message_id,
        ]

        try:
            ws = self._get_worksheet()
            ws.append_row(row, value_input_option="USER_ENTERED")
            logger.info("Logged message from %s (sentiment: %s)", phone, sentiment)
            return True
        except gspread.exceptions.APIError as e:
            logger.error("Google Sheets API error: %s", e)
            return False
        except Exception as e:
            logger.error("Unexpected error appending to Sheets: %s", e)
            return False

    def get_recent_messages(self, limit: int = 50) -> list[dict]:
        """
        Retrieve the most recent messages from the sheet.

        Args:
            limit: Maximum number of rows to return.

        Returns:
            List of message dicts with header keys.
        """
        try:
            ws = self._get_worksheet()
            records = ws.get_all_records(head=1)
            return records[-limit:] if len(records) > limit else records
        except Exception as e:
            logger.error("Error reading from Sheets: %s", e)
            return []
