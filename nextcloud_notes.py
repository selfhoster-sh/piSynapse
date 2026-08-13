"""piSynapse Nextcloud Notes
REST API integration for Nextcloud Notes (v1).
"""

import asyncio
import json
import logging
from typing import Any

from utils import retry

logger = logging.getLogger("piSynapse")

# Singleton pattern — reuse connection
_notes_client: "NextcloudNotesClient | None" = None


class NextcloudNotesClient:
    """Nextcloud Notes REST API client."""

    def __init__(self):
        from config import NEXTCLOUD_PASSWORD, NEXTCLOUD_TIMEOUT, NEXTCLOUD_URL, NEXTCLOUD_USER
        self._base = NEXTCLOUD_URL.rstrip("/")
        self._user = NEXTCLOUD_USER
        self._password = NEXTCLOUD_PASSWORD
        self._timeout = NEXTCLOUD_TIMEOUT
        self._list_cache: list[dict] | None = None
        self._list_cache_ts: float = 0

    def _request(self, method: str, path: str, data: dict | None = None) -> Any:
        """Make an authenticated request to Nextcloud Notes API."""
        import base64
        import urllib.error
        import urllib.request

        url = f"{self._base}/index.php/apps/notes/api/v1/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Basic {base64.b64encode(f'{self._user}:{self._password}'.encode()).decode()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise Exception(f"Nextcloud API error {e.code}: {e.reason}")

    @retry(attempts=2, delay=1.0)
    def list_notes(self) -> list[dict]:
        """Fetch all notes from Nextcloud. Results are cached for 30s."""
        import time
        now = time.time()
        if self._list_cache and now - self._list_cache_ts < 30:
            return self._list_cache
        result = self._request("GET", "notes")
        self._list_cache = result or []
        self._list_cache_ts = now
        return self._list_cache

    @retry(attempts=2, delay=1.0)
    def get_note(self, note_id: int) -> dict | None:
        """Fetch a single note by ID."""
        return self._request("GET", f"notes/{note_id}")

    @retry(attempts=2, delay=1.0)
    def create_note(self, title: str, content: str = "", category: str = "", tags: list[str] | None = None) -> dict:
        """Create a new note."""
        payload = {"title": title, "content": content}
        if category:
            payload["category"] = category
        if tags:
            payload["tags"] = tags
        return self._request("POST", "notes", payload)

    @retry(attempts=2, delay=1.0)
    def update_note(self, note_id: int, title: str | None = None, content: str | None = None,
                    category: str | None = None, tags: list[str] | None = None) -> dict | None:
        """Update an existing note. Only fields passed are updated."""
        # Get current note to merge
        current = self.get_note(note_id)
        if not current:
            return None
        payload: dict[str, Any] = {"etag": current.get("etag", "")}
        if title is not None:
            payload["title"] = title
        if content is not None:
            payload["content"] = content
        if category is not None:
            payload["category"] = category
        if tags is not None:
            payload["tags"] = tags
        return self._request("PUT", f"notes/{note_id}", payload)

    @retry(attempts=2, delay=1.0)
    def delete_note(self, note_id: int) -> bool:
        """Delete a note by ID."""
        try:
            self._request("DELETE", f"notes/{note_id}")
            return True
        except Exception:
            return False


def _get_client() -> NextcloudNotesClient | None:
    """Return singleton client, create if needed."""
    global _notes_client
    from config import NEXTCLOUD_PASSWORD, NEXTCLOUD_URL
    if not NEXTCLOUD_URL or not NEXTCLOUD_PASSWORD:
        return None
    if _notes_client is None:
        _notes_client = NextcloudNotesClient()
    return _notes_client


# -- Async wrappers for FastAPI/tool dispatcher compatibility --

