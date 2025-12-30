import reflex as rx
from relack.models import RoomInfo, ChatMessage, UserProfile
from relack.states.auth_state import AuthState
import datetime
import uuid
import logging


class GlobalLobbyState(rx.SharedState):
    """
    Manages the global list of rooms and active user counts.
    All users link to this with a common token 'lobby' to see the directory.
    """

    _rooms: dict[str, RoomInfo] = {}
    _known_profiles: dict[str, UserProfile] = {}
    _google_registry: dict[str, UserProfile] = {}

    @rx.var
    def room_list(self) -> list[RoomInfo]:
        return list(self._rooms.values())

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

    @rx.event
    async def create_room(self, room_name: str, description: str):
        if not room_name:
            return rx.toast("Room name required")
        auth = await self.get_state(AuthState)
        if not auth.user:
            return rx.toast("You must be logged in to create a room.")
        if auth.user.is_guest:
            return rx.toast(
                "Guest users cannot create rooms. Please sign in with Google."
            )
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
        if not auth.user or auth.user.is_guest:
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
        self._google_registry = {}
        room_state = await self.get_state(RoomState)
        yield RoomState.reset_room_state
        yield rx.toast("Database cleared successfully!")
        return


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
        if lobby._linked_to == "global-lobby":
            lobby._update_participant_count(room_name, 1)

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
        if client_token in self._active_users:
            del self._active_users[client_token]
        if client_token in self._active_user_profiles:
            del self._active_user_profiles[client_token]
        lobby = await self.get_state(GlobalLobbyState)
        if lobby._linked_to == "global-lobby":
            lobby._update_participant_count(self._room_name, -1)
        return await self._unlink()

    @rx.event
    def send_message(self, form_data: dict[str, str]):
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
        self.current_message = ""