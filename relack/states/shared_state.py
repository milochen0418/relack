import reflex as rx
import json
import datetime as dt
from relack.models import RoomInfo, ChatMessage, UserProfile, ChatMessageLog
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
    _messages_by_room: dict[str, list[ChatMessage]] = {}
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

    def _update_participant_count(self, room_name: str, delta: int):
        """Helper to update participant counts. Must be called on a linked state."""
        if room_name in self._rooms:
            room = self._rooms[room_name]
            room.participant_count += delta
            self._rooms[room_name] = room

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

        try:
            self._rooms = {room["name"]: RoomInfo(**room) for room in rooms_raw}
            self._known_profiles = {
                profile["username"]: UserProfile(**profile) for profile in profiles_raw
            }
            reconstructed: dict[str, list[ChatMessage]] = {}
            for room_name, msgs in messages_raw.items():
                reconstructed[room_name] = [ChatMessage(**msg) for msg in msgs]
            self._messages_by_room = reconstructed
        except Exception:
            yield rx.toast("Import failed: schema mismatch")
            return

        # Clear active room sessions; admins are not joined to rooms.
        room_state = await self.get_state(RoomState)
        yield RoomState.reset_room_state
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


class RoomState(rx.SharedState):
    """
    Manages the state of a specific chat room.
    This state will be linked to a specific room token (e.g., 'room-general').
    """

    _active_users: dict[str, str] = {}
    _active_user_profiles: dict[str, UserProfile] = {}
    _messages: list[ChatMessage] = []
    _room_name: str = ""
    current_message: str = ""
    is_sidebar_open: bool = True
    is_user_list_open: bool = False

    @rx.event
    def toggle_sidebar(self):
        self.is_sidebar_open = not self.is_sidebar_open

    @rx.event
    def toggle_user_list(self):
        self.is_user_list_open = not self.is_user_list_open

    @rx.var
    def in_room(self) -> bool:
        return self._room_name != ""

    @rx.var
    def room_name(self) -> str:
        return self._room_name

    @rx.var
    def messages(self) -> list[ChatMessage]:
        return self._messages

    @rx.var
    def users(self) -> list[str]:
        return list(self._active_users.values())

    @rx.var
    def online_users_list(self) -> list[UserProfile]:
        return list(self._active_user_profiles.values())

    @rx.var
    def active_user_count(self) -> int:
        return len(self._active_users)

    @rx.event
    def reset_room_state(self):
        """Clears local room state during a global reset."""
        self._active_users = {}
        self._active_user_profiles = {}
        self._messages = []
        self._room_name = ""
        self.current_message = ""

    @rx.event
    async def handle_join_room(self, room_name: str):
        auth = await self.get_state(AuthState)
        if not auth.user:
            return rx.toast("Please log in to join rooms")
        if self._room_name:
            await self.handle_leave_room()
        safe_token = f"room-{room_name.replace(' ', '-').replace('_', '-').lower()}"
        new_room_state = await self._link_to(safe_token)
        new_room_state._room_name = room_name
        username = auth.user.username
        client_token = self.router.session.client_token
        new_room_state._active_users[client_token] = username
        new_room_state._active_user_profiles[client_token] = auth.user
        join_msg = ChatMessage(
            id=str(uuid.uuid4()),
            sender="System",
            content=f"{username} joined the room.",
            timestamp=datetime.datetime.now().strftime("%H:%M"),
            is_system=True,
        )
        new_room_state._messages.append(join_msg)
        lobby = await self.get_state(GlobalLobbyState)
        if not lobby._linked_to:
            lobby_linked = await lobby._link_to("global-lobby")
        else:
            lobby_linked = lobby
        room_info = lobby_linked._rooms.get(room_name)
        if room_info and room_info.created_by != "System":
            creator_msg = ChatMessage(
                id=str(uuid.uuid4()),
                sender="System",
                content=f"This room was created by {room_info.created_by}.",
                timestamp=datetime.datetime.now().strftime("%H:%M"),
                is_system=True,
            )
            new_room_state._messages.append(creator_msg)
            await lobby.record_message(room_name, creator_msg)
        if lobby._linked_to == "global-lobby":
            lobby._update_participant_count(room_name, 1)
        await lobby.record_message(room_name, join_msg)

    @rx.event
    async def handle_leave_room(self):
        if not self._room_name:
            return
        client_token = self.router.session.client_token
        username = self._active_users.get(client_token, "Someone")
        leave_msg = ChatMessage(
            id=str(uuid.uuid4()),
            sender="System",
            content=f"{username} left the room.",
            timestamp=datetime.datetime.now().strftime("%H:%M"),
            is_system=True,
        )
        self._messages.append(leave_msg)
        lobby = await self.get_state(GlobalLobbyState)
        await lobby.record_message(self._room_name, leave_msg)
        if client_token in self._active_users:
            del self._active_users[client_token]
        if client_token in self._active_user_profiles:
            del self._active_user_profiles[client_token]
        if lobby._linked_to == "global-lobby":
            lobby._update_participant_count(self._room_name, -1)
        await self._unlink()
        self._room_name = ""

    @rx.event
    async def send_message(self, form_data: dict[str, Any]):
        message_text = form_data.get("message", "").strip()
        if not message_text:
            return
        client_token = self.router.session.client_token
        sender = self._active_users.get(client_token, "Unknown")
        msg = ChatMessage(
            id=str(uuid.uuid4()),
            sender=sender,
            content=message_text,
            timestamp=datetime.datetime.now().strftime("%H:%M"),
            is_system=False,
        )
        self._messages.append(msg)
        lobby = await self.get_state(GlobalLobbyState)
        await lobby.record_message(self._room_name, msg)
        self.current_message = ""