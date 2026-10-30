"""Relack's durable storage: one SQLite file beside Reflex's own database.

Rooms, people, messages (with threads, reactions, files and mentions), read
positions, settings and login sessions live here. Reflex's shared states only
mirror what open tabs show, so a restart, or Reflex purging old `.states`
files, loses nothing.

The App Store keeps an app's `reflex.db` on the app's own volume (a symlink,
since SQLite must not be shared with the host), so `relack.db` goes next to
wherever that `reflex.db` really is. Run locally, it lives in `.relack/`.
RELACK_DB_PATH overrides the location.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

import reflex as rx

from relack.formatting import EVERYONE, human_size, plain_text, render_markdown, snippet
from relack.models import (
    Attachment,
    ChatMessage,
    FileHit,
    AuditEntry,
    Reaction,
    RoomInfo,
    SavedItem,
    ScheduledItem,
    SearchHit,
    UserProfile,
    WebhookInfo,
)

SESSION_SECONDS = 86400 * 30
# Files uploaded but never sent are removed after this long...
PENDING_FILE_SECONDS = 86400
# ...by a cleanup that runs this often.
CLEANUP_EVERY_SECONDS = 3600
PREVIEW_KEYS = ("url", "title", "description", "image", "site")
# Kinds a browser would run or render from our own origin: stored under a
# harmless name so opening the link downloads them instead.
_ACTIVE_EXTENSIONS = {".html", ".htm", ".xhtml", ".svg", ".svgz", ".xml", ".js", ".mjs"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".bmp"}
# Where uploads live under the upload dir: relack/<32 hex>/<name>.
_FILE_PATH_RE = re.compile(r"^relack/[0-9a-f]{32}/[^/\\]+$")

_local = threading.local()
_schema_lock = threading.Lock()
_schema_ready: set[str] = set()
_fts_enabled: dict[str, bool] = {}
_last_cleanup: dict[str, float] = {}
# Small tables, cached per database file (single process).
_cache: dict[str, dict[str, Any]] = {}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    name TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles (
    username TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    profile TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(username);
CREATE TABLE IF NOT EXISTS messages (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    room TEXT NOT NULL,
    parent_id TEXT NOT NULL DEFAULT '',
    sender TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    plain TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    edited_at REAL NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    is_system INTEGER NOT NULL DEFAULT 0,
    mentions TEXT NOT NULL DEFAULT '[]',
    preview TEXT NOT NULL DEFAULT '{}',
    legacy_time TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS messages_room ON messages(room, parent_id, seq);
CREATE INDEX IF NOT EXISTS messages_parent ON messages(parent_id, seq);
CREATE INDEX IF NOT EXISTS messages_sender ON messages(sender, parent_id);
CREATE INDEX IF NOT EXISTS messages_room_seq ON messages(room, seq);
CREATE TABLE IF NOT EXISTS reactions (
    message_id TEXT NOT NULL,
    emoji TEXT NOT NULL,
    username TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (message_id, emoji, username)
);
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL DEFAULT '',
    room TEXT NOT NULL DEFAULT '',
    uploader TEXT NOT NULL,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    mime TEXT NOT NULL DEFAULT '',
    size INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS files_message ON files(message_id);
CREATE TABLE IF NOT EXISTS mentions (
    seq INTEGER NOT NULL,
    room TEXT NOT NULL,
    username TEXT NOT NULL,
    PRIMARY KEY (seq, username)
);
CREATE INDEX IF NOT EXISTS mentions_user ON mentions(username, seq);
CREATE TABLE IF NOT EXISTS room_prefs (
    username TEXT NOT NULL,
    room TEXT NOT NULL,
    left_room INTEGER NOT NULL DEFAULT 0,
    muted INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (username, room)
);
CREATE TABLE IF NOT EXISTS pins (
    room TEXT NOT NULL,
    message_id TEXT NOT NULL,
    pinned_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (room, message_id)
);
CREATE TABLE IF NOT EXISTS saved (
    username TEXT NOT NULL,
    message_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    remind_at REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (username, message_id)
);
CREATE TABLE IF NOT EXISTS scheduled (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    room TEXT NOT NULL,
    text TEXT NOT NULL,
    due_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS scheduled_due ON scheduled(due_at);
CREATE TABLE IF NOT EXISTS webhooks (
    token TEXT PRIMARY KEY,
    room TEXT NOT NULL,
    name TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at REAL NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS reads (
    username TEXT NOT NULL,
    room TEXT NOT NULL,
    seq INTEGER NOT NULL,
    PRIMARY KEY (username, room)
);
"""

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    plain, content='messages', content_rowid='seq', tokenize='trigram'
);
CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, plain) VALUES (new.seq, new.plain);
END;
CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, plain) VALUES ('delete', old.seq, old.plain);
END;
CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE OF plain ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, plain) VALUES ('delete', old.seq, old.plain);
    INSERT INTO messages_fts(rowid, plain) VALUES (new.seq, new.plain);
