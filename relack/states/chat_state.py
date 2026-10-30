"""Per-tab chat state: the open thread, editing, older history, uploads, search, unread counts."""

import json
import time
import logging
import mimetypes
import os

import reflex as rx
from reflex_ddns_auth.intent import Intent

from relack import db, permissions
from relack.formatting import plain_text
from relack.commands import set_status
from relack.models import (
    Attachment, ChatMessage, FileHit, RoomBrowseItem, SavedItem, ScheduledItem, SearchHit,
    UserProfile, WebhookInfo,
)
from relack import posting
from relack.states.auth_state import AuthState
from relack.states.shared_state import GlobalLobbyState, LocalUIState, RoomState, TabSessionState

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
    forwarding_id: str = ""
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
    def ask_forward(self, msg_id: str):
        self.forwarding_id = msg_id

    @rx.event
    def set_forward_open(self, is_open: bool):
        if not is_open:
            self.forwarding_id = ""

    @rx.event
    async def forward_to(self, room_name: str):
        """Post a quote of the message in another room."""
        msg_id, self.forwarding_id = self.forwarding_id, ""
        auth = await self.get_state(AuthState)
        row = db.message_row(msg_id)
        rooms = db.load_rooms()
        source, target = rooms.get(row["room"]) if row else None, rooms.get(room_name)
        if (
            not auth.user or permissions.is_pending(auth.user) or source is None or target is None
            or target.archived or not source.can_view(auth.user.username) or not target.can_view(auth.user.username)
        ):
            return rx.toast("This message can't be forwarded there.")
        me = auth.user
        names = db.display_names()
        quote = "\n".join("> " + line for line in row["plain"].splitlines())
        text = f"Forwarded from {names.get(row['sender'], row['sender'])}:\n{quote}"
        await posting.post(target, me.username, me.nickname or me.username, text, mentions=False)
        return rx.toast("Forwarded.")

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
        local.show("rooms")
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
        op = data.get("op")
        if op == "jump":
            return ChatUIState.jump_to(data.get("room", ""), data.get("id", ""), data.get("parent", ""))
        if op == "link":
            row = db.message_row(str(data.get("id", "")))
            if row is not None:
                return ChatUIState.jump_to(row["room"], row["id"], row["parent_id"])
            return None
        if op == "typing":
            await (await self.get_state(RoomState)).mark_typing()
            return None
        if op == "viewport":
            local = await self.get_state(LocalUIState)
            narrow = bool(data.get("narrow"))
            if narrow and not local.is_narrow and (await self.get_state(RoomState)).room_name:
                local.is_sidebar_open = False
            elif local.is_narrow and not narrow:
                # Grown past the drawer size: the list has room beside the chat again.
                local.is_sidebar_open = True
            local.is_narrow = narrow
            auth = await self.get_state(AuthState)
            zone = str(data.get("zone", ""))[:60]
            if auth.user and zone and db.load_profiles().get(auth.user.username, auth.user).timezone != zone:
                await set_status(self, auth.user, timezone=zone)
            return None
        if op == "later":
            return LaterState.schedule(str(data.get("text", "")), float(data.get("seconds", 0)))
        if data.get("op") == "profile" and data.get("user"):
            return Intent.start("relack", "profile.view", user=data["user"])


class ComposerState(rx.State):
    """Files uploaded in this tab, waiting to go out with the next message."""

    pending: list[Attachment] = []
    pending_thread: list[Attachment] = []
    uploading: bool = False

    async def _store(self, files: list[rx.UploadFile]) -> list[Attachment]:
        auth = await self.get_state(AuthState)
        if not auth.user or permissions.is_pending(auth.user):
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
        if not auth.user or permissions.is_pending(auth.user):
            return
        me = auth.user.username
        rooms = db.load_rooms()
        self.searched = query
        self.messages = db.search_messages(query, me, rooms)
        self.files = db.search_files(query, me, rooms)
        self.people = db.search_people(query) if permissions.can(auth.user, "view_profiles") else []
        local = await self.get_state(LocalUIState)
        local.show("search")

    @rx.event
    async def close(self):
        local = await self.get_state(LocalUIState)
        local.main_view = "rooms"
        self.query = ""
        return rx.set_value("relack-search", "")


