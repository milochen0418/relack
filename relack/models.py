import reflex as rx
from typing import Optional
from pydantic import BaseModel
import datetime


class UserProfile(BaseModel):
    username: str
    email: str = ""
    nickname: str = ""
    is_guest: bool
    bio: str = ""
    avatar_seed: str = ""
    created_at: str = ""
    token: str = ""
    is_approved: bool = False
    avatar_url: str = ""


class MessagePart(BaseModel):
    """A run of message text; `href` is set when the run is a URL."""

    text: str
    href: str = ""


class ChatMessage(BaseModel):
    id: str
    sender: str
    display_name: str = ""
    content: str
    timestamp: str
    is_system: bool = False
    parts: list[MessagePart] = []
    # Open Graph preview of the first URL in the message (empty when none).
    preview_url: str = ""
    preview_title: str = ""
    preview_description: str = ""
    preview_image: str = ""
    preview_site: str = ""


class ChatMessageLog(BaseModel):
    """Wraps a chat message with its room origin for admin viewing."""

    room_name: str
    message: ChatMessage


class RoomInfo(BaseModel):
    name: str
    participant_count: int = 0
    description: str = ""
    created_by: str = "System"
    # Private rooms are visible only to their creator and `allowed_members` (usernames).
    is_private: bool = False
    allowed_members: list[str] = []

    def __setstate__(self, state):
        # Rooms pickled (Reflex disk/redis state) before a field existed lack it;
        # fill in the default so attribute access and serialization keep working.
        values = state.get("__dict__", {})
        for name, field in type(self).model_fields.items():
            if name not in values:
                values[name] = field.get_default(call_default_factory=True)
        super().__setstate__(state)

    def can_view(self, username: str) -> bool:
        return (
            not self.is_private
            or username == self.created_by
            or username in self.allowed_members
        )


class PermissionConfig(BaseModel):
    """Snapshot of admin permissions toggles for backup/restore."""

    google_requires_approval: bool = True
    guest_requires_approval: bool = True
    guest_can_create_room: bool = False
    guest_can_mention_users: bool = False
    guest_can_view_profiles: bool = False
    google_can_create_room: bool = False
    google_can_mention_users: bool = False
    google_can_view_profiles: bool = False