END;
"""


def db_path() -> Path:
    if os.environ.get("RELACK_DB_PATH"):
        return Path(os.environ["RELACK_DB_PATH"])
    reflex_db = Path("reflex.db")
    if reflex_db.is_symlink():
        # The App Store links reflex.db to the app's own volume: stay beside it.
        return reflex_db.resolve().parent / "relack.db"
    # A hidden folder: the dev server's hot reload never watches it (SQLite's
    # -wal/-shm files in the project root would restart the backend on every write).
    return Path.cwd() / ".relack" / "relack.db"


def _conn() -> sqlite3.Connection:
    path = str(db_path())
    conn = getattr(_local, "conn", None)
    if conn is None or getattr(_local, "path", None) != path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # Autocommit; writes that must go together use _tx().
        conn = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=10000")
        _local.conn, _local.path = conn, path
        _ensure_schema(conn, path)
    now = time.time()
    if now - _last_cleanup.get(path, 0.0) > CLEANUP_EVERY_SECONDS and not conn.in_transaction:
        _last_cleanup[path] = now
        _cleanup(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection, path: str):
    with _schema_lock:
        if path in _schema_ready:
            return
        conn.executescript(_SCHEMA)
        try:
            conn.executescript(_FTS_SCHEMA)
            _fts_enabled[path] = True
            if not conn.execute("SELECT 1 FROM settings WHERE key = 'fts_built'").fetchone():
                # Index messages stored before the search index existed.
                conn.execute("INSERT INTO messages_fts(messages_fts) VALUES ('rebuild')")
                conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('fts_built', 'true')")
        except sqlite3.OperationalError:
            # SQLite without FTS5 / trigram: search falls back to LIKE.
            _fts_enabled[path] = False
        _schema_ready.add(path)
        _cache.pop(path, None)


@contextmanager
def _tx():
    conn = _conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def _cached() -> dict[str, Any]:
    _conn()
    return _cache.setdefault(str(db_path()), {})


def _ids_param(ids: Iterable[str]) -> str:
    return json.dumps(list(ids))


def _cleanup(conn: sqlite3.Connection):
    """Drop expired sessions and files that were uploaded but never sent."""
    now = time.time()
    conn.execute("DELETE FROM sessions WHERE created_at < ?", (now - SESSION_SECONDS,))
    stale = conn.execute(
        "SELECT id, path FROM files WHERE message_id = '' AND created_at < ?",
        (now - PENDING_FILE_SECONDS,),
    ).fetchall()
    for row in stale:
        _remove_file(row["path"])
    conn.execute(
        "DELETE FROM files WHERE message_id = '' AND created_at < ?", (now - PENDING_FILE_SECONDS,)
    )


# --- Settings ---------------------------------------------------------------


def get_setting(key: str, default: Any = None) -> Any:
    settings = _cached().get("settings")
    if settings is None:
        settings = {
            row["key"]: json.loads(row["value"])
            for row in _conn().execute("SELECT key, value FROM settings")
        }
        _cached()["settings"] = settings
    return settings.get(key, default)


def set_setting(key: str, value: Any):
    _conn().execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )
    settings = _cached().get("settings")
    if settings is not None:
        settings[key] = value


# --- Rooms and people ---------------------------------------------------------


def load_rooms() -> dict[str, RoomInfo]:
    rooms = _cached().get("rooms")
    if rooms is None:
        rooms = {}
        for row in _conn().execute("SELECT data FROM rooms ORDER BY created_at, rowid"):
            room = RoomInfo(**json.loads(row["data"]))
            rooms[room.name] = room
        _cached()["rooms"] = rooms
    return dict(rooms)


def save_room(room: RoomInfo):
    _conn().execute(
        "INSERT INTO rooms(name, data, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT(name) DO UPDATE SET data = excluded.data",
        (room.name, room.model_dump_json(), time.time()),
    )
    rooms = load_rooms()
    rooms[room.name] = room
    _cached()["rooms"] = rooms


def room_created_at(name: str) -> float:
    """When the room was created: tells a re-created room from a deleted one of the same name."""
    row = _conn().execute("SELECT created_at FROM rooms WHERE name = ?", (name,)).fetchone()
    return row["created_at"] if row else 0.0


def delete_room(name: str):
    """Delete a room with everything said and shared in it."""
    with _tx() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM messages WHERE room = ?", (name,))]
        files = conn.execute(
            "SELECT path FROM files WHERE message_id IN (SELECT value FROM json_each(?))",
            (_ids_param(ids),),
        ).fetchall()
        conn.execute("DELETE FROM reactions WHERE message_id IN (SELECT value FROM json_each(?))", (_ids_param(ids),))
        conn.execute("DELETE FROM files WHERE message_id IN (SELECT value FROM json_each(?))", (_ids_param(ids),))
        conn.execute("DELETE FROM mentions WHERE room = ?", (name,))
        conn.execute("DELETE FROM reads WHERE room = ?", (name,))
        conn.execute("DELETE FROM room_prefs WHERE room = ?", (name,))
        conn.execute("DELETE FROM pins WHERE room = ?", (name,))
        conn.execute("DELETE FROM saved WHERE message_id IN (SELECT value FROM json_each(?))", (_ids_param(ids),))
        conn.execute("DELETE FROM scheduled WHERE room = ?", (name,))
        conn.execute("DELETE FROM webhooks WHERE room = ?", (name,))
        conn.execute("DELETE FROM messages WHERE room = ?", (name,))
        conn.execute("DELETE FROM rooms WHERE name = ?", (name,))
    for row in files:
        _remove_file(row["path"])
    rooms = load_rooms()
    rooms.pop(name, None)
    _cached()["rooms"] = rooms


def load_profiles() -> dict[str, UserProfile]:
    profiles = _cached().get("profiles")
    if profiles is None:
        profiles = {}
        for row in _conn().execute("SELECT data FROM profiles ORDER BY updated_at"):
            profile = UserProfile(**json.loads(row["data"]))
            profiles[profile.username] = profile
        _cached()["profiles"] = profiles
    return dict(profiles)


def save_profile(profile: UserProfile):
    _conn().execute(
        "INSERT INTO profiles(username, data, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(username) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
        (profile.username, profile.model_dump_json(), time.time()),
    )
    profiles = load_profiles()
    profiles[profile.username] = profile
    _cached()["profiles"] = profiles


def active_status(profile: UserProfile) -> tuple[str, str]:
    """(emoji, text) of a status that hasn't run out."""
    if profile.status_until and profile.status_until < time.time():
        return "", ""
    return profile.status_emoji, profile.status_text


def display_names() -> dict[str, str]:
    return {u: (p.nickname or u) for u, p in load_profiles().items()}


def avatar_seeds() -> dict[str, str]:
    return {u: (p.avatar_seed or u) for u, p in load_profiles().items()}


def room_title(room: RoomInfo, viewer: str, names: dict[str, str]) -> str:
    """Room name, or for a direct message the other people's names."""
    if not room.is_direct:
        return room.title or room.name
    others = [u for u in [room.created_by, *room.allowed_members] if u != viewer] or [viewer]
    return ", ".join(names.get(u) or u for u in others)


def room_people(room: RoomInfo) -> dict[str, str]:
    """Username -> display name of everyone who can see the room."""
    names = display_names()
    if not room.is_private:
        return names
    return {u: names.get(u, u) for u in [room.created_by, *room.allowed_members] if u}


# --- Sessions -----------------------------------------------------------------


def save_session(session_id: str, profile: UserProfile):
    _conn().execute(
        "INSERT OR REPLACE INTO sessions(id, username, profile, created_at) VALUES (?, ?, ?, ?)",
        (session_id, profile.username, profile.model_dump_json(), time.time()),
    )


