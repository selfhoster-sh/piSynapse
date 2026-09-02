"""piSynapse Nextcloud Notes
REST API integration for Nextcloud Notes (v1).
"""

import asyncio
import json
import logging
import threading
from typing import Any

from utils import retry

logger = logging.getLogger("piSynapse")

# Singleton pattern — reuse connection
_notes_client: "NextcloudNotesClient | None" = None
# Notes run in worker threads (asyncio.to_thread); the lock makes lazy
# singleton creation single-flight across concurrent requests.
_notes_lock = threading.Lock()


class NotFoundError(Exception):
    """Raised when Nextcloud returns 404 (resource does not exist)."""


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
        """Make an authenticated request to Nextcloud Notes API.

        Raises NotFoundError on 404 (so callers can tell "does not exist"
        from a network/server failure), and the raw urllib error otherwise.
        """
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
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise NotFoundError(f"Not found: {path}") from e
            raise Exception(f"Nextcloud API error {e.code}: {e.reason}")

    @retry(attempts=2, delay=1.0)
    def list_notes(self) -> list[dict]:
        """Fetch all notes from Nextcloud (paginated, cached 30s)."""
        import time
        now = time.time()
        if self._list_cache and now - self._list_cache_ts < 30:
            return self._list_cache
        notes: list[dict] = []
        page = 1
        per_page = 100
        while page <= 200:
            result = self._request("GET", f"notes?page={page}&itemsPerPage={per_page}")
            if isinstance(result, dict):
                data = result.get("data", [])
                batch = data if isinstance(data, list) else (data.get("notes", []) if isinstance(data, dict) else [])
            else:
                batch = result or []
            if not batch:
                break
            notes.extend(batch)
            if len(batch) < per_page:
                break
            seen_ids = {n.get("id") for n in notes[:-len(batch)]}
            new_ids = {n.get("id") for n in batch}
            if new_ids.issubset(seen_ids):
                break  # server ignores pagination params — stop to avoid infinite loop
            page += 1
        self._list_cache = notes
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
        """Update an existing note. Only fields passed are updated.

        The GET (merge base) and the PUT share a single retry scope — fetching
        via the decorated ``get_note`` would nest two retry layers (up to 4
        attempts and doubled latency), so the merge is read here directly.
        """
        try:
            current = self._request("GET", f"notes/{note_id}")
        except NotFoundError:
            return None
        if not current or current.get("etag") is None:
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
        """Delete a note by ID. Returns False only when the note does not exist.

        Network/server failures raise instead of being reported as "not found".
        """
        try:
            self._request("DELETE", f"notes/{note_id}")
        except NotFoundError:
            return False
        return True

    @retry(attempts=2, delay=1.0)
    def search_notes_server(self, query: str, limit: int = 10) -> list[dict]:
        """Search notes using Nextcloud server-side search API (if supported).

        Falls back to client-side filtering if the API doesn't support search param.
        Returns up to `limit` matches.
        """
        # Try server-side search first (Nextcloud Notes API v1.0.2+ supports ?search=)
        try:
            encoded_query = query.replace(" ", "+")
            result = self._request("GET", f"notes?search={encoded_query}&page=1&itemsPerPage={limit}")
            if isinstance(result, dict):
                data = result.get("data", [])
                notes = data if isinstance(data, list) else (data.get("notes", []) if isinstance(data, dict) else [])
            else:
                notes = result or []
            if notes:
                return notes[:limit]
        except Exception:
            pass  # Fall back to client-side

        # Fallback: client-side filtering
        all_notes = self.list_notes()
        q = query.lower()
        matches = [
            n for n in all_notes
            if q in (n.get("title", "") + " " + n.get("content", "")).lower()
        ]
        return matches[:limit]


def _get_client() -> NextcloudNotesClient | None:
    """Return singleton client, create if needed."""
    global _notes_client
    from config import NEXTCLOUD_PASSWORD, NEXTCLOUD_URL
    if not NEXTCLOUD_URL or not NEXTCLOUD_PASSWORD:
        return None
    if _notes_client is None:
        with _notes_lock:
            if _notes_client is None:
                _notes_client = NextcloudNotesClient()
    return _notes_client


def _invalidate_list_cache() -> None:
    """Drop the 30s listing cache after a successful write (create/update/delete),
    so the next listing reflects the change immediately.
    """
    if _notes_client is not None:
        _notes_client._list_cache = None
        _notes_client._list_cache_ts = 0.0


