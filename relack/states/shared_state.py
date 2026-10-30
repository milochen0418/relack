import reflex as rx
import json
import datetime as dt
from relack import db, permissions
from relack.emoji import EMOJI
from relack.formatting import plain_text, resolve_mentions
from relack.models import (
    Attachment,
    CallInfo,
    ChatMessage,
    IncomingCall,
    PermissionConfig,
    RoomInfo,
    UserProfile,
)
from relack.states.permission_state import PermissionState
from relack.states.auth_state import AuthState
from relack.auth.session import get_session, parse_session_id, set_approved_status
from relack.link_preview import fetch_preview, first_url, split_message
from relack.posting import MAX_MESSAGE_CHARS
import datetime
import hashlib
import time
import uuid
from typing import Any

# Room messages an open room keeps in memory (older ones load on request)...
WINDOW = 100
# ...cut back to WINDOW once they pass this.
TRIM_AT = 160
# Threads an open room keeps loaded for whoever has them open.
MAX_OPEN_THREADS = 30
DEFAULT_ROOMS = (
    ("General", "The main hangout spot"),
    ("Tech Talk", "Discussing the latest tech"),
    ("Random", "Anything goes!"),
)


def direct_room_name(user_a: str, user_b: str) -> str:
    """Stable internal room name for the direct message between two users."""
    pair = "\n".join(sorted([user_a, user_b]))
    return "dm-" + hashlib.sha1(pair.encode()).hexdigest()[:12]


def _default_rooms() -> list[RoomInfo]:
    return [RoomInfo(name=name, description=desc, participant_count=0) for name, desc in DEFAULT_ROOMS]


def _room_token(room: RoomInfo) -> str:
    # From the exact name: "Plans" and "plans" are different rooms with different states.
    return "room-" + hashlib.sha1(f"{room.name}\n{room.token_rev}".encode()).hexdigest()[:20]


def _too_long(text: str):
    if len(text) > MAX_MESSAGE_CHARS:
        return rx.toast.error(f"Messages can be up to {MAX_MESSAGE_CHARS:,} characters.")
    return None


async def _is_admin(state: rx.State) -> bool:
    """The passcode holder in this tab, or an admin account."""
    from relack.states.admin_state import AdminState  # noqa: WPS433

    if await (await state.get_state(AdminState)).still_admin():
        return True
    return permissions.is_admin((await state.get_state(AuthState)).user)


