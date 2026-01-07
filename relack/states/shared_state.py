import reflex as rx
import json
import datetime as dt
from relack.models import RoomInfo, ChatMessage, UserProfile, ChatMessageLog, PermissionConfig
from relack.states.permission_state import PermissionState
from relack.states.auth_state import AuthState
import datetime
import uuid
import logging
from typing import Any


class GlobalLobbyState(rx.SharedState):
    """
    Manages the global list of rooms and active user counts.
    All users link to this with a common token 'lobby' to see the directory.
    """

    _rooms: dict[str, RoomInfo] = {}
    _known_profiles: dict[str, UserProfile] = {}
    _user_locations: dict[str, str] = {}
    _messages_by_room: dict[str, list[ChatMessage]] = {}
    _permissions: PermissionConfig = PermissionConfig()
    export_payload: str = ""
    import_payload: str = ""

    @rx.var
    def room_list(self) -> list[RoomInfo]:
        return list(self._rooms.values())

    @rx.var
    def all_profiles(self) -> list[UserProfile]:
        return list(self._known_profiles.values())

    @rx.var
    def recent_message_logs(self) -> list[ChatMessageLog]:
        """Flatten recent messages for admin viewing (capped per room)."""

        logs: list[ChatMessageLog] = []
        for room_name, messages in self._messages_by_room.items():
            for msg in messages:
                logs.append(ChatMessageLog(room_name=room_name, message=msg))
        # Keep the most recent 200 entries overall to avoid huge tables
        return logs[-200:]

    @rx.var
    def has_export_payload(self) -> bool:
        return bool(self.export_payload)

    @rx.event
    async def join_lobby(self):
        """Connects the user to the global lobby to receive room updates."""
        new_state = await self._link_to("global-lobby")
        auth = await self.get_state(AuthState)
        if auth.user:
            new_state._known_profiles[auth.user.username] = auth.user
        if not hasattr(new_state, "_user_locations"):
            new_state._user_locations = {}
        if not new_state._rooms:
            new_state._rooms = {
                "General": RoomInfo(
                    name="General",
                    description="The main hangout spot",
                    participant_count=0,
                ),
                "Tech Talk": RoomInfo(
                    name="Tech Talk",
                    description="Discussing the latest tech",
                    participant_count=0,
                ),
                "Random": RoomInfo(
                    name="Random", description="Anything goes!", participant_count=0
                ),
            }
        if not new_state._messages_by_room:
            new_state._messages_by_room = {}
        if not new_state._permissions:
            new_state._permissions = PermissionConfig()
        if not new_state.export_payload:
            new_state.export_payload = ""
        if not new_state.import_payload:
            new_state.import_payload = ""

    @rx.event
    async def create_room(self, room_name: str, description: str):
        if not room_name:
            return rx.toast("Room name required")
        auth = await self.get_state(AuthState)
        if not auth.user:
            return rx.toast("You must be logged in to create a room.")
        if room_name in self._rooms:
            return rx.toast("Room already exists")
        self._rooms[room_name] = RoomInfo(
            name=room_name,
            description=description,
            participant_count=0,
            created_by=auth.user.username,
        )
        return rx.toast(f"Room '{room_name}' created!")

    @rx.event
    async def delete_room(self, room_name: str):
        auth = await self.get_state(AuthState)
        if not auth.user:
            return rx.toast("Authentication required.")
        if room_name not in self._rooms:
            return
        room = self._rooms[room_name]
        if room.created_by != auth.user.username:
            return rx.toast("You can only delete rooms you created.")
        del self._rooms[room_name]
        return rx.toast(f"Room '{room_name}' deleted.")

    @rx.event
    async def record_message(self, room_name: str, message: ChatMessage):
        """Store a message snapshot for admin view; keeps last 200 per room."""

        target = self
        if not self._linked_to:
            target = await self._link_to("global-lobby")

        room_msgs = target._messages_by_room.setdefault(room_name, [])
        room_msgs.append(message)
        # Cap per-room history to avoid unbounded growth
        if len(room_msgs) > 200:
            room_msgs[:] = room_msgs[-200:]

    @rx.event
    async def clear_all_data(self):
        """Resets all shared state data to initial state."""
        auth = await self.get_state(AuthState)
        # Lazy import to avoid circular dependency at module load time.
        from relack.states.admin_state import AdminState  # noqa: WPS433

        admin_state = await self.get_state(AdminState)
        is_admin = bool(admin_state and admin_state.is_authenticated)

        if not is_admin and (not auth.user or auth.user.is_guest):
            yield rx.toast("Admin privileges required.")
            return
        self._rooms = {
            "General": RoomInfo(
                name="General", description="The main hangout spot", participant_count=0
            ),
            "Tech Talk": RoomInfo(
                name="Tech Talk",
                description="Discussing the latest tech",
                participant_count=0,
            ),
            "Random": RoomInfo(
                name="Random", description="Anything goes!", participant_count=0
            ),
        }
        self._known_profiles = {}
        self._messages_by_room = {}
        self._permissions = PermissionConfig()
        room_state = await self.get_state(RoomState)
        yield RoomState.reset_room_state
        yield rx.toast("Database cleared successfully!")
        return

    def _snapshot(self) -> dict[str, Any]:
        """Return current lobby snapshot for export."""

        return {
            "rooms": [room.dict() for room in self._rooms.values()],
            "profiles": [profile.dict() for profile in self._known_profiles.values()],
            "messages_by_room": {
                room: [msg.dict() for msg in msgs] for room, msgs in self._messages_by_room.items()
            },
            "permissions": self._permissions.dict(),
        }

    @rx.event
    async def export_data(self):
        """Serialize lobby data to JSON for admin download/copy."""

        target = self
        if not self._linked_to:
            target = await self._link_to("global-lobby")
        snapshot = target._snapshot()
        target.export_payload = json.dumps(snapshot, indent=2)
        return rx.toast("Export ready. Copy the JSON below.")

    @rx.event
    async def export_data_to_file(self):
        """Trigger a file download of the current snapshot."""

        target = self
        if not self._linked_to:
            target = await self._link_to("global-lobby")
        snapshot = target._snapshot()
        payload = json.dumps(snapshot, indent=2)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"relack-{stamp}.json"
        # Set export_payload as well for UI visibility
        target.export_payload = payload
        return rx.download(data=payload, filename=filename)

    @rx.event
    def set_import_payload(self, value: str):
        self.import_payload = value

    @rx.event
    async def import_data(self, payload: str):
        """Restore lobby data from JSON payload."""

        try:
            data = json.loads(payload)
        except Exception:
            yield rx.toast("Import failed: invalid JSON")
            return

        rooms_raw = data.get("rooms", [])
        profiles_raw = data.get("profiles", [])
        messages_raw = data.get("messages_by_room", {})
        permissions_raw = data.get("permissions")

        try:
            self._rooms = {room["name"]: RoomInfo(**room) for room in rooms_raw}
            self._known_profiles = {
                profile["username"]: UserProfile(**profile) for profile in profiles_raw
            }
            reconstructed: dict[str, list[ChatMessage]] = {}
            for room_name, msgs in messages_raw.items():
                reconstructed[room_name] = [ChatMessage(**msg) for msg in msgs]
            self._messages_by_room = reconstructed
            if permissions_raw:
                self._permissions = PermissionConfig(**permissions_raw)
            else:
                self._permissions = PermissionConfig()
        except Exception:
            yield rx.toast("Import failed: schema mismatch")
            return

        # Clear active room sessions; admins are not joined to rooms.
        room_state = await self.get_state(RoomState)
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
    """Per-tab session storage for room counts and selection."""

    all_room_counts_json: str = rx.SessionStorage("{}", name="relack_all_room_count")
    all_room_read_counts_json: str = rx.SessionStorage("{}", name="relack_all_room_read_count")
    last_room_name: str = rx.SessionStorage("", name="relack_last_room")
    curr_room_name: str = rx.SessionStorage("", name="relack_curr_room")

    @rx.var
    def unread_counts(self) -> dict[str, int]:
        try:
            total_counts = json.loads(self.all_room_counts_json or "{}")
            read_counts = json.loads(self.all_room_read_counts_json or "{}")
        except Exception:
            return {}

        diff = {}
        for room, count in total_counts.items():
            read = read_counts.get(room, 0)
            val = count - read
            if val > 0:
                diff[room] = val
        return diff

    @rx.event
    def reset_tab_session(self):
        self.all_room_counts_json = "{}"
        self.all_room_read_counts_json = "{}"
        self.last_room_name = ""
        self.curr_room_name = ""

    @rx.event
    def seed_read_counts(self, message_counts: dict[str, int]):
        try:
            read_counts = json.loads(self.all_room_read_counts_json or "{}")
        except Exception:
            read_counts = {}
        if read_counts:
            return
        safe_counts = message_counts or {}
        updated = False
        for room_name, total in safe_counts.items():
            prior = read_counts.get(room_name, 0)
            if total > prior:
                read_counts[room_name] = total
                updated = True
        if updated:
            self.all_room_read_counts_json = json.dumps(read_counts)

    @rx.event
    def mark_room_read(self, room_name: str, current_total: int):
        try:
            read_counts = json.loads(self.all_room_read_counts_json or "{}")
        except Exception:
            read_counts = {}
        existing = read_counts.get(room_name, 0)
        if current_total > existing:
            read_counts[room_name] = current_total
            self.all_room_read_counts_json = json.dumps(read_counts)


