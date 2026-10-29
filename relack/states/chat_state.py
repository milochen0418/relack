"""Per-tab chat state: the open thread, editing, older history, uploads, search, unread counts."""

import json
import logging
import mimetypes
import os

import reflex as rx
from reflex_ddns_auth.intent import Intent

from relack import db
from relack.formatting import plain_text
from relack.models import Attachment, ChatMessage, FileHit, SearchHit, UserProfile
from relack.states.auth_state import AuthState
from relack.states.shared_state import LocalUIState, RoomState, TabSessionState

MAX_UPLOAD_BYTES = int(os.environ.get("RELACK_MAX_UPLOAD_MB", "200")) * 1024 * 1024
# Older room messages loaded per "Load earlier messages".
OLDER_PAGE = 50


class ChatUIState(rx.State):
    """What this tab shows around the room's shared messages."""

    # Root message of the thread open in the side panel.
    thread_id: str = ""
    editing_id: str = ""
    edit_text: str = ""
    deleting_id: str = ""
    # Message to point at after a jump (search result, notification).
    highlight_id: str = ""
    # Messages older than the room's shared window, loaded by this tab, and
    # whether there are more before them.
    older: list[ChatMessage] = []
    has_older: bool = False
    # RoomState.history_rev they were loaded at.
    _older_rev: int = -1

    @rx.var
    def last_older_at(self) -> float:
        return self.older[-1].created_at if self.older else 0.0

    def reset_room(self):
        self.thread_id = ""
        self.editing_id = ""
        self.deleting_id = ""
        self.highlight_id = ""
        self.older = []
        self.has_older = False
        self._older_rev = -1

    def replace_older(self, msg: ChatMessage):
        if any(m.id == msg.id for m in self.older):
            self.older = [msg if m.id == msg.id else m for m in self.older]

    def remove_older(self, ids: list[str]):
        if ids:
            self.older = [m for m in self.older if m.id not in ids]

    @rx.event
    def close_thread(self):
        self.thread_id = ""

    @rx.event
    async def start_edit(self, msg_id: str):
        auth = await self.get_state(AuthState)
        row = db.message_row(msg_id)
        if not auth.user or row is None or row["sender"] != auth.user.username or row["deleted"]:
            return
        self.edit_text = plain_text(row["content"], db.display_names())
        self.editing_id = msg_id

    @rx.event
    def cancel_edit(self):
        self.editing_id = ""

    @rx.event
    def ask_delete(self, msg_id: str):
        self.deleting_id = msg_id

    @rx.event
    def cancel_delete(self):
        self.deleting_id = ""

    @rx.event
    def set_delete_open(self, is_open: bool):
        if not is_open:
            self.deleting_id = ""

    @rx.event
    async def load_earlier(self):
        room = await self.get_state(RoomState)
        name = room.room_name
        if not name:
            return
        await self._reload_older(room)
        first = self.older[0].seq if self.older else (room._messages[0].seq if room._messages else None)
        if first is None:
            self.has_older = False
            return
        page = db.room_messages(name, OLDER_PAGE, before_seq=first)
        self.older = page + self.older
        self.has_older = bool(page) and db.has_older(name, page[0].seq)

    async def _reload_older(self, room: RoomState):
        """Load this tab's older messages again, up to where the shared window now starts."""
        if self.older and self._older_rev != room.history_rev:
            end = room._messages[0].seq if room._messages else db.max_seq(room.room_name) + 1
            self.older = db.room_messages_between(room.room_name, self.older[0].seq, end)
        self._older_rev = room.history_rev

    @rx.event
    async def refresh_older(self):
        """The room's window moved or an older message changed (RoomState.history_rev)."""
        room = await self.get_state(RoomState)
        if room.room_name:
            await self._reload_older(room)

    @rx.event
    async def jump_to(self, room_name: str, msg_id: str, parent_id: str = ""):
        """Open a room at a message (and its thread), e.g. from search or a notification."""
        local = await self.get_state(LocalUIState)
        local.main_view = "rooms"
        room = await self.get_state(RoomState)
        if room.room_name != room_name:
            await room.handle_join_room(room_name)
            room = await self.get_state(RoomState)
        if room.room_name != room_name:
            return
        target = parent_id or msg_id
        row = db.message_row(target)
        if row is None or row["room"] != room_name:
            return
        await self._reload_older(room)
        shown = {m.id for m in room._messages} | {m.id for m in self.older}
        if target not in shown:
            first = self.older[0].seq if self.older else (room._messages[0].seq if room._messages else None)
            if first is not None and row["seq"] < first:
                self.older = db.room_messages_between(room_name, row["seq"], first) + self.older
                self.has_older = db.has_older(room_name, row["seq"])
        self.highlight_id = msg_id
        events = [rx.call_script(f"window.relackScrollTo && window.relackScrollTo({json.dumps('msg-' + target)})")]
        if parent_id:
            events.insert(0, RoomState.open_thread(parent_id))
            events.append(
                rx.call_script(f"window.relackScrollTo && window.relackScrollTo({json.dumps('msg-' + msg_id)})")
            )
        return events

    @rx.event
    async def bridge(self, value: str):
        """Requests from the page's script (a notification click, a mention link)."""
        try:
            data = json.loads(value)
        except (TypeError, ValueError):
            return
        if data.get("op") == "jump":
            return ChatUIState.jump_to(data.get("room", ""), data.get("id", ""), data.get("parent", ""))
        if data.get("op") == "profile" and data.get("user"):
            return Intent.start("relack", "profile.view", user=data["user"])


