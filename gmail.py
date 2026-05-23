import imaplib
import smtplib
import email
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from typing import List, Dict, Optional
import asyncio
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))


def _decode_str(value) -> str:
    """Decode email headers properly."""
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


def _get_body(msg) -> str:
    """Extract plain text body from email."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return ""


def _sync_list_emails(limit: int = 10) -> List[Dict]:
    """List recent emails via IMAP (sync)."""
    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
        imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        imap.select("INBOX")
        _, data = imap.search(None, "ALL")
        ids = data[0].split()
        recent_ids = ids[-limit:][::-1]

        messages = []
        for uid in recent_ids:
            _, msg_data = imap.fetch(uid, "(RFC822.HEADER)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            messages.append({
                "id": uid.decode(),
                "from": _decode_str(msg.get("From", "")),
                "subject": _decode_str(msg.get("Subject", "(no subject)")),
                "date": msg.get("Date", ""),
            })
        return messages


def _sync_read_email(uid: str) -> Optional[Dict]:
    """Read a specific email via IMAP (sync)."""
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
            "body": _get_body(msg)[:2000],
        }


def _sync_search_emails(query: str, limit: int = 10) -> List[Dict]:
    """Search emails via IMAP (sync)."""
    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
        imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        imap.select("INBOX")
        _, data = imap.search(None, f'(OR SUBJECT "{query}" FROM "{query}")')
        ids = data[0].split()
        recent_ids = ids[-limit:][::-1]

        messages = []
        for uid in recent_ids:
            _, msg_data = imap.fetch(uid, "(RFC822.HEADER)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            messages.append({
                "id": uid.decode(),
                "from": _decode_str(msg.get("From", "")),
                "subject": _decode_str(msg.get("Subject", "(no subject)")),
                "date": msg.get("Date", ""),
            })
        return messages


def _sync_send_email(to: str, subject: str, body: str) -> bool:
    """Send an email via SMTP (sync)."""
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        smtp.sendmail(GMAIL_USER, to, msg.as_string())
    return True


class GmailClient:
    """Gmail IMAP/SMTP client."""

    async def get_accounts(self) -> List[Dict]:
        return [{"id": 1, "emailAddress": GMAIL_USER}]

    async def get_mailboxes(self, account_id: int) -> List[Dict]:
        return [{"id": "INBOX", "name": "INBOX"}]

    async def get_messages(self, account_id: int, mailbox_id, limit: int = 10) -> List[Dict]:
        try:
            return await asyncio.to_thread(_sync_list_emails, limit)
        except Exception as e:
            print(f"[Gmail] Failed to fetch messages: {e}")
            return []

    async def get_message(self, account_id: int, mailbox_id, message_id) -> Optional[Dict]:
        try:
            return await asyncio.to_thread(_sync_read_email, str(message_id))
        except Exception as e:
            print(f"[Gmail] Failed to read message: {e}")
            return None

    async def send_message(self, account_id: int, to: str, subject: str, body: str, cc="", bcc="") -> bool:
        try:
            return await asyncio.to_thread(_sync_send_email, to, subject, body)
        except Exception as e:
            print(f"[Gmail] Failed to send: {e}")
            return False

    async def search_messages(self, account_id: int, query: str, limit: int = 10) -> List[Dict]:
        try:
            return await asyncio.to_thread(_sync_search_emails, query, limit)
        except Exception as e:
            print(f"[Gmail] Search failed: {e}")
            return []


def get_mail_client() -> Optional[GmailClient]:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("[Gmail] GMAIL_USER or GMAIL_APP_PASSWORD missing from .env")
        return None
    return GmailClient()
