import imaplib
import smtplib
import email
import os
import re
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from typing import List, Dict, Optional
import asyncio
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("piSynapse")

# Gmail IMAP/SMTP configuration
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))


# Email header and content processing helpers
def _decode_str(value) -> str:
    """Safely decode email headers with proper charset handling."""
    if value is None:
        return ""
    parts = decode_header(value)
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)


def _clean_body_text(text: str) -> str:
    """Normalize whitespace to optimize token usage for LLM processing."""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _get_body(msg, max_chars: Optional[int] = None) -> str:
    """Extract plain text body from email message, handling multipart and encoding."""
    body_str = ""

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    if max_chars and len(payload) > max_chars * 2:
                        payload = payload[:max_chars * 2]
                    body_str = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            if max_chars and len(payload) > max_chars * 2:
                payload = payload[:max_chars * 2]
            body_str = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")

    return _clean_body_text(body_str)


def _sanitize_imap_query(query: str) -> str:
    """Prevent IMAP injection by removing dangerous characters from search queries."""
    return query.replace('"', '').replace('\\', '').strip()


# Synchronous email operations (run in thread pool to avoid blocking async)
def _sync_list_emails(limit: int = 10) -> List[Dict]:
    """Fetch recent emails from inbox with metadata."""
    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
        imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        imap.select("INBOX")
        _, data = imap.search(None, "ALL")
        ids = data[0].split()
        recent_ids = ids[-limit:][::-1]

        messages = []
        for uid in recent_ids:
            try:
                _, msg_data = imap.fetch(uid, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                messages.append({
                    "id": uid.decode(),
                    "from": _decode_str(msg.get("From", "")),
                    "subject": _decode_str(msg.get("Subject", "(no subject)")),
                    "date": msg.get("Date", ""),
                    "body": _get_body(msg, max_chars=500)[:500],
                })
            except Exception as e:
                logger.error(f"[Gmail] Failed reading UID {uid}: {e}")
                continue
        return messages


def _sync_read_email(uid: str) -> Optional[Dict]:
    """Retrieve full email content by UID."""
    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
        imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        imap.select("INBOX")
        _, msg_data = imap.fetch(uid.encode(), "(RFC822)")
        if not msg_data or msg_data[0] is None:
            return None
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        return {
            "id": uid,
            "from": _decode_str(msg.get("From", "")),
            "subject": _decode_str(msg.get("Subject", "(no subject)")),
            "date": msg.get("Date", ""),
            "body": _get_body(msg, max_chars=2000)[:2000],
        }


def _sync_search_emails(query: str, limit: int = 10) -> List[Dict]:
    """Search emails by subject or sender with sanitized query."""
    safe_query = _sanitize_imap_query(query)
    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
        imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        imap.select("INBOX")
        _, data = imap.search(None, f'OR SUBJECT "{safe_query}" FROM "{safe_query}"')
        ids = data[0].split()
        recent_ids = ids[-limit:][::-1]

        messages = []
        for uid in recent_ids:
            try:
                _, msg_data = imap.fetch(uid, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                messages.append({
                    "id": uid.decode(),
                    "from": _decode_str(msg.get("From", "")),
                    "subject": _decode_str(msg.get("Subject", "(no subject)")),
                    "date": msg.get("Date", ""),
                    "body": _get_body(msg, max_chars=1500)[:1500],
                })
            except Exception as e:
                logger.error(f"[Gmail] Failed reading UID {uid} during search: {e}")
                continue
        return messages


def _sync_send_email(to: str, subject: str, body: str) -> bool:
    """Send email via SMTP."""
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        smtp.sendmail(GMAIL_USER, to, msg.as_string())
    return True


# Async wrapper for email operations
class GmailClient:
    """
    Async wrapper for Gmail IMAP/SMTP operations.
    Runs blocking I/O operations in thread pool to avoid blocking FastAPI event loop.
    """

    async def get_accounts(self) -> List[Dict]:
        """List configured Gmail accounts."""
        return [{"id": 1, "emailAddress": GMAIL_USER}]

    async def get_mailboxes(self, account_id: int) -> List[Dict]:
        """List mailboxes for account."""
        return [{"id": "INBOX", "name": "INBOX"}]

    async def get_messages(self, account_id: int, mailbox_id, limit: int = 10) -> List[Dict]:
        """Fetch recent messages from mailbox."""
        try:
            return await asyncio.to_thread(_sync_list_emails, limit)
        except Exception as e:
            logger.error(f"[Gmail] Failed to fetch messages: {e}")
            return []

    async def get_message(self, account_id: int, mailbox_id, message_id) -> Optional[Dict]:
        """Read specific message by ID."""
        try:
            return await asyncio.to_thread(_sync_read_email, str(message_id))
        except Exception as e:
            logger.error(f"[Gmail] Failed to read message {message_id}: {e}")
            return None

    async def send_message(self, account_id: int, to: str, subject: str, body: str, cc="", bcc="") -> bool:
        """Send email to recipient."""
        try:
            return await asyncio.to_thread(_sync_send_email, to, subject, body)
        except Exception as e:
            logger.error(f"[Gmail] Failed to send to {to}: {e}")
            return False

    async def search_messages(self, account_id: int, query: str, limit: int = 10) -> List[Dict]:
        """Search emails by keyword."""
        try:
            return await asyncio.to_thread(_sync_search_emails, query, limit)
        except Exception as e:
            logger.error(f"[Gmail] Search failed for query '{query}': {e}")
            return []


def get_mail_client() -> Optional[GmailClient]:
    """Initialize Gmail client if credentials are configured."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        logger.warning("[Gmail] GMAIL_USER or GMAIL_APP_PASSWORD missing from .env")
        return None
    return GmailClient()