async def list_notes() -> str:
    """List all notes."""
    client = _get_client()
    if not client:
        return "ERROR: Nextcloud credentials missing."
    try:
        notes = await asyncio.to_thread(client.list_notes)
        if not notes:
            return "No notes found."
        lines = [" Notes:\n"]
        for i, n in enumerate(notes, 1):
            nid = n.get("id", "?")
            title = n.get("title", "Untitled")
            category = n.get("category", "")
            tags = n.get("tags", [])
            starred = n.get("starred", False)
            content = n.get("content", "")
            star = " * " if starred else "   "
            lines.append(f"{star}{i}. {title}")
            meta = []
            if category:
                meta.append(f"Category: {category}")
            if tags:
                meta.append(f"Tags: {', '.join(tags)}")
            meta.append(f"ID: {nid}")
            lines.append(f"      {' | '.join(meta)}")
            if content:
                lines.append(f"      Preview: {content[:80].replace(chr(10), ' ')}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Nextcloud Notes Error: {e}")
        return "ERROR: Failed to list notes."


async def get_note(note_id: int) -> str:
    """Get a single note."""
    client = _get_client()
    if not client:
        return "ERROR: Nextcloud credentials missing."
    try:
        note = await asyncio.to_thread(client.get_note, note_id)
        if not note:
            return f"Note {note_id} not found."
        title = note.get("title", "Untitled")
        content = note.get("content", "")
        category = note.get("category", "")
        tags = note.get("tags", [])
        modified = note.get("modified", "")
        starred = note.get("starred", False)
        lines = []
        star = " * " if starred else "   "
        lines.append(f"{star}{title}")
        meta = []
        if category:
            meta.append(f"Category: {category}")
        if tags:
            meta.append(f"Tags: {', '.join(tags)}")
        meta.append(f"ID: {note_id}")
        if modified:
            meta.append(f"Modified: {modified}")
        lines.append(f"      {' | '.join(meta)}")
        lines.append("")
        lines.append(content)
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Nextcloud Notes Error: {e}")
        return "ERROR: Failed to get note."


async def create_note(title: str, content: str = "", category: str = "") -> str:
    """Create a new note."""
    client = _get_client()
    if not client:
        return "ERROR: Nextcloud credentials missing."
    try:
        result = await asyncio.to_thread(client.create_note, title, content, category)
        nid = result.get("id", "?")
        return f"OK Note '{title}' created (ID: {nid})."
    except Exception as e:
        logger.error(f"Nextcloud Notes Error: {e}")
        return "ERROR: Failed to create note."


async def update_note(note_id: int, title: str | None = None, content: str | None = None) -> str:
    """Update an existing note."""
    client = _get_client()
    if not client:
        return "ERROR: Nextcloud credentials missing."
    try:
        result = await asyncio.to_thread(client.update_note, note_id, title, content)
        if not result:
            return f"Note {note_id} not found."
        return f"OK Note {note_id} updated."
    except Exception as e:
        logger.error(f"Nextcloud Notes Error: {e}")
        return "ERROR: Failed to update note."


async def delete_note(note_id: int) -> str:
    """Delete a note."""
    client = _get_client()
    if not client:
        return "ERROR: Nextcloud credentials missing."
    try:
        ok = await asyncio.to_thread(client.delete_note, note_id)
        return f"OK Note {note_id} deleted." if ok else f"Note {note_id} not found."
    except Exception as e:
        logger.error(f"Nextcloud Notes Error: {e}")
        return "ERROR: Failed to delete note."


async def search_notes(query: str) -> str:
    """Search notes by title or content."""
    client = _get_client()
    if not client:
        return "ERROR: Nextcloud credentials missing."
    try:
        notes = await asyncio.to_thread(client.list_notes)
        q = query.lower()
        matches = [
            n for n in notes
            if q in (n.get("title", "") + " " + n.get("content", "")).lower()
        ]
        if not matches:
            return f"'{query}' not found in notes."
        lines = [f" Search Results for '{query}':\n"]
        for i, n in enumerate(matches[:10], 1):
            nid = n.get("id", "?")
            title = n.get("title", "Untitled")
            preview = n.get("content", "")[:100].replace("\n", " ")
            lines.append(f"   {i}. {title}")
            lines.append(f"      ID: {nid}")
            if preview:
                lines.append(f"      Preview: {preview}...")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Nextcloud Notes Error: {e}")
        return "ERROR: Failed to search notes."