def load_session(session_id: str) -> UserProfile | None:
    row = _conn().execute(
        "SELECT profile, created_at FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None or row["created_at"] < time.time() - SESSION_SECONDS:
        return None
    return UserProfile(**json.loads(row["profile"]))


def delete_session(session_id: str):
    _conn().execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def update_session_profiles(profile: UserProfile):
    """After a profile edit: every login of that person shows the new nickname and bio."""
    conn = _conn()
    for row in conn.execute(
        "SELECT id, profile FROM sessions WHERE username = ?", (profile.username,)
    ).fetchall():
        old = UserProfile(**json.loads(row["profile"]))
        new = old.model_copy(update={"nickname": profile.nickname, "bio": profile.bio})
        conn.execute("UPDATE sessions SET profile = ? WHERE id = ?", (new.model_dump_json(), row["id"]))


# --- Files --------------------------------------------------------------------


def upload_root() -> Path:
    root = rx.get_upload_dir() / "relack"
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_file_name(name: str) -> str:
    name = os.path.basename(name.replace("\\", "/")).strip().replace("\x00", "")
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"/\\|?*')
    # Kept in the file's URL: "#" and "%" would cut or garble it.
    name = name.replace("#", "_").replace("%", "_").lstrip(". ").rstrip()
    return (name or "file")[-150:]


def new_file_path(name: str) -> tuple[str, Path]:
    """A fresh, unguessable place for an upload: (path under the upload dir, file)."""
    stored = safe_file_name(name)
    if Path(stored).suffix.lower() in _ACTIVE_EXTENSIONS:
        stored += ".download"
    folder = uuid.uuid4().hex
    rel = f"relack/{folder}/{stored}"
    target = upload_root() / folder / stored
    target.parent.mkdir(parents=True, exist_ok=True)
    return rel, target


def valid_file_path(rel_path: str) -> bool:
    """Whether a stored path is one of our uploads (imported data is not trusted)."""
    if not _FILE_PATH_RE.match(rel_path or "") or rel_path.rsplit("/", 1)[1] in (".", ".."):
        return False
    target = (rx.get_upload_dir() / rel_path).resolve()
    return target.parent.parent == upload_root().resolve()


def _remove_file(rel_path: str):
    if not valid_file_path(rel_path):
        return
    target = rx.get_upload_dir() / rel_path
    try:
        target.unlink(missing_ok=True)
        target.parent.rmdir()
    except OSError:
        pass


def _attachment(row: sqlite3.Row) -> Attachment:
    name = row["name"]
    return Attachment(
        id=row["id"],
        name=name,
        path=row["path"],
        mime=row["mime"],
        size=row["size"],
        size_label=human_size(row["size"]),
        is_image=Path(name).suffix.lower() in _IMAGE_EXTENSIONS and not row["path"].endswith(".download"),
    )


def add_file(uploader: str, name: str, rel_path: str, mime: str, size: int) -> Attachment:
    file_id = uuid.uuid4().hex
    conn = _conn()
    conn.execute(
        "INSERT INTO files(id, uploader, name, path, mime, size, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (file_id, uploader, safe_file_name(name), rel_path, mime, size, time.time()),
    )
    return _attachment(conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone())


def discard_pending_file(file_id: str, uploader: str):
    conn = _conn()
    row = conn.execute(
        "SELECT path FROM files WHERE id = ? AND uploader = ? AND message_id = ''", (file_id, uploader)
    ).fetchone()
    if row:
        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
        _remove_file(row["path"])


# --- Messages -----------------------------------------------------------------


def _write_mentions(conn: sqlite3.Connection, seq: int, room: str, mentions: list[str]):
    conn.execute("DELETE FROM mentions WHERE seq = ?", (seq,))
    for username in dict.fromkeys(mentions):
        conn.execute("INSERT INTO mentions(seq, room, username) VALUES (?, ?, ?)", (seq, room, username))


def _insert_message(
    conn: sqlite3.Connection,
    *,
    room: str,
    sender: str,
    display_name: str,
    content: str,
    plain: str,
    mentions: list[str] | None = None,
    preview: dict[str, str] | None = None,
    parent_id: str = "",
    is_system: bool = False,
    created_at: float | None = None,
    msg_id: str | None = None,
    legacy_time: str = "",
    edited_at: float = 0.0,
    deleted: bool = False,
) -> tuple[str, int]:
    msg_id = msg_id or str(uuid.uuid4())
    mentions = mentions or []
    cur = conn.execute(
        "INSERT INTO messages(id, room, parent_id, sender, display_name, content, plain, created_at,"
        " edited_at, deleted, is_system, mentions, preview, legacy_time)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            msg_id,
            room,
            parent_id,
            sender,
            display_name,
            content,
            plain,
            time.time() if created_at is None else created_at,
            edited_at,
            int(deleted),
            int(is_system),
            json.dumps(mentions),
            json.dumps(preview or {}),
            legacy_time,
        ),
    )
    seq = cur.lastrowid
    _write_mentions(conn, seq, room, mentions)
    return msg_id, seq


def insert_message(*, file_ids: list[str] | None = None, **fields) -> tuple[str, int]:
    """Store a message (and attach the sender's pending files); returns (id, seq)."""
    with _tx() as conn:
        msg_id, seq = _insert_message(conn, **fields)
        if file_ids:
            conn.execute(
                "UPDATE files SET message_id = ?, room = ? WHERE message_id = '' AND uploader = ?"
                " AND id IN (SELECT value FROM json_each(?))",
                (msg_id, fields["room"], fields["sender"], _ids_param(file_ids)),
            )
    return msg_id, seq


def message_row(msg_id: str) -> sqlite3.Row | None:
    return _conn().execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()


def update_message_text(msg_id: str, content: str, plain: str, mentions: list[str], preview: dict | None):
    with _tx() as conn:
        row = conn.execute("SELECT seq, room FROM messages WHERE id = ?", (msg_id,)).fetchone()
        if row is None:
            return
        conn.execute(
            "UPDATE messages SET content = ?, plain = ?, mentions = ?, preview = ?, edited_at = ? WHERE id = ?",
            (content, plain, json.dumps(mentions), json.dumps(preview or {}), time.time(), msg_id),
        )
        _write_mentions(conn, row["seq"], row["room"], mentions)


def _purge(conn: sqlite3.Connection, msg_id: str) -> list[str]:
    """Delete a message row with its reactions, files and mentions; returns file paths."""
    paths = [r["path"] for r in conn.execute("SELECT path FROM files WHERE message_id = ?", (msg_id,))]
    conn.execute("DELETE FROM reactions WHERE message_id = ?", (msg_id,))
    conn.execute("DELETE FROM files WHERE message_id = ?", (msg_id,))
    conn.execute("DELETE FROM pins WHERE message_id = ?", (msg_id,))
    conn.execute("DELETE FROM saved WHERE message_id = ?", (msg_id,))
    conn.execute("DELETE FROM mentions WHERE seq = (SELECT seq FROM messages WHERE id = ?)", (msg_id,))
    conn.execute("DELETE FROM messages WHERE id = ?", (msg_id,))
    return paths


