"""Signature normalization for collective learning (Phase 2).

Collapses personally-identifying surface forms to typed placeholders so
cross-user duplicates share one signature ("Ahmet'e mail at" and
"Mehmet'e mail at" are the same routing shape) and raw PII never becomes
a global corpus entry. Deterministic regex only — no NER model (Pi budget);
runs lazily on feeder candidates, never per message.

Deliberate residual: person names without contact markers are NOT masked
(no reliable Turkish NER at this cost); quorum + admin review mitigate.
"""

import re

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
# +90 555 123 45 67 / 0555 123 45 67 / 555-123-45-67 style runs: a leading
# +/0/parenthesis plus at least 7 more digits allowing separators.
_PHONE_RE = re.compile(r"(?:\+\d[\d\s().-]{6,}\d|\(?0\d{2,3}\)?[\s.-]?\d[\d\s.-]{5,}\d)")
_DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b")
# Long digit runs: IDs, IBAN fragments, amounts. Short numbers (quantities,
# ordinals like "2. not") keep their routing signal, so they stay.
_NUMBER_RE = re.compile(r"\b\d{5,}\b")
_WS_RE = re.compile(r"\s+")


def normalize_signature(text: str) -> str:
    """Return the shareable routing signature of a user sentence."""
    sig = (text or "").strip().casefold()
    sig = _EMAIL_RE.sub("[email]", sig)
    sig = _URL_RE.sub("[url]", sig)
    sig = _PHONE_RE.sub("[phone]", sig)
    sig = _DATE_RE.sub("[date]", sig)
    sig = _NUMBER_RE.sub("[number]", sig)
    return _WS_RE.sub(" ", sig).strip()
