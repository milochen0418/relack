import reflex as rx
from typing import Optional
from pydantic import BaseModel
import datetime


class Stored(BaseModel):
    """Models kept in Reflex's pickled states: Reflex's schema check skips `_` vars,
    so objects pickled before a field existed come back without it."""

    def __setstate__(self, state):
        # Rooms pickled (Reflex disk/redis state) before a field existed lack it;
        # fill in the default so attribute access and serialization keep working.
        values = state.get("__dict__", {})
        for name, field in type(self).model_fields.items():
            if name not in values:
                values[name] = field.get_default(call_default_factory=True)
        super().__setstate__(state)


class UserProfile(Stored):
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
    status_emoji: str = ""
    status_text: str = ""
    # When the status clears, and until when notifications are off (Unix time; 0 = never set).
    status_until: float = 0.0
    dnd_until: float = 0.0
    timezone: str = ""


class MessagePart(BaseModel):
    """A run of message text; `href` is set when the run is a URL."""

    text: str
    href: str = ""


class Attachment(BaseModel):
    """A file sent with a message, stored under the upload dir at `path`."""

    id: str
    name: str
    path: str
    mime: str = ""
    size: int = 0
    size_label: str = ""
    is_image: bool = False


class Reaction(BaseModel):
    """One emoji on a message: who reacted with it (`names` is the tooltip)."""

    emoji: str
    count: int = 0
    users: list[str] = []
    names: str = ""


class ChatMessage(Stored):
    id: str
    sender: str
    display_name: str = ""
    # As stored: mentions are `<@username>` / `<!here>` tokens (see relack.formatting).
    content: str
    # "HH:MM" of messages imported from before `created_at` existed.
    timestamp: str = ""
    is_system: bool = False
    parts: list[MessagePart] = []
    # Open Graph preview of the first URL in the message (empty when none).
    preview_url: str = ""
    preview_title: str = ""
    preview_description: str = ""
    preview_image: str = ""
    preview_site: str = ""
    seq: int = 0
    room: str = ""
    # Unix time (UTC); the browser shows it in its own time zone.
    created_at: float = 0.0
    edited: bool = False
    # Kept (as "This message was deleted.") only while it still has thread replies.
    deleted: bool = False
    # Thread root this message replies to; "" for messages in the room itself.
    parent_id: str = ""
    # Markdown shown in the bubble, mentions turned into `#mention-` links.
    render: str = ""
    avatar_seed: str = ""
    # The sender's status emoji, and whether the message is pinned in its room.
    status_emoji: str = ""
    pinned: bool = False
    mentions: list[str] = []
    attachments: list[Attachment] = []
    reactions: list[Reaction] = []
    reply_count: int = 0
    last_reply_at: float = 0.0
    # Avatar seeds of the latest people who replied in the thread.
    reply_seeds: list[str] = []


class SavedItem(BaseModel):
    """A pinned or saved message, or one with a reminder, shown in a list."""

    message_id: str
    room: str
    room_title: str
    parent_id: str = ""
    display_name: str
    text: str
    created_at: float = 0.0
    remind_at: float = 0.0


class ScheduledItem(BaseModel):
    id: str
    room: str
    room_title: str
    text: str
    due_at: float


class RoomBrowseItem(BaseModel):
    name: str
    title: str
    description: str = ""
    archived: bool = False
    joined: bool = True
    can_manage: bool = False


class AuditEntry(BaseModel):
    at: float
    actor: str
    action: str
    target: str = ""
    detail: str = ""


class WebhookInfo(BaseModel):
    token: str
    name: str
    created_by: str = ""


class SearchHit(BaseModel):
    """A message found by search, with the matching words split out for highlighting."""

    message_id: str
    room: str
    room_title: str
    parent_id: str = ""
    sender: str
    display_name: str
    avatar_seed: str = ""
    created_at: float = 0.0
    before: str = ""
    match: str = ""
    after: str = ""


class FileHit(BaseModel):
    """A file found by search."""

    file: Attachment
    message_id: str
    room: str
    room_title: str
    parent_id: str = ""
    uploader: str
    created_at: float = 0.0


class ChatMessageLog(BaseModel):
    """Wraps a chat message with its room origin for admin viewing."""

    room_name: str
    room_title: str = ""
    message: ChatMessage


class RoomInfo(Stored):
    name: str
    participant_count: int = 0
    description: str = ""
    created_by: str = "System"
    # Private rooms are visible only to their creator and `allowed_members` (usernames).
    is_private: bool = False
    allowed_members: list[str] = []
    # Direct message among `created_by` and `allowed_members` (two people, or a group).
    is_direct: bool = False
    # Display name after a rename; `name` stays the room's permanent id.
    title: str = ""
    # Read-only and out of the sidebar; found under Browse rooms.
    archived: bool = False
    # Bumped to shut someone out: tabs still linked to the old shared state get nothing more.
    token_rev: int = 0

    def can_view(self, username: str) -> bool:
        return (
            not self.is_private
            or username == self.created_by
            or username in self.allowed_members
        )


class CallInfo(BaseModel):
    """The ongoing call of a room (at most one per room)."""

    room_name: str
    # Opaque id handed to the call app as its room; random, so a private room's
    # call cannot be guessed from the room name.
    call_id: str
    # The call app (provider of `call.join`) chosen by whoever started the call.
    # Everyone joins through it: other apps can't reach this call.
    app: str = ""
    started_by: str
    started_at: float
    # Still ringing the room's people (stops after a while, not when someone answers).
    ringing: bool = True
    # client_token -> username of each tab in the call, and its last heartbeat.
    members: dict[str, str] = {}
    last_seen: dict[str, float] = {}
    # Usernames that answered or declined; they are not rung again for this call.
    responded: list[str] = []


class IncomingCall(BaseModel):
    """A call ringing for the current viewer (what the popup shows)."""

    room_name: str
    title: str
    caller: str
    is_direct: bool = False


class PermissionConfig(BaseModel):
    """Snapshot of admin permissions toggles for backup/restore."""

    # Everything is open until an admin tightens it.
    google_requires_approval: bool = False
    guest_requires_approval: bool = False
    guest_can_create_room: bool = True
    guest_can_mention_users: bool = True
    guest_can_view_profiles: bool = True
    google_can_create_room: bool = True
    google_can_mention_users: bool = True
    google_can_view_profiles: bool = True