class LaterState(rx.State):
    """This person's saved messages and scheduled posts, and the room's pins."""

    saved_ids: list[str] = []
    items: list[SavedItem] = []
    scheduled: list[ScheduledItem] = []
    pins: list[SavedItem] = []

    @rx.event
    async def load(self):
        auth = await self.get_state(AuthState)
        if auth.user:
            me = auth.user.username
            self.saved_ids = db.saved_ids(me)
            self.items = db.saved_items(me)
            self.scheduled = db.scheduled_items(me)

    @rx.event
    async def load_pins(self):
        auth = await self.get_state(AuthState)
        tab = await self.get_state(TabSessionState)
        rooms = db.load_rooms()
        room = rooms.get(tab.curr_room_name)
        if auth.user and room and room.can_view(auth.user.username):
            self.pins = db.pinned(room.name, auth.user.username)

    async def _own(self, msg_id: str) -> str:
        """The user's name, if they can see the message."""
        auth = await self.get_state(AuthState)
        row = db.message_row(msg_id)
        room = db.load_rooms().get(row["room"]) if row else None
        if not auth.user or not room or not room.can_view(auth.user.username) or permissions.is_pending(auth.user):
            return ""
        return auth.user.username

    @rx.event
    async def toggle_saved(self, msg_id: str):
        me = await self._own(msg_id)
        if me:
            db.set_saved(me, msg_id, msg_id not in db.saved_ids(me))
            await self.load()

    @rx.event
    async def remind(self, msg_id: str, seconds: int):
        me = await self._own(msg_id)
        if me:
            db.set_saved(me, msg_id, True, time.time() + seconds)
            await self.load()
            return rx.toast("Reminder set.")

    @rx.event
    async def schedule(self, text: str, seconds: float):
        auth = await self.get_state(AuthState)
        tab = await self.get_state(TabSessionState)
        room = db.load_rooms().get(tab.curr_room_name)
        text = text.strip()
        if (
            not auth.user or room is None or not room.can_view(auth.user.username) or room.archived
            or not text or permissions.is_pending(auth.user)
        ):
            return
        db.add_scheduled(auth.user.username, room.name, text[: posting.MAX_MESSAGE_CHARS], time.time() + max(seconds, 60))
        await self.load()
        return rx.toast("Scheduled.")

    @rx.event
    async def cancel_scheduled(self, item_id: str):
        auth = await self.get_state(AuthState)
        if auth.user:
            db.cancel_scheduled(item_id, auth.user.username)
            await self.load()


class StatusState(rx.State):
    """The status box above the room list."""

    emoji: str = ""
    text: str = ""
    dnd_until: float = 0.0

    @rx.event
    async def load(self):
        auth = await self.get_state(AuthState)
        if auth.user:
            profile = db.load_profiles().get(auth.user.username, auth.user)
            self.emoji, self.text = db.active_status(profile)
            self.dnd_until = profile.dnd_until if profile.dnd_until > time.time() else 0.0

    @rx.event
    def set_text(self, value: str):
        self.text = value[:100]

    @rx.event
    async def save(self, emoji: str):
        auth = await self.get_state(AuthState)
        if auth.user:
            await set_status(self, auth.user, status_emoji=emoji, status_text=self.text, status_until=0.0)
            await self.load()

    @rx.event
    async def clear(self):
        self.text = ""
        await self.save("")

    @rx.event
    async def set_dnd(self, seconds: int):
        auth = await self.get_state(AuthState)
        if auth.user:
            await set_status(self, auth.user, dnd_until=time.time() + seconds if seconds else 0.0)
            await self.load()