def delete_message(msg_id: str) -> list[str]:
    """Delete a message; returns the ids that are gone for good.

    A thread root that still has replies stays as "This message was deleted.";
    it goes once its last reply does.
    """
    removed: list[str] = []
    paths: list[str] = []
    with _tx() as conn:
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
        if row is None:
            return []
        has_replies = conn.execute(
            "SELECT 1 FROM messages WHERE parent_id = ? AND deleted = 0 LIMIT 1", (msg_id,)
        ).fetchone()
        if has_replies:
            paths += [r["path"] for r in conn.execute("SELECT path FROM files WHERE message_id = ?", (msg_id,))]
            conn.execute("DELETE FROM reactions WHERE message_id = ?", (msg_id,))
            conn.execute("DELETE FROM files WHERE message_id = ?", (msg_id,))
            conn.execute("DELETE FROM mentions WHERE seq = ?", (row["seq"],))
            conn.execute("DELETE FROM pins WHERE message_id = ?", (msg_id,))
            conn.execute("DELETE FROM saved WHERE message_id = ?", (msg_id,))
            conn.execute(
                "UPDATE messages SET deleted = 1, content = '', plain = '', mentions = '[]', preview = '{}'"
                " WHERE id = ?",
                (msg_id,),
            )
        else:
            paths += _purge(conn, msg_id)
            removed.append(msg_id)
            parent = row["parent_id"]
            if parent:
                root = conn.execute("SELECT deleted FROM messages WHERE id = ?", (parent,)).fetchone()
                left = conn.execute(
                    "SELECT 1 FROM messages WHERE parent_id = ? AND deleted = 0 LIMIT 1", (parent,)
                ).fetchone()
                if root is not None and root["deleted"] and not left:
                    paths += _purge(conn, parent)
                    removed.append(parent)
    for path in paths:
        _remove_file(path)
    return removed


def toggle_reaction(msg_id: str, emoji: str, username: str) -> bool:
    """Add the reaction, or take it back if it was there; True when added."""
    with _tx() as conn:
        if conn.execute(
            "DELETE FROM reactions WHERE message_id = ? AND emoji = ? AND username = ?",
            (msg_id, emoji, username),
        ).rowcount:
            return False
        conn.execute(
            "INSERT INTO reactions(message_id, emoji, username, created_at) VALUES (?, ?, ?, ?)",
            (msg_id, emoji, username, time.time()),
        )
    return True


def messages_after(room: str, seq: int) -> list[ChatMessage]:
    """Room messages stored after `seq` (bots and scheduled posts don't come through a tab)."""
    rows = _conn().execute(
        "SELECT * FROM messages WHERE room = ? AND parent_id = '' AND deleted = 0 AND seq > ? ORDER BY seq",
        (room, seq),
    ).fetchall()
    return build_messages(rows)


def max_root_seq(room: str) -> int:
    row = _conn().execute(
        "SELECT MAX(seq) AS s FROM messages WHERE room = ? AND parent_id = ''", (room,)
    ).fetchone()
    return row["s"] or 0


def max_seq(room: str | None = None) -> int:
    if room is None:
        row = _conn().execute("SELECT MAX(seq) AS s FROM messages").fetchone()
    else:
        row = _conn().execute("SELECT MAX(seq) AS s FROM messages WHERE room = ?", (room,)).fetchone()
    return row["s"] or 0


def build_messages(rows: list[sqlite3.Row]) -> list[ChatMessage]:
    """ChatMessages for message rows, with reactions, files and thread summaries."""
    if not rows:
        return []
    conn = _conn()
    names = display_names()
    seeds = avatar_seeds()
    ids = [r["id"] for r in rows]
    param = _ids_param(ids)

    reactions: dict[str, dict[str, list[str]]] = {}
    for r in conn.execute(
        "SELECT message_id, emoji, username FROM reactions WHERE message_id IN (SELECT value FROM json_each(?))"
        " ORDER BY created_at",
        (param,),
    ):
        reactions.setdefault(r["message_id"], {}).setdefault(r["emoji"], []).append(r["username"])

    files: dict[str, list[Attachment]] = {}
    for r in conn.execute(
        "SELECT * FROM files WHERE message_id IN (SELECT value FROM json_each(?)) ORDER BY created_at",
        (param,),
    ):
        files.setdefault(r["message_id"], []).append(_attachment(r))

    pinned_ids = {
        r["message_id"]
        for r in conn.execute("SELECT message_id FROM pins WHERE message_id IN (SELECT value FROM json_each(?))", (param,))
    }
    statuses = {u: active_status(p)[0] for u, p in load_profiles().items()}
    roots = _ids_param(r["id"] for r in rows if not r["parent_id"])
    stats: dict[str, dict[str, Any]] = {}
    for r in conn.execute(
        "SELECT parent_id, COUNT(*) AS n, MAX(created_at) AS last FROM messages"
        " WHERE deleted = 0 AND parent_id IN (SELECT value FROM json_each(?)) GROUP BY parent_id",
        (roots,),
    ):
        stats[r["parent_id"]] = {"reply_count": r["n"], "last_reply_at": r["last"] or 0.0, "reply_seeds": []}
    for r in conn.execute(
        "SELECT parent_id, sender FROM messages WHERE deleted = 0"
        " AND parent_id IN (SELECT value FROM json_each(?)) ORDER BY seq DESC",
        (roots,),
    ):
        seeds_of = stats[r["parent_id"]]["reply_seeds"]
        seed = seeds.get(r["sender"], r["sender"])
        if seed not in seeds_of and len(seeds_of) < 3:
            seeds_of.append(seed)

    messages = []
    for r in rows:
        preview = json.loads(r["preview"] or "{}")
        deleted = bool(r["deleted"])
        messages.append(
            ChatMessage(
                id=r["id"],
                seq=r["seq"],
                room=r["room"],
                parent_id=r["parent_id"],
                sender=r["sender"],
                display_name=names.get(r["sender"]) or r["display_name"] or r["sender"],
                content=r["content"],
                render="" if deleted else render_markdown(r["content"], names),
                timestamp=r["legacy_time"],
                created_at=r["created_at"],
                edited=bool(r["edited_at"]),
                deleted=deleted,
                is_system=bool(r["is_system"]),
                mentions=json.loads(r["mentions"] or "[]"),
                avatar_seed=seeds.get(r["sender"], r["sender"]),
                status_emoji=statuses.get(r["sender"], ""),
                pinned=r["id"] in pinned_ids,
                attachments=files.get(r["id"], []),
                reactions=[
                    Reaction(
                        emoji=emoji,
                        count=len(users),
                        users=users,
                        names=", ".join(names.get(u, u) for u in users),
                    )
                    for emoji, users in reactions.get(r["id"], {}).items()
                ],
                **{f"preview_{k}": str(preview.get(k, "")) for k in PREVIEW_KEYS},
                **stats.get(r["id"], {}),
            )
        )
    return messages


