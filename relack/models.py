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


class ChatMessage(BaseModel):
    id: str
    sender: str
    content: str
    timestamp: str
    is_system: bool = False


class ChatMessageLog(BaseModel):
    """Wraps a chat message with its room origin for admin viewing."""

    room_name: str
    message: ChatMessage


class RoomInfo(BaseModel):
    name: str
    participant_count: int = 0
    description: str = ""
    created_by: str = "System"