# -- Async wrappers for FastAPI/tool dispatcher compatibility --

async def list_notes() -> tuple[str, list[dict]]:
    """List all notes.

    Returns ``(display_text, items)`` where ``items`` are the raw note dicts
    in the exact order they are numbered in ``display_text`` (the model only
    sees list positions; real IDs never appear in tool output).
    """
    client = _get_client()
    if not client:
        return "ERROR: Nextcloud credentials missing.", []
    try:
        notes = await asyncio.to_thread(client.list_notes)
        if not notes:
            return "No notes found.", []
        lines = [" Notes:\n"]
        for i, n in enumerate(notes, 1):
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
            if meta:
                lines.append(f"      {' | '.join(meta)}")
            if content:
                lines.append(f"      Preview: {content[:80].replace(chr(10), ' ')}")
            lines.append("")
        return "\n".join(lines), notes
    except Exception as e:
        logger.error(f"Nextcloud Notes Error: {e}")
        return "ERROR: Failed to list notes.", []


async def get_note(note_id: int) -> str:
    """Get a single note."""
    client = _get_client()
    if not client:
        return "ERROR: Nextcloud credentials missing."
    try:
        note = await asyncio.to_thread(client.get_note, note_id)
        if not note:
            return "ERROR: Note not found."
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
        if modified:
            meta.append(f"Modified: {modified}")
        if meta:
            lines.append(f"      {' | '.join(meta)}")
        lines.append("")
        lines.append(content)
        return "\n".join(lines)
    except NotFoundError:
        return "Note not found."
    except Exception as e:
        logger.error(f"Nextcloud Notes Error: {e}")
        return "ERROR: Failed to get note."


async def create_note(title: str, content: str = "", category: str = "") -> tuple[str, int | None]:
    """Create a new note.

    Returns ``(result_text, note_id)`` — the id is forwarded by the dispatcher
    so the verification hook can re-read the note and confirm it persisted.
    """
    client = _get_client()
    if not client:
        return "ERROR: Nextcloud credentials missing.", None
    try:
        resp = await asyncio.to_thread(client.create_note, title, content, category)
        _invalidate_list_cache()
        note_id = resp.get("id") if isinstance(resp, dict) else None
        return f"OK Note '{title}' created.", note_id
    except Exception as e:
        logger.error(f"Nextcloud Notes Error: {e}")
        return "ERROR: Failed to create note.", None


async def update_note(note_id: int, title: str | None = None, content: str | None = None,
                      category: str | None = None, tags: list[str] | None = None) -> str:
    """Update an existing note. Only fields passed are forwarded to Nextcloud."""
    client = _get_client()
    if not client:
        return "ERROR: Nextcloud credentials missing."
    try:
        result = await asyncio.to_thread(client.update_note, note_id, title, content, category, tags)
        if not result:
            return "ERROR: Note not found."
        _invalidate_list_cache()
        return "OK Note updated."
    except NotFoundError:
        return "Note not found."
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
        if ok:
            _invalidate_list_cache()
        return "OK Note deleted." if ok else "Note not found."
    except NotFoundError:
        return "Note not found."
    except Exception as e:
        logger.error(f"Nextcloud Notes Error: {e}")
        return "ERROR: Failed to delete note."


async def search_notes(query: str, limit: int = 10) -> tuple[str, list[dict]]:
    """Search notes by title or content.

    Returns ``(display_text, items)`` — same contract as ``list_notes``.
    Uses server-side search API when available (Nextcloud Notes v1.0.2+).
    """
    client = _get_client()
    if not client:
        return "ERROR: Nextcloud credentials missing.", []
    try:
        matches = await asyncio.to_thread(client.search_notes_server, query, limit)
        if not matches:
            return f"'{query}' not found in notes.", []
        lines = [f" Search Results for '{query}':\n"]
        for i, n in enumerate(matches, 1):
            title = n.get("title", "Untitled")
            preview = n.get("content", "")[:100].replace("\n", " ")
            lines.append(f"   {i}. {title}")
            if preview:
                lines.append(f"      Preview: {preview}...")
            lines.append("")
        return "\n".join(lines), matches
    except Exception as e:
        logger.error(f"Nextcloud Notes Error: {e}")
        return "ERROR: Failed to search notes.", []