def get_message(msg_id: str) -> ChatMessage | None:
    row = message_row(msg_id)
    return build_messages([row])[0] if row else None


_VISIBLE_ROOT = (
    "(deleted = 0 OR EXISTS (SELECT 1 FROM messages c WHERE c.parent_id = messages.id AND c.deleted = 0))"
)


def room_messages(room: str, limit: int, before_seq: int | None = None) -> list[ChatMessage]:
    """The latest `limit` messages of a room (before `before_seq`), oldest first."""
    sql = f"SELECT * FROM messages WHERE room = ? AND parent_id = '' AND {_VISIBLE_ROOT}"
    args: list[Any] = [room]
    if before_seq is not None:
        sql += " AND seq < ?"
        args.append(before_seq)
    rows = _conn().execute(sql + " ORDER BY seq DESC LIMIT ?", (*args, limit)).fetchall()
    return build_messages(list(reversed(rows)))


def room_messages_between(room: str, from_seq: int, before_seq: int) -> list[ChatMessage]:
    rows = _conn().execute(
        f"SELECT * FROM messages WHERE room = ? AND parent_id = '' AND {_VISIBLE_ROOT}"
        " AND seq >= ? AND seq < ? ORDER BY seq",
        (room, from_seq, before_seq),
    ).fetchall()
    return build_messages(rows)


def has_older(room: str, before_seq: int) -> bool:
    return (
        _conn()
        .execute(
            f"SELECT 1 FROM messages WHERE room = ? AND parent_id = '' AND {_VISIBLE_ROOT} AND seq < ? LIMIT 1",
            (room, before_seq),
        )
        .fetchone()
        is not None
    )


def thread_replies(root_id: str) -> list[ChatMessage]:
    rows = _conn().execute(
        "SELECT * FROM messages WHERE parent_id = ? AND deleted = 0 ORDER BY seq", (root_id,)
    ).fetchall()
    return build_messages(rows)


# --- Reading, unread counts and notifications --------------------------------


def baseline(username: str) -> int:
    """Where `username` started reading: rooms never opened count from here."""
    conn = _conn()
    row = conn.execute("SELECT seq FROM reads WHERE username = ? AND room = '*'", (username,)).fetchone()
    if row:
        return row["seq"]
    seq = max_seq()
    conn.execute("INSERT OR IGNORE INTO reads(username, room, seq) VALUES (?, '*', ?)", (username, seq))
    return seq


def mark_read(username: str, room: str, seq: int | None = None):
    seq = max_seq(room) if seq is None else seq
    conn = _conn()
    row = conn.execute("SELECT seq FROM reads WHERE username = ? AND room = ?", (username, room)).fetchone()
    if row is not None and row["seq"] >= seq:
        # Open tabs call this every few seconds: write only when it moves.
        return
    conn.execute(
        "INSERT INTO reads(username, room, seq) VALUES (?, ?, ?) "
        "ON CONFLICT(username, room) DO UPDATE SET seq = MAX(seq, excluded.seq)",
        (username, room, seq),
    )


def unread_counts(username: str, rooms: Iterable[str]) -> tuple[dict[str, int], dict[str, int]]:
    """Unread room messages and unread mentions of `username`, per room."""
    conn = _conn()
    base = baseline(username)
    reads = {
        r["room"]: r["seq"]
        for r in conn.execute("SELECT room, seq FROM reads WHERE username = ? AND room != '*'", (username,))
    }
    allowed = set(rooms)
    muted = muted_rooms(username)
    unread: dict[str, int] = {}
    for room in allowed - muted:
        # Counts only the unread end of the room (messages_room index).
        n = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE room = ? AND parent_id = '' AND seq > ?"
            " AND deleted = 0 AND is_system = 0 AND sender != ?",
            (room, reads.get(room, base), username),
        ).fetchone()[0]
        if n:
            unread[room] = n
    floor = min([base, *reads.values()])
    seen: dict[str, set[int]] = {}
    for r in conn.execute(
        "SELECT x.seq, x.room, x.username FROM mentions x JOIN messages m ON m.seq = x.seq"
        " WHERE x.username IN (?, ?) AND x.seq > ? AND m.deleted = 0 AND m.sender != ?",
        (username, EVERYONE, floor, username),
    ):
        room = r["room"]
        if room not in allowed or r["seq"] <= reads.get(room, base):
            continue
        if r["username"] == EVERYONE and (room not in reads or room in muted):
            continue  # @here reaches people who have opened the room and not muted it
        seen.setdefault(room, set()).add(r["seq"])
    return unread, {room: len(seqs) for room, seqs in seen.items()}


def notifications_since(username: str, since_seq: int, rooms: dict[str, RoomInfo]) -> list[dict[str, Any]]:
    """Messages after `since_seq` that should notify `username`.

    Direct messages, mentions (@here only in rooms they have opened), and
    replies in threads they started or replied in.
    """
    direct = [name for name, room in rooms.items() if room.is_direct and room.can_view(username)]
    rows = _conn().execute(
        "SELECT m.*, EXISTS (SELECT 1 FROM mentions x WHERE x.seq = m.seq AND (x.username = :me"
        "   OR (x.username = :everyone AND EXISTS (SELECT 1 FROM reads r WHERE r.username = :me AND r.room = m.room))))"
        "   AS mentioned"
        " FROM messages m WHERE m.seq > :since AND m.sender != :me AND m.deleted = 0 AND m.is_system = 0 AND ("
        "   m.room IN (SELECT value FROM json_each(:direct))"
        "   OR EXISTS (SELECT 1 FROM mentions x WHERE x.seq = m.seq AND (x.username = :me"
        "     OR (x.username = :everyone AND EXISTS (SELECT 1 FROM reads r WHERE r.username = :me AND r.room = m.room))))"
        "   OR (m.parent_id != '' AND m.parent_id IN ("
        "     SELECT id FROM messages WHERE sender = :me AND parent_id = ''"
        "     UNION SELECT parent_id FROM messages WHERE sender = :me AND parent_id != '')))"
        " ORDER BY m.seq LIMIT 20",
        {"me": username, "everyone": EVERYONE, "since": since_seq, "direct": json.dumps(direct)},
    ).fetchall()
    names = display_names()
    muted = muted_rooms(username)
    left = left_rooms(username)
    items = []
    for r in rows:
        room = rooms.get(r["room"])
        if room is None or not room.can_view(username):
            continue
        if (r["room"] in muted or r["room"] in left) and username not in json.loads(r["mentions"] or "[]"):
            continue
        sender = names.get(r["sender"]) or r["display_name"] or r["sender"]
        text = r["plain"] or "Sent a file"
        title = room_title(room, username, names)
        if room.is_direct:
            kind, heading = "dm", sender
        elif r["mentioned"]:
            kind, heading = "mention", f"{sender} in #{title}"
        else:
            kind, heading = "thread", f"{sender} replied in #{title}"
        items.append(
            {
                "seq": r["seq"],
                "id": r["id"],
                "room": r["room"],
                "parent": r["parent_id"],
                "kind": kind,
                "title": heading,
                "body": " ".join(text.split())[:180],
                "seed": avatar_seeds().get(r["sender"], r["sender"]),
            }
        )
    return items


