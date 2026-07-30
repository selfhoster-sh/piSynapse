"""piSynapse Mail
Unified IMAP/SMTP mail client supporting Gmail and ProtonMail (via ProtonBridge).
Base class handles shared IMAP/SMTP logic; provider-specific subclasses handle connection setup.
"""

import asyncio
import email
import imaplib
import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from utils import clean_body_text, decode_email_header, retry, sanitize_imap_query

logger = logging.getLogger("piSynapse")


class MailClient(ABC):
    """Abstract base for all mail providers."""

    @abstractmethod
    def _connect_imap(self) -> imaplib.IMAP4_SSL | imaplib.IMAP4:
        ...

    @abstractmethod
    def _get_sender_email(self) -> str:
        ...

    @abstractmethod
    def _login_smtp(self, smtp: smtplib.SMTP_SSL | smtplib.SMTP):
        ...

    @retry(attempts=2, delay=2.0)
    def _list_emails(self, limit: int = 10) -> list[dict]:
        emails = []
        mail = self._connect_imap()
        try:
            mail.select("INBOX")
            _, data = mail.search(None, "ALL")
            mail_ids = data[0].split()
            for m_id in reversed(mail_ids[-limit:]):
                try:
                    _, msg_data = mail.fetch(m_id, "(RFC822)")
                    for part in msg_data:
                        if isinstance(part, tuple):
                            msg = email.message_from_bytes(part[1])
                            body = clean_body_text(_get_body(msg))
                            emails.append({
                                "id": m_id.decode(),
                                "subject": decode_email_header(msg["Subject"]),
                                "from": decode_email_header(msg["From"]),
                                "date": decode_email_header(msg["Date"]),
                                "body": body[:300],
                            })
                except Exception as e:
                    logger.error(f"Error reading email {m_id}: {e}")
                    continue
        finally:
            _safe_logout(mail)
        return emails

    @retry(attempts=2, delay=2.0)
    def _read_email(self, message_id: str) -> dict | None:
        mail = self._connect_imap()
        try:
            mail.select("INBOX")
            _, data = mail.fetch(message_id.encode(), "(RFC822)")
            for part in data:
                if isinstance(part, tuple):
                    msg = email.message_from_bytes(part[1])
                    body = _get_body(msg)
                    return {
                        "id": message_id,
                        "subject": decode_email_header(msg["Subject"]),
                        "from": decode_email_header(msg["From"]),
                        "date": decode_email_header(msg["Date"]),
                        "body": body[:2000],
                    }
            return None
        finally:
            _safe_logout(mail)

    def _send_email(self, to: str, subject: str, body: str) -> bool:
        msg = MIMEMultipart()
        msg["From"] = self._get_sender_email()
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        smtp = self._connect_smtp()
        try:
            self._login_smtp(smtp)
            smtp.sendmail(self._get_sender_email(), [to], msg.as_string())
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to}: {e}")
            return False
        finally:
            _safe_smtp_quit(smtp)

    @retry(attempts=2, delay=2.0)
    def _search_emails(self, query: str, limit: int = 10) -> list[dict]:
        safe_query = sanitize_imap_query(query)
        emails = []
        mail = self._connect_imap()
        try:
            mail.select("INBOX")
            _, data = mail.search(None, f'OR TEXT "{safe_query}" OR SUBJECT "{safe_query}" FROM "{safe_query}"')
            mail_ids = data[0].split()
            for m_id in reversed(mail_ids[-limit:]):
                try:
                    _, msg_data = mail.fetch(m_id, "(RFC822)")
                    for part in msg_data:
                        if isinstance(part, tuple):
                            msg = email.message_from_bytes(part[1])
                            body = clean_body_text(_get_body(msg))
                            emails.append({
                                "id": m_id.decode(),
                                "subject": decode_email_header(msg["Subject"]),
                                "from": decode_email_header(msg["From"]),
                                "date": decode_email_header(msg["Date"]),
                                "body": body[:300],
                            })
                except Exception as e:
                    logger.error(f"Error in search result {m_id}: {e}")
                    continue
        finally:
            _safe_logout(mail)
        return emails

    # -- Async wrappers for FastAPI compatibility --

    async def get_messages(self, account_id: int, mailbox_id: Any, limit: int = 10) -> list[dict]:
        return await asyncio.to_thread(self._list_emails, limit)

    async def get_message(self, account_id: int, mailbox_id: Any, message_id) -> dict | None:
        return await asyncio.to_thread(self._read_email, str(message_id))

    async def send_message(self, account_id: int, to: str, subject: str, body: str, cc="", bcc="") -> bool:
        return await asyncio.to_thread(self._send_email, to, subject, body)

    async def search_messages(self, account_id: int, query: str, limit: int = 10) -> list[dict]:
        return await asyncio.to_thread(self._search_emails, query, limit)


# -- Gmail Implementation --

