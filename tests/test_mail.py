"""Tests for the mail module: SMTP send path (retry + fresh connection), IMAP
list/search/read parsing, body extraction, and client selection.
"""

import smtplib
from email import message_from_string
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import mail
from mail import MailClient, _get_body


def _sample_email(subject="Hello", from_="alice@test", body="Test body"):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_
    msg["Date"] = "Thu, 15 Aug 2026 10:00:00 +0000"
    msg.set_content(body)
    return msg


class _FakeIMAP:
    def __init__(self, ids=("1", "2", "3", "4", "5"), fail_fetch=()):
        self.ids = list(ids)
        self.fail_fetch = set(fail_fetch)
        self.logged_out = False
        self.selects = []
        self.searches = []
        self.fetched = []

    def select(self, mailbox):
        self.selects.append(mailbox)
        return ("OK", [b"0"])

    def search(self, charset, criterion):
        self.searches.append(criterion)
        return ("OK", [b" ".join(i.encode() for i in self.ids)])

    def fetch(self, mid, parts):
        self.fetched.append(mid)
        if not self.ids:
            return ("OK", [])
        if mid in self.fail_fetch:
            raise OSError("fetch failed")
        i = mid.decode() if isinstance(mid, bytes) else str(mid)
        msg = _sample_email(subject=f"Subject {i}", from_="alice@test", body=f"Body {i}")
        return ("OK", [(None, msg.as_bytes())])

    def logout(self):
        self.logged_out = True


class _FakeSMTP:
    def __init__(self, fail_sends=0):
        self.fail_sends = fail_sends
        self.sent = []
        self.quitted = False

    def sendmail(self, from_addr, to_addrs, msg):
        if self.fail_sends > 0:
            self.fail_sends -= 1
            raise smtplib.SMTPRecipientsRefused({"x@y": (550, "no")})
        self.sent.append((from_addr, to_addrs, msg))

    def quit(self):
        self.quitted = True


class _SMTPFactory:
    """Callable returning a fresh _FakeSMTP per connection attempt.

    Only the first connection is configured to fail, so a retry that opens a
    fresh connection succeeds.
    """

    def __init__(self, fail_sends=1):
        self.fail_sends = fail_sends
        self.created = []

    def __call__(self):
        fail = 1 if self.fail_sends > 0 else 0
        self.fail_sends -= 1
        s = _FakeSMTP(fail_sends=fail)
        self.created.append(s)
        return s


class _FakeMail(MailClient):
    def __init__(self, imap=None, smtp=None):
        self._imap = imap
        self._smtp = smtp
        self._sender = "me@test"

    def _connect_imap(self):
        return self._imap

    def _connect_smtp(self):
        return self._smtp() if callable(self._smtp) else self._smtp

    def _get_sender_email(self):
        return self._sender

    def _login_smtp(self, smtp):
        pass


# -- SMTP send path --

def test_send_email_success():
    smtp = _FakeSMTP()
    client = _FakeMail(smtp=smtp)
    assert client._send_email("a@b.com", "Subj", "Body") is True
    assert smtp.sent and smtp.quitted
    from_addr, to_addrs, msg = smtp.sent[0]
    assert from_addr == "me@test"
    assert "a@b.com" in to_addrs
    parsed = message_from_string(msg)  # MIMEText utf-8 bodies are base64-encoded
    assert _get_body(parsed).strip() == "Body"


def test_send_email_retries_with_fresh_connection():
    factory = _SMTPFactory(fail_sends=1)
    client = _FakeMail(smtp=factory)
    assert client._send_email("a@b.com", "Subj", "Body") is True
    assert len(factory.created) == 2  # one fresh connection per attempt
    assert factory.created[1].sent  # delivered on the second (fresh) connection
    assert factory.created[0].quitted  # failed connection still quit cleanly


def test_send_email_returns_false_after_all_retries():
    factory = _SMTPFactory(fail_sends=99)
    client = _FakeMail(smtp=factory)
    assert client._send_email("a@b.com", "Subj", "Body") is False
    assert len(factory.created) == 2


# -- IMAP read path --

def test_list_emails_limits_and_parses():
    imap = _FakeIMAP(ids=("1", "2", "3", "4", "5"))
    client = _FakeMail(imap=imap)
    emails = client._list_emails(limit=3)
    assert len(emails) == 3
    assert emails[0]["id"] == "5"  # newest first
    assert emails[0]["subject"] == "Subject 5"
    assert emails[0]["from"] == "alice@test"
    assert emails[0]["body"] == "Body 5"
    assert imap.logged_out


def test_list_emails_skips_failed_fetch():
    imap = _FakeIMAP(ids=("1", "2", "3"), fail_fetch=(b"2",))
    client = _FakeMail(imap=imap)
    emails = client._list_emails(limit=10)
    assert [e["id"] for e in emails] == ["3", "1"]


def test_search_emails_sanitizes_query():
    imap = _FakeIMAP(ids=("7",))
    client = _FakeMail(imap=imap)
    emails = client._search_emails('in"jection\\ query', limit=5)
    assert len(emails) == 1
    criterion = imap.searches[0]
    assert "\\" not in criterion
    assert "injection query" in criterion  # quotes stripped from the query value


def test_read_email_missing_returns_none():
    imap = _FakeIMAP(ids=())
    client = _FakeMail(imap=imap)
    assert client._read_email("123") is None


def test_async_wrappers_offload(monkeypatch):
    client = _FakeMail(imap=_FakeIMAP(ids=("1",)))
    client._list_emails = lambda limit=10, mailbox="INBOX": [{"id": "1"}]
    import asyncio
    result = asyncio.run(client.get_messages(1, None, limit=5))
    assert result == [{"id": "1"}]


# -- Body extraction --

def test_get_body_plain():
    msg = EmailMessage()
    msg.set_content("Hello world")
    assert _get_body(msg).strip() == "Hello world"


def test_get_body_multipart_skips_html_and_attachments():
    msg = MIMEMultipart()
    text = MIMEText("the plain part", "plain")
    html = MIMEText("<p>the html part</p>", "html")
    att = MIMEText("attached text", "plain")
    att.add_header("Content-Disposition", "attachment", filename="notes.txt")
    msg.attach(text)
    msg.attach(html)
    msg.attach(att)
    assert _get_body(msg) == "the plain part"


# -- Client selection --

def test_get_active_mail_client_provider_selection(monkeypatch):
    import config

    monkeypatch.setenv("MAIL_PROVIDER", "proton")
    monkeypatch.setattr(config, "PROTON_USER", "u")
    monkeypatch.setattr(config, "PROTON_PASSWORD", "p")
    mail._mail_clients.clear()
    assert isinstance(mail.get_active_mail_client(), mail.ProtonMailClient)


def test_get_active_mail_client_missing_creds_returns_none(monkeypatch):
    import config

    monkeypatch.setenv("MAIL_PROVIDER", "proton")
    monkeypatch.setattr(config, "PROTON_USER", "")
    monkeypatch.setattr(config, "PROTON_PASSWORD", "")
    mail._mail_clients.clear()
    assert mail.get_active_mail_client() is None


def test_get_active_mail_client_no_provider(monkeypatch):
    monkeypatch.delenv("MAIL_PROVIDER", raising=False)
    mail._mail_clients.clear()
    assert mail.get_active_mail_client() is None