# --- Per-person room choices, pins, saved messages, scheduled posts ---------


def room_pref(username: str, room: str) -> tuple[bool, bool]:
    """(left, muted)."""
    row = _conn().execute(
        "SELECT left_room, muted FROM room_prefs WHERE username = ? AND room = ?", (username, room)
    ).fetchone()
    return (bool(row["left_room"]), bool(row["muted"])) if row else (False, False)


def set_room_pref(username: str, room: str, *, left: bool | None = None, muted: bool | None = None):
    was_left, was_muted = room_pref(username, room)
    _conn().execute(
        "INSERT OR REPLACE INTO room_prefs(username, room, left_room, muted) VALUES (?, ?, ?, ?)",
        (username, room, int(was_left if left is None else left), int(was_muted if muted is None else muted)),
    )


def muted_rooms(username: str) -> set[str]:
    return {
        r["room"]
        for r in _conn().execute("SELECT room FROM room_prefs WHERE username = ? AND muted = 1", (username,))
    }


def left_rooms(username: str) -> set[str]:
    return {
        r["room"]
        for r in _conn().execute("SELECT room FROM room_prefs WHERE username = ? AND left_room = 1", (username,))
    }


def toggle_pin(room: str, msg_id: str, username: str) -> bool:
    with _tx() as conn:
        if conn.execute("DELETE FROM pins WHERE room = ? AND message_id = ?", (room, msg_id)).rowcount:
            return False
        conn.execute(
            "INSERT INTO pins(room, message_id, pinned_by, created_at) VALUES (?, ?, ?, ?)",
            (room, msg_id, username, time.time()),
        )
    return True


def _items(rows: list[sqlite3.Row], viewer: str) -> list[SavedItem]:
    rooms = load_rooms()
    names = display_names()
    items = []
    for r in rows:
        room = rooms.get(r["room"])
        if room is None or not room.can_view(viewer):
            continue
        items.append(
            SavedItem(
                message_id=r["id"],
                room=r["room"],
                room_title=room_title(room, viewer, names),
                parent_id=r["parent_id"],
                display_name=names.get(r["sender"]) or r["display_name"] or r["sender"],
                text=" ".join(r["plain"].split())[:200] or "(file)",
                created_at=r["created_at"],
                remind_at=r["remind_at"] if "remind_at" in r.keys() else 0.0,
            )
        )
    return items


def pinned(room: str, viewer: str) -> list[SavedItem]:
    rows = _conn().execute(
        "SELECT m.* FROM pins p JOIN messages m ON m.id = p.message_id WHERE p.room = ? ORDER BY p.created_at DESC",
        (room,),
    ).fetchall()
    return _items(rows, viewer)


def saved_ids(username: str) -> list[str]:
    return [
        r["message_id"]
        for r in _conn().execute("SELECT message_id FROM saved WHERE username = ?", (username,))
    ]


def set_saved(username: str, msg_id: str, saved: bool, remind_at: float = 0.0):
    conn = _conn()
    if saved:
        conn.execute(
            "INSERT OR REPLACE INTO saved(username, message_id, created_at, remind_at) VALUES (?, ?, ?, ?)",
            (username, msg_id, time.time(), remind_at),
        )
    else:
        conn.execute("DELETE FROM saved WHERE username = ? AND message_id = ?", (username, msg_id))


def saved_items(username: str) -> list[SavedItem]:
    rows = _conn().execute(
        "SELECT m.*, s.remind_at AS remind_at FROM saved s JOIN messages m ON m.id = s.message_id"
        " WHERE s.username = ? ORDER BY s.created_at DESC",
        (username,),
    ).fetchall()
    return _items(rows, username)


def due_reminders(username: str) -> list[SavedItem]:
    """Reminders of `username` that are due; each comes back once."""
    now = time.time()
    conn = _conn()
    rows = conn.execute(
        "SELECT m.*, s.remind_at AS remind_at FROM saved s JOIN messages m ON m.id = s.message_id"
        " WHERE s.username = ? AND s.remind_at > 0 AND s.remind_at <= ?",
        (username, now),
    ).fetchall()
    if rows:
        conn.execute(
            "UPDATE saved SET remind_at = 0 WHERE username = ? AND remind_at > 0 AND remind_at <= ?", (username, now)
        )
    return _items(rows, username)


def add_scheduled(username: str, room: str, text: str, due_at: float) -> str:
    item_id = uuid.uuid4().hex
    _conn().execute(
        "INSERT INTO scheduled(id, username, room, text, due_at) VALUES (?, ?, ?, ?, ?)",
        (item_id, username, room, text, due_at),
    )
    return item_id


def cancel_scheduled(item_id: str, username: str):
    _conn().execute("DELETE FROM scheduled WHERE id = ? AND username = ?", (item_id, username))


def scheduled_items(username: str) -> list[ScheduledItem]:
    rooms = load_rooms()
    names = display_names()
    items = []
    for r in _conn().execute("SELECT * FROM scheduled WHERE username = ? ORDER BY due_at", (username,)):
        room = rooms.get(r["room"])
        if room is not None:
            items.append(
                ScheduledItem(
                    id=r["id"], room=r["room"], room_title=room_title(room, username, names),
                    text=" ".join(r["text"].split())[:200], due_at=r["due_at"],
                )
            )
    return items


def due_scheduled() -> list[sqlite3.Row]:
    return _conn().execute("SELECT * FROM scheduled WHERE due_at <= ? ORDER BY due_at", (time.time(),)).fetchall()


