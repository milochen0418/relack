import reflex as rx
from typing import Optional
from pydantic import BaseModel
import datetime


class UserProfile(BaseModel):
    username: str
    nickname: str = ""
    is_guest: bool
    bio: str = ""
    avatar_seed: str = ""
    created_at: str = ""
    token: str = ""
    google_id: str = ""
    email: str = ""


class ChatMessage(BaseModel):
    id: str
    sender: str
    content: str
    timestamp: str
    is_system: bool = False


class RoomInfo(BaseModel):
    name: str
    participant_count: int = 0
    description: str = ""
    created_by: str = "System"