class RoomState(rx.SharedState):
    """
    Manages the state of a specific chat room.
    This state will be linked to a specific room token (e.g., 'room-general').
    """

    _active_users: dict[str, str] = {}
    _active_user_profiles: dict[str, UserProfile] = {}
    _active_user_last_seen: dict[str, float] = {}
    _messages: list[ChatMessage] = []
    _current_room_by_client: dict[str, str] = {}
    _message_counts_by_room: dict[str, int] = {}
    _room_creator_map: dict[str, str] = {}
    _known_profiles_snapshot: dict[str, UserProfile] = {}
    current_message: str = ""
    is_sidebar_open: bool = True
    is_user_list_open: bool = False
    STALE_WINDOW_SECONDS: int = 180

    @rx.event
    def toggle_sidebar(self):
        self.is_sidebar_open = not self.is_sidebar_open

    @rx.event
    def toggle_user_list(self):
        self.is_user_list_open = not self.is_user_list_open

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
    def users(self) -> list[str]:
        return list(self._active_users.values())

    @rx.var
    def online_users_list(self) -> list[UserProfile]:
        # Deduplicate by username and filter out stale sessions.
        now_ts = datetime.datetime.utcnow().timestamp()
        unique: dict[str, UserProfile] = {}
        for token, profile in self._active_user_profiles.items():
            last_seen = self._active_user_last_seen.get(token, now_ts)
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
    def room_creator_username(self) -> str:
        return self._room_creator_map.get(self.room_name, "")

    @rx.var
    def room_creator_display(self) -> str:
        username = self.room_creator_username
        if not username:
            return ""
        profile = self._known_profiles_snapshot.get(username)
        if profile and profile.nickname:
            return profile.nickname
        return username

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
        """Refresh presence for this client, sync message counts, and prune stale sessions."""
        # Sync per-room message counts from lobby snapshot so unread badges stay current even when not in that room.
        lobby = await self.get_state(GlobalLobbyState)
        if not lobby._linked_to:
            lobby = await lobby._link_to("global-lobby")
        self._message_counts_by_room = {room: len(msgs) for room, msgs in lobby._messages_by_room.items()}
        self._room_creator_map = {room: info.created_by for room, info in lobby._rooms.items()}
        self._known_profiles_snapshot = dict(lobby._known_profiles)
        tab_state = await self.get_state(TabSessionState)
        tab_state.all_room_counts_json = json.dumps(self._message_counts_by_room)

        # Always prune stale clients to keep online status accurate
        now_ts = datetime.datetime.utcnow().timestamp()
        await self._prune_stale_clients(now_ts)

        # Presence refresh only if currently in a room.
        if not self.room_name:
            tab_state.curr_room_name = ""
            return
        client_token = self.router.session.client_token
        self._active_user_last_seen[client_token] = now_ts

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
        safe_token = f"room-{room_name.replace(' ', '-').replace('_', '-').lower()}"
        target_state = await self._link_to(safe_token)
        
        target_state._active_user_last_seen.pop(client_token, None)
        target_state._active_users.pop(client_token, None)
        target_state._active_user_profiles.pop(client_token, None)
        target_state._current_room_by_client.pop(client_token, None)
        
        tab_state = await self.get_state(TabSessionState)
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
        self._active_users = {}
        self._active_user_profiles = {}
        self._messages = []
        self._current_room_by_client = {}
        self._message_counts_by_room = {}
        self._room_creator_map = {}
        self._known_profiles_snapshot = {}
        self.current_message = ""
        tab_state = await self.get_state(TabSessionState)
        tab_state.reset_tab_session()

    @rx.event
    async def handle_join_room(self, room_name: str):
        auth = await self.get_state(AuthState)
        if not auth.user:
            return rx.toast("Please log in to join rooms")
            
        # Optimization: If already in this room, just mark as read/refresh and return
        # This prevents unnecessary unlink/link cycles which can cause UI state flicker or "No room selected"
        if self.room_name == room_name:
            await self.mark_room_read_to_current(room_name)
            await self.heartbeat()
            return

        # Set curr_room_name immediately to prevent UI unselect during re-join
        tab_state = await self.get_state(TabSessionState)
        tab_state.curr_room_name = room_name
        if self.room_name:
            await self._internal_leave_room(clear_tab_state=False)
        safe_token = f"room-{room_name.replace(' ', '-').replace('_', '-').lower()}"
        new_room_state = await self._link_to(safe_token)
        client_token = self.router.session.client_token
        new_room_state._current_room_by_client[client_token] = room_name
        tab_state.last_room_name = room_name
        # Load existing history for this room from lobby snapshot (if any)
        lobby = await self.get_state(GlobalLobbyState)
        if not lobby._linked_to:
            lobby_linked = await lobby._link_to("global-lobby")
        else:
            lobby_linked = lobby

        # Update global user location tracking
        if not hasattr(lobby_linked, "_user_locations"):
            lobby_linked._user_locations = {}
        lobby_linked._user_locations[client_token] = room_name

        prior_msgs = lobby_linked._messages_by_room.get(room_name, [])
        new_room_state._messages = list(prior_msgs)
        new_room_state._message_counts_by_room = {
            room: len(msgs) for room, msgs in lobby_linked._messages_by_room.items()
        }
        new_room_state._room_creator_map = {room: info.created_by for room, info in lobby_linked._rooms.items()}
        new_room_state._known_profiles_snapshot = dict(lobby_linked._known_profiles)
        tab_state.all_room_counts_json = json.dumps(new_room_state._message_counts_by_room)

        username = auth.user.username
        new_room_state._active_users[client_token] = username
        new_room_state._active_user_profiles[client_token] = auth.user
        new_room_state._active_user_last_seen[client_token] = datetime.datetime.utcnow().timestamp()

        # Refresh counts/presence after linking to ensure unread map is up to date immediately.
        await new_room_state.heartbeat()

        # Mark only this room as read at its current total.
        await new_room_state.mark_room_read_to_current(room_name)

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
            
        if client_token in self._active_users:
            del self._active_users[client_token]
        if client_token in self._active_user_profiles:
            del self._active_user_profiles[client_token]
        if client_token in self._active_user_last_seen:
            del self._active_user_last_seen[client_token]
        self._current_room_by_client.pop(client_token, None)
        tab_state = await self.get_state(TabSessionState)
        if clear_tab_state:
            tab_state.curr_room_name = ""
        # Only unlink if this state instance is actually linked; avoids runtime errors on logout
        # when session storage still has a room name but no active room link.
        if self._linked_to:
            await self._unlink()

    @rx.event
    async def handle_leave_room(self):
        await self._internal_leave_room(clear_tab_state=True)

    @rx.event
    async def send_message(self, form_data: dict[str, Any]):
        message_text = form_data.get("message", "").strip()
        if not message_text:
            return
        client_token = self.router.session.client_token
        sender = self._active_users.get(client_token, "Unknown")
        profile = self._active_user_profiles.get(client_token)
        display_name = sender
        if profile:
            display_name = profile.nickname or profile.username

        msg = ChatMessage(
            id=str(uuid.uuid4()),
            sender=sender,
            display_name=display_name,
            content=message_text,
            timestamp=datetime.datetime.now().strftime("%H:%M"),
            is_system=False,
        )
        self._messages.append(msg)
        self._message_counts_by_room[self.room_name] = len(self._messages)
        tab_state = await self.get_state(TabSessionState)
        tab_state.all_room_counts_json = json.dumps(self._message_counts_by_room)
        lobby = await self.get_state(GlobalLobbyState)
        await lobby.record_message(self.room_name, msg)
        self.current_message = ""

    @rx.event
    async def seed_all_room_read_counts(self):
        """Initialize read counts to current totals (used on initial dashboard entry)."""
        tab_state = await self.get_state(TabSessionState)
        tab_state.seed_read_counts(self._message_counts_by_room)

    async def mark_room_read_to_current(self, room_name: str):
        """Set read count for a specific room to its current total, without decreasing."""
        tab_state = await self.get_state(TabSessionState)
        current_total = self._message_counts_by_room.get(room_name, 0)
        tab_state.mark_room_read(room_name, current_total)