class RoomAdminState(rx.State):
    """The room settings dialog and the Browse rooms list."""

    is_open: bool = False
    room: str = ""
    title: str = ""
    description: str = ""
    can_manage: bool = False
    is_private: bool = False
    archived: bool = False
    muted: bool = False
    members: list[UserProfile] = []
    hooks: list[WebhookInfo] = []
    hook_name: str = ""
    browse: list[RoomBrowseItem] = []

    @rx.event
    def set_title(self, value: str):
        self.title = value

    @rx.event
    def set_description(self, value: str):
        self.description = value

    @rx.event
    def set_hook_name(self, value: str):
        self.hook_name = value

    @rx.event
    def set_open(self, is_open: bool):
        self.is_open = is_open

    def _manager(self, user, info) -> bool:
        return bool(user) and not info.is_direct and (info.created_by == user.username or permissions.is_admin(user))

    async def _fill(self, name: str):
        auth = await self.get_state(AuthState)
        info = db.load_rooms().get(name)
        if not auth.user or info is None or not info.can_view(auth.user.username):
            return False
        me = auth.user.username
        self.room, self.title, self.description = name, info.title or name, info.description
        self.is_private, self.archived = info.is_private, info.archived
        self.can_manage = self._manager(auth.user, info)
        self.muted = db.room_pref(me, name)[1]
        profiles = db.load_profiles()
        self.members = [
            profiles.get(u) or UserProfile(username=u, is_guest=False, avatar_seed=u) for u in info.allowed_members
        ]
        self.hooks = db.room_webhooks(name) if self.can_manage else []
        return True

    @rx.event
    async def open_settings(self, name: str):
        self.is_open = await self._fill(name)

    @rx.event
    async def save(self):
        yield GlobalLobbyState.update_room(self.room, self.title, self.description)
        self.is_open = False

    @rx.event
    async def toggle_muted(self):
        auth = await self.get_state(AuthState)
        if auth.user and self.room:
            self.muted = not self.muted
            db.set_room_pref(auth.user.username, self.room, muted=self.muted)

    @rx.event
    def add_member(self, data: dict):
        """`people.pick` result handler."""
        self.is_open = True
        return [GlobalLobbyState.add_room_member(self.room, data.get("user", "")), RoomAdminState.refresh]

    @rx.event
    def remove_member(self, username: str):
        return [GlobalLobbyState.remove_room_member(self.room, username), RoomAdminState.refresh]

    @rx.event
    async def refresh(self):
        await self._fill(self.room)

    @rx.event
    async def add_hook(self):
        auth = await self.get_state(AuthState)
        info = db.load_rooms().get(self.room)
        name = self.hook_name.strip()
        if not info or not name or not self._manager(auth.user, info):
            return
        db.add_webhook(self.room, name[:60], auth.user.username)
        db.audit(auth.user.username, "webhook.create", self.room, name)
        self.hook_name = ""
        self.hooks = db.room_webhooks(self.room)
        return rx.set_value("relack-hook-name", "")

    @rx.event
    async def delete_hook(self, token: str):
        auth = await self.get_state(AuthState)
        info = db.load_rooms().get(self.room)
        if info and self._manager(auth.user, info):
            db.delete_webhook(self.room, token)
            db.audit(auth.user.username, "webhook.delete", self.room)
            self.hooks = db.room_webhooks(self.room)

    @rx.event
    async def load_browse(self):
        auth = await self.get_state(AuthState)
        if not auth.user:
            return
        me = auth.user.username
        left = db.left_rooms(me)
        names = db.display_names()
        self.browse = [
            RoomBrowseItem(
                name=r.name, title=db.room_title(r, me, names), description=r.description,
                archived=r.archived, joined=r.name not in left, can_manage=self._manager(auth.user, r),
            )
            for r in db.load_rooms().values()
            if r.can_view(me) and not r.is_direct
        ]

    @rx.event
    def rejoin(self, name: str):
        return [GlobalLobbyState.set_room_left(name, False), RoomAdminState.load_browse]

    @rx.event
    def leave(self, name: str):
        return [GlobalLobbyState.set_room_left(name, True), RoomAdminState.load_browse]

    @rx.event
    def unarchive(self, name: str):
        return [GlobalLobbyState.set_archived(name, False), RoomAdminState.load_browse]


class UnreadState(rx.State):
    """Unread counts of this tab's user, and the notifications they should get."""

    unread: dict[str, int] = {}
    mentions: dict[str, int] = {}
    # Shown in the tab title.
    total: int = 0
    # Notification.permission in this browser.
    permission: str = "default"
    # What this user may do; refreshed with the counts.
    pending: bool = False
    can_create_room: bool = True
    can_mention: bool = True
    muted: list[str] = []
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
        self.pending = permissions.is_pending(auth.user)
        self.can_create_room = permissions.can(auth.user, "create_room")
        self.can_mention = permissions.can(auth.user, "mention_users")
        if self.pending:
            return
        rooms = {name: room for name, room in db.load_rooms().items() if room.can_view(me)}
        muted = sorted(db.muted_rooms(me))
        if muted != self.muted:
            self.muted = muted
        tab = await self.get_state(TabSessionState)
        current = tab.curr_room_name if tab.curr_room_name in rooms else ""
        if seen and current:
            db.mark_read(me, current)
        left = db.left_rooms(me)
        unread, mentions = db.unread_counts(
            me, [name for name, room in rooms.items() if name not in left and not room.archived]
        )
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
        reminders = [
            {
                "seq": 0, "id": "remind-" + r.message_id + str(int(time.time())), "room": r.room,
                "parent": r.parent_id, "kind": "reminder", "title": "Reminder", "body": r.text,
                "seed": "", "target": r.message_id,
            }
            # Taken only by a tab that can show them.
            for r in (db.due_reminders(me) if seen or self.permission == "granted" else [])
        ]
        if latest <= self._notified_seq and not reminders:
            return
        items = db.notifications_since(me, self._notified_seq, rooms)
        self._notified_seq = latest
        # Do not disturb holds everything back, reminders aside.
        profile = db.load_profiles().get(me)
        if profile and profile.dnd_until > time.time():
            items = []
        items += reminders
        if items:
            return rx.call_script(f"window.relackNotify && window.relackNotify({json.dumps(items)})")