class ComposerState(rx.State):
    """Files uploaded in this tab, waiting to go out with the next message."""

    pending: list[Attachment] = []
    pending_thread: list[Attachment] = []
    uploading: bool = False

    async def _store(self, files: list[rx.UploadFile]) -> list[Attachment]:
        auth = await self.get_state(AuthState)
        if not auth.user:
            return []
        stored = []
        for upload in files:
            name = upload.name or upload.filename or "file"
            rel, target = db.new_file_path(name)
            size = 0
            with target.open("wb") as out:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        break
                    out.write(chunk)
            if size > MAX_UPLOAD_BYTES:
                target.unlink(missing_ok=True)
                continue
            mime = upload.content_type or mimetypes.guess_type(name)[0] or ""
            stored.append(db.add_file(auth.user.username, name, rel, mime, size))
        return stored

    async def _store_safely(self, files: list[rx.UploadFile]) -> tuple[list[Attachment], int]:
        """Store what can be stored; returns the files and how many failed."""
        stored: list[Attachment] = []
        for upload in files:
            try:
                stored += await self._store([upload])
            except Exception:
                logging.exception("upload of %s failed", upload.name or upload.filename)
        return stored, len(files) - len(stored)

    @rx.event
    async def upload_main(self, files: list[rx.UploadFile]):
        stored, failed = await self._store_safely(files)
        self.pending = [*self.pending, *stored]
        self.uploading = False
        if failed:
            return rx.toast.error(f"{failed} file(s) were not added (over {MAX_UPLOAD_BYTES // (1024 * 1024)} MB?).")

    @rx.event
    async def upload_thread(self, files: list[rx.UploadFile]):
        stored, failed = await self._store_safely(files)
        self.pending_thread = [*self.pending_thread, *stored]
        self.uploading = False
        if failed:
            return rx.toast.error(f"{failed} file(s) were not added (over {MAX_UPLOAD_BYTES // (1024 * 1024)} MB?).")

    @rx.event
    def upload_progress(self, progress: dict):
        self.uploading = progress.get("progress", 1) < 1

    @rx.event
    async def remove_pending(self, file_id: str):
        auth = await self.get_state(AuthState)
        if auth.user:
            db.discard_pending_file(file_id, auth.user.username)
        self.pending = [f for f in self.pending if f.id != file_id]
        self.pending_thread = [f for f in self.pending_thread if f.id != file_id]


class SearchState(rx.State):
    """The sidebar search box: filters rooms as you type, Enter searches everything."""

    query: str = ""
    searched: str = ""
    messages: list[SearchHit] = []
    files: list[FileHit] = []
    people: list[UserProfile] = []

    @rx.var
    def room_filter(self) -> str:
        return self.query.strip().lower()

    @rx.event
    def set_query(self, value: str):
        self.query = value

    @rx.event
    async def run(self, form_data: dict | None = None):
        query = ((form_data or {}).get("q") or self.query).strip()
        self.query = query
        if not query:
            return
        auth = await self.get_state(AuthState)
        if not auth.user:
            return
        me = auth.user.username
        rooms = db.load_rooms()
        self.searched = query
        self.messages = db.search_messages(query, me, rooms)
        self.files = db.search_files(query, me, rooms)
        self.people = db.search_people(query)
        local = await self.get_state(LocalUIState)
        local.main_view = "search"

    @rx.event
    async def close(self):
        local = await self.get_state(LocalUIState)
        local.main_view = "rooms"
        self.query = ""
        return rx.set_value("relack-search", "")


class UnreadState(rx.State):
    """Unread counts of this tab's user, and the notifications they should get."""

    unread: dict[str, int] = {}
    mentions: dict[str, int] = {}
    # Shown in the tab title.
    total: int = 0
    # Notification.permission in this browser.
    permission: str = "default"
    # This browser's choices, read by the page script ("on" / "off").
    desktop: str = rx.LocalStorage("on", name="relack_desktop")
    sound: str = rx.LocalStorage("on", name="relack_sound")
    _notified_seq: int = 0
    _user: str = ""

    @rx.event
    def set_permission(self, value: str):
        self.permission = value or "default"

    @rx.event
    def toggle_desktop(self):
        self.desktop = "off" if self.desktop != "off" else "on"

    @rx.event
    def toggle_sound(self):
        self.sound = "off" if self.sound != "off" else "on"

    @rx.event
    async def sync(self, seen: bool):
        """Refresh counts; `seen` when the tab is in front, so its open room counts as read."""
        auth = await self.get_state(AuthState)
        if not auth.user:
            return
        me = auth.user.username
        if self._user != me:
            self._user, self._notified_seq = me, 0
        rooms = {name: room for name, room in db.load_rooms().items() if room.can_view(me)}
        tab = await self.get_state(TabSessionState)
        current = tab.curr_room_name if tab.curr_room_name in rooms else ""
        if seen and current:
            db.mark_read(me, current)
        unread, mentions = db.unread_counts(me, rooms)
        if seen and current:
            unread.pop(current, None)
            mentions.pop(current, None)
        if unread != self.unread:
            self.unread = unread
        if mentions != self.mentions:
            self.mentions = mentions
        total = sum(max(unread.get(r, 0), mentions.get(r, 0)) for r in {*unread, *mentions})
        if total != self.total:
            self.total = total

        latest = db.max_seq()
        if not self._notified_seq:
            self._notified_seq = latest
            return
        if latest <= self._notified_seq:
            return
        items = db.notifications_since(me, self._notified_seq, rooms)
        self._notified_seq = latest
        if items:
            return rx.call_script(f"window.relackNotify && window.relackNotify({json.dumps(items)})")
