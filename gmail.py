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

GMAIL_USER        = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
IMAP_HOST         = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT         = int(os.getenv("IMAP_PORT", "993"))
SMTP_HOST         = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT         = int(os.getenv("SMTP_PORT", "465"))


def _decode_str(value) -> str:
    """Safely decodes email header values (handles encoded UTF-8, ISO-8859, etc.)."""
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
    """Collapses whitespace to reduce token usage when passing body to LLM."""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()


def _get_body(msg) -> str:
    """Extracts plain text body from a possibly multipart email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:
                    pass
    else:
        try:
            return msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace"
            )
        except Exception:
            pass
    return ""


def _sanitize_imap_query(query: str) -> str:
    """Removes characters that would break IMAP search syntax."""
    return query.replace('"', '').replace('\\', '').strip()


def _sync_list_emails(limit: int = 10) -> List[Dict]:
    emails = []
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select("INBOX")
        _, data = mail.search(None, "ALL")
        mail_ids = data[0].split()

        for m_id in reversed(mail_ids[-limit:]):
            try:
                _, msg_data = mail.fetch(m_id, "(RFC822)")
                for part in msg_data:
                    if isinstance(part, tuple):
                        msg = email.message_from_bytes(part[1])
                        body = _clean_body_text(_get_body(msg))
                        emails.append({
                            "id": m_id.decode(),
                            "subject": _decode_str(msg["Subject"]),
                            "from": _decode_str(msg["From"]),
                            "date": _decode_str(msg["Date"]),
                            "body": body[:200],
                        })
            except Exception as e:
                logger.error(f"[Gmail] Error reading email ID {m_id}: {e}")
                continue

        mail.logout()
    except Exception as e:
        logger.error(f"[Gmail] Failed to list emails: {e}")
    return emails


def _sync_read_email(message_id: str) -> Optional[Dict]:
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select("INBOX")
        _, data = mail.fetch(message_id.encode(), "(RFC822)")
        for part in data:
            if isinstance(part, tuple):
                msg = email.message_from_bytes(part[1])
                body = _get_body(msg)
                mail.logout()
                return {
                    "id": message_id,
                    "subject": _decode_str(msg["Subject"]),
                    "from": _decode_str(msg["From"]),
                    "date": _decode_str(msg["Date"]),
                    "body": body[:2000],
                }
        mail.logout()
    except Exception as e:
        logger.error(f"[Gmail] Failed to read email {message_id}: {e}")
    return None


def _sync_send_email(to: str, subject: str, body: str) -> bool:
    try:
        msg = MIMEMultipart()
        msg["From"] = GMAIL_USER
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.sendmail(GMAIL_USER, [to], msg.as_string())
        return True
    except Exception as e:
        logger.error(f"[Gmail] Failed to send email to {to}: {e}")
        return False


def _sync_search_emails(query: str, limit: int = 10) -> List[Dict]:
    """Searches emails by subject or sender using sanitized IMAP query."""
    safe_query = _sanitize_imap_query(query)
    emails = []
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select("INBOX")
        _, data = mail.search(None, f'OR SUBJECT "{safe_query}" FROM "{safe_query}"')
        mail_ids = data[0].split()

        for m_id in reversed(mail_ids[-limit:]):
            try:
                _, msg_data = mail.fetch(m_id, "(RFC822)")
                for part in msg_data:
                    if isinstance(part, tuple):
                        msg = email.message_from_bytes(part[1])
                        body = _clean_body_text(_get_body(msg))
                        emails.append({
                            "id": m_id.decode(),
                            "subject": _decode_str(msg["Subject"]),
                            "from": _decode_str(msg["From"]),
                            "date": _decode_str(msg["Date"]),
                            "body": body[:200],
                        })
            except Exception as e:
                logger.error(f"[Gmail] Error reading search result ID {m_id}: {e}")
                continue

        mail.logout()
    except Exception as e:
        logger.error(f"[Gmail] Search failed for '{query}': {e}")
    return emails


class GmailClient:
    """Wraps sync IMAP/SMTP calls in asyncio.to_thread to avoid blocking the FastAPI event loop."""

    async def get_mailboxes(self, account_id: int) -> List[Dict]:
        # Only INBOX is exposed for now; extend here to support labels/folders
        return [{"id": "INBOX", "name": "INBOX"}]

    async def get_messages(self, account_id: int, mailbox_id, limit: int = 10) -> List[Dict]:
        # Fetches the most recent `limit` messages from INBOX
        try:
            return await asyncio.to_thread(_sync_list_emails, limit)
        except Exception as e:
            logger.error(f"[Gmail] get_messages failed: {e}")
            return []

    async def get_message(self, account_id: int, mailbox_id, message_id) -> Optional[Dict]:
        # Fetches a single message by its IMAP sequence number
        try:
            return await asyncio.to_thread(_sync_read_email, str(message_id))
        except Exception as e:
            logger.error(f"[Gmail] get_message failed for ID {message_id}: {e}")
            return None

    async def send_message(self, account_id: int, to: str, subject: str, body: str, cc="", bcc="") -> bool:
        # Sends via SMTP SSL; cc/bcc accepted in signature but not yet wired through
        try:
            return await asyncio.to_thread(_sync_send_email, to, subject, body)
        except Exception as e:
            logger.error(f"[Gmail] send_message failed for {to}: {e}")
            return False

    async def search_messages(self, account_id: int, query: str, limit: int = 10) -> List[Dict]:
        # Searches by subject OR sender using IMAP OR operator
        try:
            return await asyncio.to_thread(_sync_search_emails, query, limit)
        except Exception as e:
            logger.error(f"[Gmail] search_messages failed for '{query}': {e}")
            return []


def get_mail_client() -> Optional[GmailClient]:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        logger.warning("[Gmail] GMAIL_USER or GMAIL_APP_PASSWORD missing from .env")
        return None
    return GmailClient()