class GlobalLobbyState(rx.SharedState):
    """
    Manages the global list of rooms and active user counts.
    All users link to this with a common token 'lobby' to see the directory.

    Rooms, profiles, permissions and approvals are kept in relack.db; this
    state mirrors them for the open tabs.
    """

    _rooms: dict[str, RoomInfo] = {}
    _known_profiles: dict[str, UserProfile] = {}
    _user_locations: dict[str, str] = {}
    _permissions: PermissionConfig = PermissionConfig()
    _approved_users: dict[str, bool] = {}
    # client_token -> username of the viewer, used to hide private rooms.
    _viewer_by_client: dict[str, str] = {}
    # Ongoing calls by room name (see CallState). Always reassigned, never mutated.
    _calls: dict[str, CallInfo] = {}
    # Whether the fields above were loaded from relack.db.
    _db_ready: bool = False
    # Rooms each person has left (they stay under Browse rooms).
    _left: dict[str, list[str]] = {}
    # Bumped on every new message, so open tabs refresh unread counts right away.
    activity: int = 0

    @rx.var
    def visible_room_list(self) -> list[RoomInfo]:
        """Rooms this client's user may see (private rooms filtered out for outsiders)."""
        viewer = self._viewer_by_client.get(self.router.session.client_token, "")
        left = self._left.get(viewer, [])
        return [
            room
            for room in self._rooms.values()
            if room.can_view(viewer) and not room.archived and room.name not in left
        ]

    def _names(self) -> dict[str, str]:
        return {u: (p.nickname or u) for u, p in self._known_profiles.items()}

    def _display_name(self, username: str) -> str:
        profile = self._known_profiles.get(username)
        return (profile.nickname if profile else "") or username

    def _room_title(self, room: RoomInfo, viewer: str) -> str:
        """Room name, or for a direct message the other person's name."""
        return db.room_title(room, viewer, self._names())

    @rx.var
    def room_titles(self) -> dict[str, str]:
        """Display title per room; direct messages show the other person's name."""
        viewer = self._viewer_by_client.get(self.router.session.client_token, "")
        names = self._names()
        return {
            room.name: db.room_title(room, viewer, names)
            for room in self._rooms.values()
            if room.can_view(viewer)
        }

    @rx.var
    def call_counts(self) -> dict[str, int]:
        """People in each ongoing call of a room this client's user can see."""
        viewer = self._viewer_by_client.get(self.router.session.client_token, "")
        return {
            name: len(set(call.members.values()))
            for name, call in self._calls.items()
            if (room := self._rooms.get(name)) is not None and room.can_view(viewer)
        }

    @rx.var
    def incoming_calls(self) -> list[IncomingCall]:
        """Calls ringing for this client.

        Private rooms and direct messages ring all their members; a public room
        rings the people who currently have that room open.
        """
        client_token = self.router.session.client_token
        viewer = self._viewer_by_client.get(client_token, "")
        if not viewer:
            return []
        here = self._user_locations.get(client_token, "")
        ringing = []
        for call in self._calls.values():
            room = self._rooms.get(call.room_name)
            if (
                not call.ringing
                or room is None
                or not room.can_view(viewer)
                or viewer in call.members.values()
                or viewer in call.responded
                or (not room.is_private and here != room.name)
            ):
                continue
            ringing.append(
                IncomingCall(
                    room_name=room.name,
                    title=self._room_title(room, viewer),
                    caller=self._display_name(call.started_by),
                    is_direct=room.is_direct,
                )
            )
        return ringing

    def _load_db(self):
        """Fill this shared state from relack.db (once per state)."""
        if self._db_ready:
            return
        if not db.load_rooms():
            for room in _default_rooms():
                db.save_room(room)
        self._rooms = db.load_rooms()
        self._known_profiles = db.load_profiles()
        self._left = {}
        permissions = db.get_setting("permissions")
        self._permissions = PermissionConfig(**permissions) if permissions else PermissionConfig()
        self._approved_users = dict(db.get_setting("approved_users", {}) or {})
        self._db_ready = True

    def _reload_db(self):
        """After relack.db was replaced (import, clear): drop what this state held."""
        self._rooms = {}
        self._known_profiles = {}
        self._db_ready = False
        self._load_db()

    @rx.event
    async def approve_user(self, email: str):
        if not await _is_admin(self):
            return rx.toast("Admin privileges required.")
        self._set_approved(email, True)
        await self._admin_after_change()
        return rx.toast(f"Approved {email}")

    @rx.event
    async def revoke_user(self, email: str):
        if not await _is_admin(self):
            return rx.toast("Admin privileges required.")
        self._set_approved(email, False)
        # Whatever room they have open moves to a new shared state without them.
        target = self if self._linked_to else await self._link_to("global-lobby")
        tokens = [t for t, user in target._viewer_by_client.items() if user == email]
        for name in {target._user_locations.get(t, "") for t in tokens}:
            if room := db.load_rooms().get(name):
                await self._save_room(room.model_copy(update={"token_rev": room.token_rev + 1}), "room.reseal", email)
        await self._admin_after_change()
        return rx.toast(f"Revoked {email}")

    def _set_approved(self, email: str, approved: bool):
        self._approved_users = {**self._approved_users, email: approved}
        set_approved_status(email, approved)
        if email in self._known_profiles:
            profile = self._known_profiles[email].model_copy(update={"is_approved": approved})
            db.save_profile(profile)
            self._known_profiles = {**self._known_profiles, email: profile}
        db.audit("admin", "user.approve" if approved else "user.revoke", email)

    def is_user_approved(self, email: str) -> bool:
        return self._approved_users.get(email, False)

    @rx.event
    async def join_lobby(self):
        """Connects the user to the global lobby to receive room updates."""
        new_state = await self._link_to("global-lobby")
        new_state._load_db()
        auth = await self.get_state(AuthState)
        if auth.user:
            profile = auth.user.model_copy(
                update={"is_approved": new_state._approved_users.get(auth.user.username, auth.user.is_approved)}
            )
            stored = new_state._known_profiles.get(profile.username)
            if stored is not None:
                # Status, time zone and profile edits live in the stored profile.
                profile = profile.model_copy(update={
                    "status_emoji": stored.status_emoji, "status_text": stored.status_text,
                    "status_until": stored.status_until, "dnd_until": stored.dnd_until,
                    "timezone": stored.timezone, "nickname": stored.nickname or profile.nickname,
                    "bio": stored.bio or profile.bio,
                })
            if stored != profile:
                db.save_profile(profile)
                new_state._known_profiles = {**new_state._known_profiles, profile.username: profile}
            left = sorted(db.left_rooms(profile.username))
            if new_state._left.get(profile.username, []) != left:
                new_state._left = {**new_state._left, profile.username: left}
            # Reassign (not mutate): lobby state pickled before this var existed
            # would otherwise write into the shared class-level default.
            new_state._viewer_by_client = {
                **new_state._viewer_by_client,
                self.router.session.client_token: auth.user.username,
            }
        if not hasattr(new_state, "_user_locations"):
            new_state._user_locations = {}

    @rx.event
    async def create_room(
        self,
        room_name: str,
        description: str,
        is_private: bool = False,
        allowed_members: list[str] | None = None,
    ):
        room_name = (room_name or "").strip()
        if not room_name:
            return rx.toast("Room name required")
        auth = await self.get_state(AuthState)
        if not auth.user:
            return rx.toast("You must be logged in to create a room.")
        if permissions.is_pending(auth.user) or not permissions.can(auth.user, "create_room"):
            return rx.toast("You don't have permission to create rooms.")
        self._load_db()
        if room_name.lower().startswith("dm-"):
            return rx.toast("Room names can't start with dm-.")
        if room_name in self._rooms:
            return rx.toast("Room already exists")
        creator = auth.user.username
        room = RoomInfo(
            name=room_name,
            description=description,
            participant_count=0,
            created_by=creator,
            is_private=is_private,
            allowed_members=(
                list(dict.fromkeys(m for m in allowed_members or [] if m and m != creator))
                if is_private
                else []
            ),
        )
        db.save_room(room)
        db.audit(creator, "room.create", room_name)
        self._rooms = {**self._rooms, room_name: room}
        kind = "Private room" if is_private else "Room"
        return rx.toast(f"{kind} '{room_name}' created!")

    @rx.event
    async def open_direct_message(self, username: str):
        """Open (creating on first use) the direct message room with `username`."""
        auth = await self.get_state(AuthState)
        if not auth.user or permissions.is_pending(auth.user):
            return rx.toast("You must be logged in to send messages.")
        me = auth.user.username
        if not username or username == me:
            return rx.toast("You cannot message yourself.")
        target = self
        if not self._linked_to:
            target = await self._link_to("global-lobby")
        target._load_db()
        room_name = direct_room_name(me, username)
        existing = target._rooms.get(room_name)
        if existing is not None and not (existing.is_direct and existing.can_view(me) and existing.can_view(username)):
            return rx.toast("This direct message can't be opened.")
        if existing is None:
            room = RoomInfo(
                name=room_name,
                description="Direct message",
                created_by=me,
                is_private=True,
                allowed_members=[username],
                is_direct=True,
            )
            db.save_room(room)
            target._rooms = {**target._rooms, room_name: room}
        return [LocalUIState.show_rooms, RoomState.handle_join_room(room_name)]

    @rx.event
    async def open_group_message(self, usernames: list[str]):
        """Open (creating on first use) the direct message among these people and me."""
        auth = await self.get_state(AuthState)
        if not auth.user or permissions.is_pending(auth.user):
            return rx.toast("You must be logged in to send messages.")
        me = auth.user.username
        others = sorted({u for u in usernames if u and u != me})
        if not others:
            return rx.toast("Pick at least one person.")
        if len(others) == 1:
            return GlobalLobbyState.open_direct_message(others[0])
        target = self if self._linked_to else await self._link_to("global-lobby")
        target._load_db()
        room_name = "dm-" + hashlib.sha1("\n".join(sorted([me, *others])).encode()).hexdigest()[:12]
        existing = target._rooms.get(room_name)
        if existing is not None and not (existing.is_direct and existing.can_view(me)):
            return rx.toast("This direct message can't be opened.")
        if existing is None:
            room = RoomInfo(
                name=room_name, description="Group message", created_by=me,
                is_private=True, allowed_members=others, is_direct=True,
            )
            db.save_room(room)
            target._rooms = {**target._rooms, room_name: room}
        return [LocalUIState.show_rooms, RoomState.handle_join_room(room_name)]

    async def _manageable(self, room_name: str) -> RoomInfo | None:
        """The room, if this user may change it (its creator or an admin)."""
        auth = await self.get_state(AuthState)
        room = db.load_rooms().get(room_name)
        if room is None or room.is_direct or not auth.user:
            return None
        return room if room.created_by == auth.user.username or await _is_admin(self) else None

    async def _save_room(self, room: RoomInfo, action: str, detail: str = ""):
        auth = await self.get_state(AuthState)
        db.save_room(room)
        db.audit(auth.user.username if auth.user else "admin", action, room.name, detail)
        target = self if self._linked_to else await self._link_to("global-lobby")
        target._load_db()
        target._rooms = {**target._rooms, room.name: room}

    @rx.event
    async def update_room(self, room_name: str, title: str, description: str):
        room = await self._manageable(room_name)
        title = title.strip()
        if room is None or not title:
            return rx.toast("You can't change this room.")
        taken = any((r.title or r.name) == title and r.name != room_name for r in db.load_rooms().values())
        if taken:
            return rx.toast("Room already exists")
        await self._save_room(room.model_copy(update={"title": title, "description": description}), "room.rename", title)
        return rx.toast("Room updated.")

    @rx.event
    async def set_archived(self, room_name: str, archived: bool):
        room = await self._manageable(room_name)
        if room is None:
            return rx.toast("You can't change this room.")
        await self._save_room(room.model_copy(update={"archived": archived}), "room.archive" if archived else "room.unarchive")
        return rx.toast("Room archived." if archived else "Room restored.")

    @rx.event
    async def add_room_member(self, room_name: str, username: str):
        room = await self._manageable(room_name)
        if room is None or not room.is_private or not username or username in [room.created_by, *room.allowed_members]:
            return
        await self._save_room(room.model_copy(update={"allowed_members": [*room.allowed_members, username]}), "room.member_add", username)

    @rx.event
    async def remove_room_member(self, room_name: str, username: str):
        room = await self._manageable(room_name)
        if room is None or username not in room.allowed_members:
            return
        members = [u for u in room.allowed_members if u != username]
        await self._save_room(
            room.model_copy(update={"allowed_members": members, "token_rev": room.token_rev + 1}),
            "room.member_remove",
            username,
        )

    @rx.event
    async def set_room_left(self, room_name: str, left: bool):
        """Leave a room (it moves to Browse rooms) or come back to it."""
        auth = await self.get_state(AuthState)
        room = db.load_rooms().get(room_name)
        if not auth.user or room is None or room.is_private or not room.can_view(auth.user.username):
            return rx.toast("Private rooms are left by being removed from them.") if left else None
        me = auth.user.username
        db.set_room_pref(me, room_name, left=left)
        target = self if self._linked_to else await self._link_to("global-lobby")
        target._left = {**target._left, me: sorted(db.left_rooms(me))}

    @rx.event
    async def delete_room(self, room_name: str):
        auth = await self.get_state(AuthState)
        if not auth.user:
            return rx.toast("Authentication required.")
        if room_name not in self._rooms:
            return
        room = self._rooms[room_name]
        if room.created_by != auth.user.username and not await _is_admin(self):
            return rx.toast("You can only delete rooms you created.")
        db.delete_room(room_name)
        db.audit(auth.user.username, "room.delete", room_name)
        self._rooms = {name: r for name, r in self._rooms.items() if name != room_name}
        return rx.toast(f"Room '{room_name}' deleted.")

    @rx.event
    async def clear_all_data(self):
        """Resets all shared state data to initial state."""
        auth = await self.get_state(AuthState)
        # Lazy import to avoid circular dependency at module load time.
        from relack.states.admin_state import AdminState  # noqa: WPS433

        admin_state = await self.get_state(AdminState)
        is_admin = bool(admin_state and admin_state.is_authenticated)

        if not await _is_admin(self):
            yield rx.toast("Admin privileges required.")
            return
        db.clear_all()
        db.audit(auth.user.username if auth.user else "admin", "data.clear")
        # Open rooms reload their messages when someone next comes in.
        db.set_setting("data_version", time.time())
        self._reload_db()
        self._calls = {}
        self.activity += 1
        if is_admin:
            await self._admin_after_change()
        yield RoomState.reset_room_state
        yield rx.toast("Database cleared successfully!")
        return

    async def _admin_after_change(self):
        """Refresh the admin's tables after relack.db was replaced."""
        from relack.states.admin_state import AdminState  # noqa: WPS433

        (await self.get_state(AdminState)).load_admin_data()

    @rx.event
    async def export_data(self):
        """Serialize all data to JSON for the admin to copy (in the admin's own tab only)."""
        from relack.states.admin_state import AdminState  # noqa: WPS433

        admin = await self.get_state(AdminState)
        if not admin.is_authenticated:
            return rx.toast("Admin privileges required.")
        admin.export_payload = json.dumps(db.export_all(), indent=2, ensure_ascii=False)
        db.audit("admin", "data.export")
        return rx.toast("Export ready. Copy the JSON below.")

    @rx.event
    async def export_data_to_file(self):
        """Trigger a file download of the current snapshot."""
        if not await _is_admin(self):
            return rx.toast("Admin privileges required.")
        payload = json.dumps(db.export_all(), indent=2, ensure_ascii=False)
        db.audit("admin", "data.export")
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        return rx.download(data=payload, filename=f"relack-{stamp}.json")

    @rx.event
    async def import_data(self, payload: str):
        """Replace all data with a JSON export."""
        if not await _is_admin(self):
            yield rx.toast("Admin privileges required.")
            return
        try:
            data = json.loads(payload)
        except Exception:
            yield rx.toast("Import failed: invalid JSON")
            return

        try:
            db.import_all(data)
        except Exception:
            # Checked before writing: the current data is unchanged.
            yield rx.toast("Import failed: schema mismatch")
            return
        db.set_setting("data_version", time.time())
        db.audit("admin", "data.import")
        target = self if self._linked_to else await self._link_to("global-lobby")
        target._reload_db()
        target.activity += 1
        await self._admin_after_change()

        # Clear active room sessions; admins are not joined to rooms.
        yield RoomState.reset_room_state
        # Sync permission UI to imported snapshot
        permission_state = await self.get_state(PermissionState)
        await permission_state.sync_from_lobby()
        yield rx.toast("Import completed.")

    @rx.event
    async def import_data_from_upload(self, files: list[rx.UploadFile]):
        """Handle file upload (expects a single JSON file)."""

        if not files:
            yield rx.toast("No file provided.")
            return
        try:
            content = await files[0].read()
            payload = content.decode("utf-8")
        except Exception:
            yield rx.toast("Failed to read file.")
            return

        # Reuse import_data flow
        async for action in self.import_data(payload):
            yield action