def remove_scheduled(item_id: str):
    _conn().execute("DELETE FROM scheduled WHERE id = ?", (item_id,))


# --- Webhooks, audit log, retention ------------------------------------------


def add_webhook(room: str, name: str, created_by: str) -> str:
    token = uuid.uuid4().hex + uuid.uuid4().hex
    _conn().execute(
        "INSERT INTO webhooks(token, room, name, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
        (token, room, name, created_by, time.time()),
    )
    return token


def room_webhooks(room: str) -> list[WebhookInfo]:
    return [
        WebhookInfo(token=r["token"], name=r["name"], created_by=r["created_by"])
        for r in _conn().execute("SELECT * FROM webhooks WHERE room = ? ORDER BY created_at", (room,))
    ]


def delete_webhook(room: str, token: str):
    _conn().execute("DELETE FROM webhooks WHERE room = ? AND token = ?", (room, token))


def webhook(token: str) -> sqlite3.Row | None:
    return _conn().execute("SELECT * FROM webhooks WHERE token = ?", (token,)).fetchone()


def audit(actor: str, action: str, target: str = "", detail: str = ""):
    _conn().execute(
        "INSERT INTO audit(at, actor, action, target, detail) VALUES (?, ?, ?, ?, ?)",
        (time.time(), actor, action, target, detail[:500]),
    )


def audit_entries(limit: int = 300) -> list[AuditEntry]:
    return [
        AuditEntry(at=r["at"], actor=r["actor"], action=r["action"], target=r["target"], detail=r["detail"])
        for r in _conn().execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))
    ]


def purge_older_than(days: int) -> int:
    """Delete messages (with their threads and files) older than `days` days."""
    cutoff = time.time() - days * 86400
    conn = _conn()
    ids = [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM messages WHERE created_at > 0 AND created_at < ? AND parent_id = ''"
            " AND NOT EXISTS (SELECT 1 FROM messages c WHERE c.parent_id = messages.id AND c.created_at >= ?)",
            (cutoff, cutoff),
        )
    ]
    paths: list[str] = []
    with _tx() as tx:
        for msg_id in ids:
            for r in tx.execute("SELECT id FROM messages WHERE parent_id = ?", (msg_id,)).fetchall():
                paths += _purge(tx, r["id"])
            paths += _purge(tx, msg_id)
    for path in paths:
        _remove_file(path)
    return len(ids)


# --- Search -------------------------------------------------------------------


def _like(query: str) -> str:
    return "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search_messages(query: str, viewer: str, rooms: dict[str, RoomInfo], limit: int = 50) -> list[SearchHit]:
    query = query.strip()
    if not query:
        return []
    conn = _conn()
    if _fts_enabled.get(str(db_path())) and len(query) >= 3:
        rows = conn.execute(
            "SELECT m.* FROM messages_fts f JOIN messages m ON m.seq = f.rowid"
            " WHERE messages_fts MATCH ? AND m.deleted = 0 ORDER BY m.seq DESC LIMIT ?",
            ('"' + query.replace('"', '""') + '"', limit * 4),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM messages WHERE deleted = 0 AND plain LIKE ? ESCAPE '\\' ORDER BY seq DESC LIMIT ?",
            (_like(query), limit * 4),
        ).fetchall()
    names = display_names()
    seeds = avatar_seeds()
    hits = []
    for r in rows:
        room = rooms.get(r["room"])
        if room is None or not room.can_view(viewer):
            continue
        before, match, after = snippet(r["plain"], query)
        hits.append(
            SearchHit(
                message_id=r["id"],
                room=r["room"],
                room_title=room_title(room, viewer, names),
                parent_id=r["parent_id"],
                sender=r["sender"],
                display_name=names.get(r["sender"]) or r["display_name"] or r["sender"],
                avatar_seed=seeds.get(r["sender"], r["sender"]),
                created_at=r["created_at"],
                before=before,
                match=match,
                after=after,
            )
        )
        if len(hits) >= limit:
            break
    return hits


def search_files(query: str, viewer: str, rooms: dict[str, RoomInfo], limit: int = 30) -> list[FileHit]:
    query = query.strip()
    if not query:
        return []
    rows = _conn().execute(
        "SELECT f.*, m.parent_id AS parent_id, m.sender AS sender FROM files f JOIN messages m ON m.id = f.message_id"
        " WHERE m.deleted = 0 AND f.name LIKE ? ESCAPE '\\' ORDER BY f.created_at DESC LIMIT ?",
        (_like(query), limit * 4),
    ).fetchall()
    names = display_names()
    hits = []
    for r in rows:
        room = rooms.get(r["room"])
        if room is None or not room.can_view(viewer):
            continue
        hits.append(
            FileHit(
                file=_attachment(r),
                message_id=r["message_id"],
                room=r["room"],
                room_title=room_title(room, viewer, names),
                parent_id=r["parent_id"],
                uploader=names.get(r["uploader"], r["uploader"]),
                created_at=r["created_at"],
            )
        )
        if len(hits) >= limit:
            break
    return hits


def search_people(query: str, limit: int = 20) -> list[UserProfile]:
    query = query.strip().lower()
    if not query:
        return []
    found = [
        p
        for p in load_profiles().values()
        if query in p.username.lower() or query in p.nickname.lower() or query in p.email.lower()
    ]
    return sorted(found, key=lambda p: (p.nickname or p.username).lower())[:limit]


# --- Admin: recent messages, export, import, clear -----------------------------


def recent_messages(limit: int = 200) -> list[ChatMessage]:
    rows = _conn().execute(
        "SELECT * FROM messages WHERE deleted = 0 ORDER BY seq DESC LIMIT ?", (limit,)
    ).fetchall()
    return build_messages(list(reversed(rows)))


def export_all() -> dict[str, Any]:
    conn = _conn()
    messages: dict[str, list[dict[str, Any]]] = {}
    rows = conn.execute("SELECT * FROM messages ORDER BY seq").fetchall()
    for msg in build_messages(rows):
        data = msg.model_dump(
            include={
                "id", "sender", "display_name", "content", "timestamp", "is_system", "created_at",
                "edited", "deleted", "parent_id", "mentions", "preview_url", "preview_title",
                "preview_description", "preview_image", "preview_site",
            }
        )
        data["reactions"] = [{"emoji": r.emoji, "users": r.users} for r in msg.reactions]
        data["attachments"] = [a.model_dump(include={"id", "name", "path", "mime", "size"}) for a in msg.attachments]
        messages.setdefault(msg.room, []).append(data)
    return {
        "version": 2,
        "rooms": [room.model_dump() for room in load_rooms().values()],
        "profiles": [p.model_dump() for p in load_profiles().values()],
        "messages_by_room": messages,
        "permissions": get_setting("permissions"),
        "approved_users": get_setting("approved_users", {}),
        "admins": get_setting("admins", []),
        "retention_days": get_setting("retention_days", 0),
        **{table: [dict(r) for r in conn.execute(f"SELECT * FROM {table}")] for table in _EXTRA_TABLES},
    }