class GmailClient(MailClient):

    def __init__(self):
        from config import (
            GMAIL_APP_PASSWORD,
            GMAIL_USER,
            IMAP_HOST,
            IMAP_PORT,
            IMAP_TIMEOUT,
            SMTP_HOST,
            SMTP_PORT,
            SMTP_TIMEOUT,
        )
        self._user = GMAIL_USER
        self._password = GMAIL_APP_PASSWORD
        self._imap_host = IMAP_HOST
        self._imap_port = IMAP_PORT
        self._smtp_host = SMTP_HOST
        self._smtp_port = SMTP_PORT
        self._imap_timeout = IMAP_TIMEOUT
        self._smtp_timeout = SMTP_TIMEOUT

    def _connect_imap(self):
        mail = imaplib.IMAP4_SSL(self._imap_host, self._imap_port, timeout=self._imap_timeout)
        try:
            mail.login(self._user, self._password)
        except (imaplib.IMAP4.error, Exception) as _e:
            raise RuntimeError(f"IMAP login failed for {self._user}") from _e
        return mail

    def _connect_smtp(self):
        return smtplib.SMTP_SSL(self._smtp_host, self._smtp_port, timeout=self._smtp_timeout)

    def _get_sender_email(self) -> str:
        return self._user

    def _login_smtp(self, smtp):
        try:
            smtp.login(self._user, self._password)
        except smtplib.SMTPAuthenticationError as _e:
            raise RuntimeError(f"SMTP login failed for {self._user}") from _e


# -- ProtonMail Implementation --

class ProtonMailClient(MailClient):

    def __init__(self):
        from config import (
            IMAP_TIMEOUT,
            PROTON_IMAP_HOST,
            PROTON_IMAP_PORT,
            PROTON_PASSWORD,
            PROTON_SMTP_HOST,
            PROTON_SMTP_PORT,
            PROTON_USER,
            SMTP_TIMEOUT,
        )
        self._user = PROTON_USER
        self._password = PROTON_PASSWORD
        self._imap_host = PROTON_IMAP_HOST
        self._imap_port = PROTON_IMAP_PORT
        self._smtp_host = PROTON_SMTP_HOST
        self._smtp_port = PROTON_SMTP_PORT
        self._imap_timeout = IMAP_TIMEOUT
        self._smtp_timeout = SMTP_TIMEOUT
        self._ssl_ctx = ssl.create_default_context()
        if PROTON_IMAP_HOST in ("localhost", "127.0.0.1", "::1"):
            self._ssl_ctx.check_hostname = False
            self._ssl_ctx.verify_mode = ssl.CERT_NONE
        else:
            self._ssl_ctx.check_hostname = True
            self._ssl_ctx.verify_mode = ssl.CERT_REQUIRED

    def _connect_imap(self):
        mail = imaplib.IMAP4(self._imap_host, self._imap_port, timeout=self._imap_timeout)
        mail.starttls(ssl_context=self._ssl_ctx)
        try:
            mail.login(self._user, self._password)
        except (imaplib.IMAP4.error, Exception) as _e:
            raise RuntimeError(f"IMAP login failed for {self._user}") from _e
        return mail

    def _connect_smtp(self):
        smtp = smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=self._smtp_timeout)
        smtp.starttls(context=self._ssl_ctx)
        return smtp

    def _get_sender_email(self) -> str:
        return self._user

    def _login_smtp(self, smtp):
        try:
            smtp.login(self._user, self._password)
        except smtplib.SMTPAuthenticationError as _e:
            raise RuntimeError(f"SMTP login failed for {self._user}") from _e


# -- Helpers --

def _get_body(msg) -> str:
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


def _safe_logout(mail):
    try:
        mail.logout()
    except Exception:
        pass


def _safe_smtp_quit(smtp):
    try:
        smtp.quit()
    except Exception:
        pass


_mail_clients: dict[str, MailClient] = {}


def _get_or_create(provider: str, cls) -> MailClient:
    """Return cached instance or create a new one."""
    if provider not in _mail_clients:
        _mail_clients[provider] = cls()
    return _mail_clients[provider]


def get_active_mail_client() -> MailClient | None:
    """Returns a cached mail client based on MAIL_PROVIDER config.

    Reads MAIL_PROVIDER from os.environ at runtime so it can be changed
    via the settings API without restarting the server.
    Uses singleton pattern — each provider gets one shared instance.
    """
    import os

    from config import GMAIL_APP_PASSWORD, GMAIL_USER, PROTON_PASSWORD, PROTON_USER

    provider = os.environ.get("MAIL_PROVIDER", "gmail").lower()

    if provider == "proton":
        if PROTON_USER and PROTON_PASSWORD:
            return _get_or_create("proton", ProtonMailClient)
        logger.warning("[Mail] ProtonMail credentials missing")
        return None

    if provider == "auto":
        if PROTON_USER and PROTON_PASSWORD:
            return _get_or_create("proton", ProtonMailClient)
        if GMAIL_USER and GMAIL_APP_PASSWORD:
            return _get_or_create("gmail", GmailClient)
        return None

    # Default: Gmail
    if GMAIL_USER and GMAIL_APP_PASSWORD:
        return _get_or_create("gmail", GmailClient)
    return None