class TabSessionState(rx.State):
    """Per-tab session storage for the room selection."""

    tab_id: str = rx.SessionStorage("", name="relack_tab_id")
    last_room_name: str = rx.SessionStorage("", name="relack_last_room")
    curr_room_name: str = rx.SessionStorage("", name="relack_curr_room")

    @rx.event
    def reset_tab_session(self):
        self.last_room_name = ""
        self.curr_room_name = ""


class LocalUIState(rx.State):
    """Per-tab UI toggles that should NOT sync across browsers/tabs."""

    is_sidebar_open: bool = True
    is_user_list_open: bool = False
    # Main panel of the dashboard: "rooms" (chat), "people" (member directory),
    # "search", "browse" (all rooms) or "later" (saved and scheduled).
    main_view: str = "rooms"
    # Narrow screen: the sidebar is a drawer, closed once a room is picked.
    is_narrow: bool = False

    @rx.event
    def show_rooms(self):
        self.main_view = "rooms"
        if self.is_narrow:
            self.is_sidebar_open = False

    @rx.event
    def show_later(self):
        self.main_view = "later"

    @rx.event
    def show_browse(self):
        self.main_view = "browse"

    @rx.event
    def show_people(self):
        self.main_view = "people"

    @rx.event
    def show_search(self):
        self.main_view = "search"

    @rx.event
    def toggle_sidebar(self):
        self.is_sidebar_open = not self.is_sidebar_open

    @rx.event
    def toggle_user_list(self):
        self.is_user_list_open = not self.is_user_list_open