# Tables an export carries as plain rows.
_EXTRA_TABLES = ("room_prefs", "pins", "saved", "scheduled", "webhooks")


def _clear_tables(conn: sqlite3.Connection):
    for table in (
        "rooms", "profiles", "settings", "messages", "reactions", "files", "mentions", "reads",
        "room_prefs", "pins", "saved", "scheduled", "webhooks",
    ):
        conn.execute(f"DELETE FROM {table}")
    if _fts_enabled.get(str(db_path())):
        conn.execute("INSERT INTO messages_fts(messages_fts) VALUES ('delete-all')")


def clear_all():
    """Forget rooms, people, messages and settings (logins, admins and retention stay)."""
    kept = {key: get_setting(key) for key in ("admins", "retention_days")}
    with _tx() as conn:
        _clear_tables(conn)
        for key, value in kept.items():
            if value:
                conn.execute("INSERT INTO settings(key, value) VALUES (?, ?)", (key, json.dumps(value)))
    shutil.rmtree(upload_root(), ignore_errors=True)
    _cache.pop(str(db_path()), None)


def import_all(data: dict[str, Any]):
    """Replace everything with an export (this version's or an older one).

    The whole file is checked before anything changes, then written in one
    transaction, so a bad file leaves the current data as it was.
    """
    from relack.formatting import resolve_mentions  # noqa: WPS433

    rooms = [RoomInfo(**room) for room in data.get("rooms", [])]
    profiles = [UserProfile(**p) for p in data.get("profiles", [])]
    permissions = data.get("permissions")
    approved = {str(k): bool(v) for k, v in (data.get("approved_users") or {}).items()}
    kept = {
        "admins": data["admins"] if "admins" in data else get_setting("admins", []),
        "retention_days": data["retention_days"] if "retention_days" in data else get_setting("retention_days", 0),
    }
    extra = {table: [dict(r) for r in data.get(table) or []] for table in _EXTRA_TABLES}
    names = {p.username: (p.nickname or p.username) for p in profiles}
    messages = []
    for room_name, msgs in (data.get("messages_by_room") or {}).items():
        for raw in msgs:
            content = str(raw.get("content", ""))
            mentions = raw.get("mentions")
            if mentions is None:
                content, mentions = resolve_mentions(content, names)
            deleted = bool(raw.get("deleted"))
            created_at = float(raw.get("created_at") or 0.0)
            messages.append(
                {
                    "fields": {
                        "room": str(room_name),
                        "sender": str(raw.get("sender", "")),
                        "display_name": str(raw.get("display_name", "")),
                        "content": "" if deleted else content,
                        "plain": "" if deleted else plain_text(content, names),
                        "mentions": [] if deleted else [str(m) for m in mentions],
                        "preview": {} if deleted else {
                            k: str(raw[f"preview_{k}"]) for k in PREVIEW_KEYS if raw.get(f"preview_{k}")
                        },
                        "parent_id": str(raw.get("parent_id", "")),
                        "is_system": bool(raw.get("is_system")),
                        "created_at": created_at,
                        "msg_id": str(raw.get("id") or "") or None,
                        "legacy_time": str(raw.get("timestamp", "")) if not created_at else "",
                        "edited_at": time.time() if raw.get("edited") else 0.0,
                        "deleted": deleted,
                    },
                    "reactions": [
                        (str(r.get("emoji", "")), str(user))
                        for r in raw.get("reactions", [])
                        for user in r.get("users", [])
                    ],
                    "attachments": [
                        att
                        for att in raw.get("attachments", [])
                        if isinstance(att, dict) and valid_file_path(str(att.get("path", "")))
                    ],
                }
            )

    with _tx() as conn:
        _clear_tables(conn)
        now = time.time()
        for i, room in enumerate(rooms):
            conn.execute(
                "INSERT INTO rooms(name, data, created_at) VALUES (?, ?, ?)",
                (room.name, room.model_dump_json(), now + i * 1e-3),
            )
        for p in profiles:
            conn.execute(
                "INSERT INTO profiles(username, data, updated_at) VALUES (?, ?, ?)",
                (p.username, p.model_dump_json(), now),
            )
        if permissions:
            conn.execute("INSERT INTO settings(key, value) VALUES ('permissions', ?)", (json.dumps(permissions),))
        conn.execute("INSERT INTO settings(key, value) VALUES ('approved_users', ?)", (json.dumps(approved),))
        for key, value in kept.items():
            conn.execute("INSERT INTO settings(key, value) VALUES (?, ?)", (key, json.dumps(value)))
        for msg in messages:
            msg_id, _seq = _insert_message(conn, **msg["fields"])
            for emoji, user in msg["reactions"]:
                conn.execute(
                    "INSERT OR IGNORE INTO reactions(message_id, emoji, username, created_at) VALUES (?, ?, ?, ?)",
                    (msg_id, emoji, user, now),
                )
            for att in msg["attachments"]:
                conn.execute(
                    "INSERT OR IGNORE INTO files(id, message_id, room, uploader, name, path, mime, size, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(att.get("id") or uuid.uuid4().hex),
                        msg_id,
                        msg["fields"]["room"],
                        msg["fields"]["sender"],
                        safe_file_name(str(att.get("name", "file"))),
                        str(att["path"]),
                        str(att.get("mime", "")),
                        int(att.get("size") or 0),
                        msg["fields"]["created_at"] or now,
                    ),
                )
        for table, rows in extra.items():
            for row in rows:
                columns = ", ".join(c for c in row if c.isidentifier())
                marks = ", ".join("?" for c in row if c.isidentifier())
                conn.execute(
                    f"INSERT OR IGNORE INTO {table}({columns}) VALUES ({marks})",
                    [v for c, v in row.items() if c.isidentifier()],
                )
    _cache.pop(str(db_path()), None)


def is_empty() -> bool:
    conn = _conn()
    return (
        conn.execute("SELECT 1 FROM rooms LIMIT 1").fetchone() is None
        and conn.execute("SELECT 1 FROM messages LIMIT 1").fetchone() is None
    )