class RoomState(rx.SharedState):
    """
    Manages the state of a specific chat room.
    This state will be linked to a specific room token (e.g., 'room-general').

    Messages are stored in relack.db; this keeps the latest WINDOW of them,
    and the threads someone has open, for everyone in the room.
    """

    _active_users: dict[str, str] = {}
    _active_user_profiles: dict[str, UserProfile] = {}
    _active_user_last_seen: dict[str, float] = {}
    _messages: list[ChatMessage] = []
    _current_room_by_client: dict[str, str] = {}
    _room_info_map: dict[str, RoomInfo] = {}
    _known_profiles_snapshot: dict[str, UserProfile] = {}
    # The room these messages are from, and which data they were loaded from
    # (a re-created room or an import/clear makes it reload).
    _room: str = ""
    _loaded_version: str = ""
    # Whether the room has messages before the window ("Load earlier messages").
    window_has_older: bool = False
    # Bumped when the window was cut or a message before it changed: tabs that
    # show older messages load them again.
    history_rev: int = 0
    # Threads someone has open: the root message and its replies, by root id.
    _thread_roots: dict[str, ChatMessage] = {}
    _thread_replies: dict[str, list[ChatMessage]] = {}
    # Who is typing: client token -> (display name, when).
    _typing: dict[str, tuple[str, float]] = {}
    current_message: str = ""
    STALE_WINDOW_SECONDS: int = 10

    @rx.var
    def in_room(self) -> bool:
        client_token = self.router.session.client_token
        return bool(self._current_room_by_client.get(client_token))

    @rx.var
    def room_name(self) -> str:
        client_token = self.router.session.client_token
        return self._current_room_by_client.get(client_token, "")

    @rx.var
    def messages(self) -> list[ChatMessage]:
        return self._messages

    @rx.var
    def thread_roots(self) -> dict[str, ChatMessage]:
        return self._thread_roots

    @rx.var
    def thread_replies(self) -> dict[str, list[ChatMessage]]:
        return self._thread_replies

    @rx.var
    def typing_names(self) -> list[str]:
        """Others typing in this room right now."""
        me = self._typing.get(self.router.session.client_token, ("", 0))[0]
        return sorted({n for token, (n, _t) in self._typing.items() if n != me})

    @rx.var
    def room_archived(self) -> bool:
        info = self._room_info_map.get(self.room_name)
        return bool(info and info.archived)

    @rx.var
    def users(self) -> list[str]:
        return list(self._active_users.values())

    @rx.var
    def online_users_list(self) -> list[UserProfile]:
        # Deduplicate by username and filter out stale sessions.
        now_ts = datetime.datetime.utcnow().timestamp()
        unique: dict[str, UserProfile] = {}
        for token, profile in self._active_user_profiles.items():
            last_seen = self._active_user_last_seen.get(token, 0)
            if now_ts - last_seen > self.STALE_WINDOW_SECONDS:
                continue
            if profile.username not in unique:
                unique[profile.username] = profile
        return list(unique.values())

    @rx.var
    def display_name_map(self) -> dict[str, str]:
        # Map canonical username/email to preferred display nickname.
        mapping: dict[str, str] = {}
        for profile in self._active_user_profiles.values():
            mapping[profile.username] = profile.nickname or profile.username
        return mapping

    @rx.var
    def avatar_seed_map(self) -> dict[str, str]:
        # Use stored avatar seed per user; fall back to username/email if missing.
        mapping: dict[str, str] = {}
        for profile in self._active_user_profiles.values():
            mapping[profile.username] = profile.avatar_seed or profile.username
        return mapping

    @rx.var
    def mention_candidates(self) -> str:
        """People the composer's @ autocomplete offers (JSON: username, name, avatar seed)."""
        info = self._room_info_map.get(self._room)
        if info is None:
            return "[]"
        profiles = self._known_profiles_snapshot
        usernames = (
            list(profiles)
            if not info.is_private
            else [u for u in [info.created_by, *info.allowed_members] if u]
        )
        people = []
        for username in dict.fromkeys(usernames):
            profile = profiles.get(username)
            people.append(
                {
                    "u": username,
                    "n": (profile.nickname if profile else "") or username,
                    "s": (profile.avatar_seed if profile else "") or username,
                }
            )
        return json.dumps(people, ensure_ascii=False)

    @rx.var
    def room_creator_username(self) -> str:
        info = self._room_info_map.get(self.room_name)
        return info.created_by if info else ""

    @rx.var
    def room_is_direct(self) -> bool:
        info = self._room_info_map.get(self.room_name)
        return bool(info and info.is_direct)

    @rx.var
    def room_is_private(self) -> bool:
        info = self._room_info_map.get(self.room_name)
        return bool(info and info.is_private)

    @rx.var
    def room_allowed_members(self) -> list[UserProfile]:
        """People who can see the current private room, creator first."""
        info = self._room_info_map.get(self.room_name)
        if not info or not info.is_private:
            return []
        return [
            self._known_profiles_snapshot.get(username)
            or UserProfile(username=username, is_guest=False, avatar_seed=username)
            for username in [info.created_by, *info.allowed_members]
        ]

    @rx.var
    def room_creator_display(self) -> str:
        username = self.room_creator_username
        if not username:
            return ""
        profile = self._known_profiles_snapshot.get(username)
        if profile and profile.nickname:
            return profile.nickname
        return username

    async def _lobby(self) -> GlobalLobbyState:
        lobby = await self.get_state(GlobalLobbyState)
        if not lobby._linked_to:
            lobby = await lobby._link_to("global-lobby")
        lobby._load_db()
        return lobby

    async def _prune_stale_clients(self, now_ts: float | None = None):
        """Remove clients that have not sent a heartbeat recently."""
        now_val = now_ts or datetime.datetime.utcnow().timestamp()
        stale_tokens = [
            token
            for token, ts in self._active_user_last_seen.items()
            if now_val - ts > self.STALE_WINDOW_SECONDS
        ]
        if not stale_tokens:
            return
        for token in stale_tokens:
            self._active_user_last_seen.pop(token, None)
            self._active_users.pop(token, None)
            self._active_user_profiles.pop(token, None)

    @rx.event
    async def heartbeat(self):
        """Refresh presence for this client and prune stale sessions."""
        client_token = self.router.session.client_token
        tab_state = await self.get_state(TabSessionState)
        if not tab_state.tab_id:
            tab_state.tab_id = str(uuid.uuid4())
        tab_id = tab_state.tab_id

        lobby = await self._lobby()

        try:
            session_id = parse_session_id(self.router.headers.cookie)
            if session_id and not get_session(session_id):
                self._active_users.pop(tab_id, None)
                self._active_user_profiles.pop(tab_id, None)
                self._active_user_last_seen.pop(tab_id, None)
                self._current_room_by_client.pop(client_token, None)
                if hasattr(lobby, "_user_locations"):
                    lobby._user_locations.pop(client_token, None)
                return
        except Exception:
            pass

        # Only on change: every write here goes out to the whole room.
        if self._room_info_map != lobby._rooms:
            self._room_info_map = dict(lobby._rooms)
        if self._known_profiles_snapshot != lobby._known_profiles:
            self._known_profiles_snapshot = dict(lobby._known_profiles)

        now_ts = datetime.datetime.utcnow().timestamp()
        await self._prune_stale_clients(now_ts)

        if not self.room_name:
            tab_state.curr_room_name = ""
            return
        auth = await self.get_state(AuthState)
        info = lobby._rooms.get(self.room_name)
        if (
            info is None
            or not auth.user
            or not info.can_view(auth.user.username)
            or permissions.is_pending(auth.user)
        ):
            # Removed from the room, revoked, or the room is gone.
            await self._internal_leave_room(clear_tab_state=True)
            return
        if self._linked_to and self._linked_to != _room_token(info):
            # Someone was shut out: everyone else follows to the room's new shared state.
            name = self.room_name
            await self._internal_leave_room(clear_tab_state=False)
            return RoomState.handle_join_room(name)
        self._catch_up()
        if self._typing and any(now_ts - t > 6 for _n, t in self._typing.values()):
            self._typing = {k: v for k, v in self._typing.items() if now_ts - v[1] <= 6}
        self._active_user_last_seen[tab_id] = now_ts

        # Self-healing: if this tab is in a room but missing from presence, re-add
        if tab_id not in self._active_users:
            auth = await self.get_state(AuthState)
            if auth.user:
                self._active_users[tab_id] = auth.user.username
                self._active_user_profiles[tab_id] = auth.user

    @rx.event
    async def on_disconnect(self):
        """Cleanup presence when the client disconnects (e.g., tab closed)."""
        client_token = self.router.session.client_token

        # 1. Try to identify room from local context
        room_name = self.room_name

        # 2. If not found locally, check global registry
        lobby = await self.get_state(GlobalLobbyState)
        if not lobby._linked_to:
            lobby = await lobby._link_to("global-lobby")

        if not room_name and hasattr(lobby, "_user_locations"):
            room_name = lobby._user_locations.get(client_token, "")

        # 3. Clean up global registry
        if hasattr(lobby, "_user_locations"):
            lobby._user_locations.pop(client_token, None)

        if not room_name:
            return

        # 4. Link to the correct room state instance and remove user
        room_info = db.load_rooms().get(room_name)
        if room_info is None:
            return
        target_state = await self._link_to(_room_token(room_info))

        tab_state = await self.get_state(TabSessionState)
        tab_id = tab_state.tab_id
        if tab_id:
            target_state._active_user_last_seen.pop(tab_id, None)
            target_state._active_users.pop(tab_id, None)
            target_state._active_user_profiles.pop(tab_id, None)
        target_state._current_room_by_client.pop(client_token, None)
        tab_state.curr_room_name = ""

    @rx.event
    async def rejoin_last_room(self):
        """Rejoin the last room stored locally, if not already in a room."""
        tab_state = await self.get_state(TabSessionState)
        if self.room_name or not tab_state.last_room_name:
            return
        auth = await self.get_state(AuthState)
        if not auth.user:
            return
        yield RoomState.handle_join_room(tab_state.last_room_name)

    @rx.event
    async def reset_room_state(self):
        """Clears local room state during a global reset."""
        if not await _is_admin(self):
            return
        self._active_users = {}
        self._active_user_profiles = {}
        self._messages = []
        self._current_room_by_client = {}
        self._room_info_map = {}
        self._known_profiles_snapshot = {}
        self._room = ""
        self._loaded_version = ""
        self._thread_roots = {}
        self._thread_replies = {}
        self.window_has_older = False
        self.current_message = ""
        tab_state = await self.get_state(TabSessionState)
        tab_state.reset_tab_session()

    @rx.event
    async def handle_join_room(self, room_name: str):
        from relack.states.chat_state import ChatUIState  # noqa: WPS433

        auth = await self.get_state(AuthState)
        if not auth.user or permissions.is_pending(auth.user):
            return rx.toast("Please log in to join rooms")

        lobby = await self._lobby()
        room_info = lobby._rooms.get(room_name)
        if room_info is None or not room_info.can_view(auth.user.username):
            tab_state = await self.get_state(TabSessionState)
            if tab_state.last_room_name == room_name:
                tab_state.last_room_name = ""
            return rx.toast("This room is private.") if room_info else None

        # Optimization: If already in this room, just mark as read/refresh and return
        # This prevents unnecessary unlink/link cycles which can cause UI state flicker or "No room selected"
        if self.room_name == room_name:
            db.mark_read(auth.user.username, room_name)
            await self.heartbeat()
            return

        # Set curr_room_name immediately to prevent UI unselect during re-join
        tab_state = await self.get_state(TabSessionState)
        tab_state.curr_room_name = room_name
        if self.room_name:
            await self._internal_leave_room(clear_tab_state=False)
        ui = await self.get_state(ChatUIState)
        ui.reset_room()
        new_room_state = await self._link_to(_room_token(room_info))
        client_token = self.router.session.client_token
        new_room_state._current_room_by_client[client_token] = room_name
        tab_state.last_room_name = room_name

        # Update global user location tracking
        if not hasattr(lobby, "_user_locations"):
            lobby._user_locations = {}
        lobby._user_locations[client_token] = room_name

        version = self._data_key(room_name)
        if (
            new_room_state._room != room_name
            or new_room_state._loaded_version != version
            or not new_room_state._messages
        ):
            new_room_state._room = room_name
            new_room_state._loaded_version = version
            new_room_state._thread_roots = {}
            new_room_state._thread_replies = {}
            new_room_state._set_window(db.room_messages(room_name, WINDOW))
        new_room_state._room_info_map = dict(lobby._rooms)
        new_room_state._known_profiles_snapshot = dict(lobby._known_profiles)

        username = auth.user.username
        if not tab_state.tab_id:
            tab_state.tab_id = str(uuid.uuid4())
        tab_id = tab_state.tab_id
        new_room_state._active_users[tab_id] = username
        new_room_state._active_user_profiles[tab_id] = auth.user
        new_room_state._active_user_last_seen[tab_id] = datetime.datetime.utcnow().timestamp()

        # Refresh presence after linking.
        await new_room_state.heartbeat()

        db.mark_read(username, room_name)

    async def _internal_leave_room(self, clear_tab_state: bool):
        client_token = self.router.session.client_token
        current_room = self._current_room_by_client.get(client_token, "")

        # Always clean up global location tracking
        lobby = await self.get_state(GlobalLobbyState)
        if not lobby._linked_to:
            lobby = await lobby._link_to("global-lobby")
        if hasattr(lobby, "_user_locations"):
            lobby._user_locations.pop(client_token, None)

        if not current_room:
            return

        tab_state = await self.get_state(TabSessionState)
        tab_id = tab_state.tab_id
        if tab_id:
            self._active_users.pop(tab_id, None)
            self._active_user_profiles.pop(tab_id, None)
            self._active_user_last_seen.pop(tab_id, None)
        self._current_room_by_client.pop(client_token, None)
        if clear_tab_state:
            tab_state.curr_room_name = ""
        if self._linked_to:
            await self._unlink()

    @rx.event
    async def handle_leave_room(self):
        await self._internal_leave_room(clear_tab_state=True)

    async def _post(
        self, user: UserProfile, text: str, files: list[Attachment], parent_id: str = ""
    ) -> ChatMessage | None:
        """Store a message from `user` in this room and tell everyone's tabs."""
        room = self.room_name
        room_info = db.load_rooms().get(room)
        if (
            room_info is None
            or room_info.archived
            or not room_info.can_view(user.username)
            or permissions.is_pending(user)
        ):
            return None
        content, mentions = resolve_mentions(text, self._mentionable(user, room_info))
        plain = plain_text(content, db.display_names())
        url = first_url(split_message(plain))
        preview = await fetch_preview(url) if url else None
        msg_id, seq = db.insert_message(
            room=room,
            sender=user.username,
            display_name=user.nickname or user.username,
            content=content,
            plain=plain,
            mentions=mentions,
            preview=preview,
            parent_id=parent_id,
            file_ids=[f.id for f in files],
        )
        db.mark_read(user.username, room, seq)
        lobby = await self._lobby()
        lobby.activity += 1
        return db.get_message(msg_id)

    @staticmethod
    def _data_key(room_name: str) -> str:
        return f"{db.get_setting('data_version', 0.0)}:{db.room_created_at(room_name)}"

    def _catch_up(self):
        """Take in messages stored without going through this state (bots, scheduled posts)."""
        if not self._room:
            return
        if self._loaded_version != self._data_key(self._room):
            # Imported, cleared, or retention removed messages.
            self._loaded_version = self._data_key(self._room)
            self._thread_roots = {}
            self._thread_replies = {}
            self._set_window(db.room_messages(self._room, WINDOW))
            return
        last = self._messages[-1].seq if self._messages else 0
        if db.max_root_seq(self._room) > last:
            messages = [*self._messages, *db.messages_after(self._room, last)]
            if len(messages) > TRIM_AT:
                self._set_window(messages[-WINDOW:])
            else:
                self._messages = messages

    async def mark_typing(self):
        auth = await self.get_state(AuthState)
        if auth.user and self.room_name:
            token = self.router.session.client_token
            name = auth.user.nickname or auth.user.username
            self._typing = {**self._typing, token: (name, datetime.datetime.utcnow().timestamp())}

    def _set_window(self, messages: list[ChatMessage]):
        """The room messages everyone in the room sees (older ones load per tab)."""
        self._messages = messages
        self.window_has_older = bool(messages) and db.has_older(self._room, messages[0].seq)
        self.history_rev += 1

    def _in_window(self, msg_id: str) -> bool:
        return any(m.id == msg_id for m in self._messages)

    @staticmethod
    def _mentionable(user: UserProfile, room_info: RoomInfo | None) -> dict[str, str]:
        """Who `user` can @mention in the room (nobody without that permission)."""
        if room_info is None or not permissions.can(user, "mention_users"):
            return {}
        return db.room_people(room_info)

    def _replace_message(self, msg: ChatMessage):
        """Show the new version of a message wherever this room has it."""
        if self._in_window(msg.id):
            self._messages = [msg if m.id == msg.id else m for m in self._messages]
        elif not msg.parent_id:
            # Older than the window: tabs showing it load it again.
            self.history_rev += 1
        if msg.id in self._thread_roots:
            self._thread_roots = {**self._thread_roots, msg.id: msg}
        if msg.parent_id in self._thread_replies:
            self._thread_replies = {
                **self._thread_replies,
                msg.parent_id: [msg if r.id == msg.id else r for r in self._thread_replies[msg.parent_id]],
            }

    def _drop_messages(self, ids: list[str]):
        gone = set(ids)
        if any(not self._in_window(i) for i in gone):
            self.history_rev += 1
        self._messages = [m for m in self._messages if m.id not in gone]
        self._thread_roots = {k: v for k, v in self._thread_roots.items() if k not in gone}
        self._thread_replies = {
            root: [r for r in replies if r.id not in gone]
            for root, replies in self._thread_replies.items()
            if root not in gone
        }

    def _read_only(self) -> bool:
        info = db.load_rooms().get(self.room_name)
        return info is None or info.archived

    async def _my_message(self, msg_id: str) -> tuple[UserProfile, Any] | None:
        """The logged-in user and the row of their own message in this room."""
        auth = await self.get_state(AuthState)
        row = db.message_row(msg_id)
        if not auth.user or row is None or row["room"] != self.room_name:
            return None
        if row["sender"] != auth.user.username:
            return None
        return auth.user, row

    @rx.event
    async def send_message(self, form_data: dict[str, Any]):
        from relack.states.chat_state import ComposerState  # noqa: WPS433

        message_text = (form_data.get("message") or "").strip()
        if too_long := _too_long(message_text):
            return too_long
        composer = await self.get_state(ComposerState)
        files = list(composer.pending)
        if not message_text and not files:
            return
        auth = await self.get_state(AuthState)
        if not auth.user or not self.room_name or permissions.is_pending(auth.user):
            return
        self._typing = {k: v for k, v in self._typing.items() if k != self.router.session.client_token}
        if message_text.startswith("/") and not files:
            from relack.commands import run_command  # noqa: WPS433

            result = await run_command(self, auth.user, message_text)
            if result is not None:
                handled, message_text = result
                if handled:
                    return handled
                if not message_text:
                    return
        composer.pending = []
        msg = await self._post(auth.user, message_text, files)
        if msg is None:
            return rx.toast("This room is read-only.")
        # Through the database, so a webhook's post just before this one isn't skipped.
        self._catch_up()
        self.current_message = ""

    @rx.event
    async def send_reply(self, form_data: dict[str, Any]):
        """Reply in the thread open in this tab."""
        from relack.states.chat_state import ChatUIState, ComposerState  # noqa: WPS433

        ui = await self.get_state(ChatUIState)
        root_id = form_data.get("root_id") or ui.thread_id
        message_text = (form_data.get("message") or "").strip()
        if too_long := _too_long(message_text):
            return too_long
        composer = await self.get_state(ComposerState)
        files = list(composer.pending_thread)
        if not root_id or (not message_text and not files):
            return
        auth = await self.get_state(AuthState)
        root = db.message_row(root_id)
        if not auth.user or root is None or root["room"] != self.room_name or root["parent_id"]:
            return
        composer.pending_thread = []
        msg = await self._post(auth.user, message_text, files, parent_id=root_id)
        if msg is None:
            return
        replies = self._thread_replies.get(root_id)
        self._thread_replies = {
            **self._thread_replies,
            root_id: [*replies, msg] if replies is not None else db.thread_replies(root_id),
        }
        root_msg = db.get_message(root_id)
        if root_msg is not None:
            self._thread_roots = {**self._thread_roots, root_id: root_msg}
            self._replace_message(root_msg)
            ui.replace_older(root_msg)

    @rx.event
    async def open_thread(self, root_id: str):
        from relack.states.chat_state import ChatUIState  # noqa: WPS433

        root = db.get_message(root_id)
        if root is None or root.room != self.room_name or root.parent_id:
            return
        roots = {k: v for k, v in self._thread_roots.items() if k != root_id}
        replies = {k: v for k, v in self._thread_replies.items() if k != root_id}
        # Keep the most recently opened threads.
        keep = list(roots)[-(MAX_OPEN_THREADS - 1):]
        self._thread_roots = {**{k: roots[k] for k in keep}, root_id: root}
        self._thread_replies = {
            **{k: replies[k] for k in keep if k in replies},
            root_id: db.thread_replies(root_id),
        }
        ui = await self.get_state(ChatUIState)
        ui.thread_id = root_id
        ui.editing_id = ""

    @rx.event
    async def toggle_pin(self, msg_id: str):
        auth = await self.get_state(AuthState)
        row = db.message_row(msg_id)
        if not auth.user or row is None or row["room"] != self.room_name or row["deleted"] or self._read_only():
            return
        db.toggle_pin(self.room_name, msg_id, auth.user.username)
        msg = db.get_message(msg_id)
        if msg is not None:
            self._replace_message(msg)

    @rx.event
    async def toggle_reaction(self, msg_id: str, emoji: str):
        from relack.states.chat_state import ChatUIState  # noqa: WPS433

        auth = await self.get_state(AuthState)
        row = db.message_row(msg_id)
        if not auth.user or row is None or row["room"] != self.room_name or row["deleted"] or emoji not in EMOJI or self._read_only():
            return
        db.toggle_reaction(msg_id, emoji, auth.user.username)
        msg = db.get_message(msg_id)
        if msg is not None:
            self._replace_message(msg)
            ui = await self.get_state(ChatUIState)
            ui.replace_older(msg)

    @rx.event
    async def save_edit(self, form_data: dict[str, Any]):
        from relack.states.chat_state import ChatUIState  # noqa: WPS433

        ui = await self.get_state(ChatUIState)
        msg_id = form_data.get("id") or ui.editing_id
        text = (form_data.get("message") or "").strip()
        if too_long := _too_long(text):
            return too_long
        found = await self._my_message(msg_id)
        ui.editing_id = ""
        if found is None or found[1]["deleted"] or self._read_only():
            return
        user, row = found
        if not text:
            # Saving an empty message deletes it, as in Slack.
            ui.deleting_id = msg_id
            return
        room_info = db.load_rooms().get(self.room_name)
        content, mentions = resolve_mentions(text, self._mentionable(user, room_info))
        if content == row["content"]:
            return
        plain = plain_text(content, db.display_names())
        url = first_url(split_message(plain))
        old_preview = json.loads(row["preview"] or "{}")
        preview = old_preview if old_preview.get("url") == url else (await fetch_preview(url) if url else None)
        db.update_message_text(msg_id, content, plain, mentions, preview)
        msg = db.get_message(msg_id)
        if msg is not None:
            self._replace_message(msg)
            ui.replace_older(msg)

    @rx.event
    async def delete_message(self, msg_id: str):
        from relack.states.chat_state import ChatUIState  # noqa: WPS433

        found = await self._my_message(msg_id)
        row = found[1] if found else db.message_row(msg_id)
        if row is None or row["room"] != self.room_name or (found is None and not await _is_admin(self)):
            return rx.toast("You can only delete your own messages.")
        if self._read_only():
            return rx.toast("This room is read-only.")
        if found is None:
            db.audit("admin", "message.delete", self.room_name, row["plain"])
        removed = db.delete_message(msg_id)
        ui = await self.get_state(ChatUIState)
        self._drop_messages(removed)
        ui.remove_older(removed)
        if ui.thread_id in removed:
            ui.thread_id = ""
        for changed in [msg_id if msg_id not in removed else "", row["parent_id"]]:
            if changed and changed not in removed and (msg := db.get_message(changed)) is not None:
                self._replace_message(msg)
                ui.replace_older(msg)
