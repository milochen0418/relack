"""Slash commands typed in the message box."""

import re
import time

import reflex as rx

from relack import db, permissions
from relack.models import UserProfile

HELP = (
    "/shrug [text] · /me text · /later 2h text · /mute · /unmute · /leave · "
    "/status 🌴 text · /dnd 1h · /topic text · /rename name · /archive"
)
_DURATION = re.compile(r"^(\d+)(m|h|d)$")


def duration(text: str) -> int | None:
    match = _DURATION.match(text)
    if not match:
        return None
    return int(match.group(1)) * {"m": 60, "h": 3600, "d": 86400}[match.group(2)]


async def set_status(state: rx.State, user: UserProfile, **changes):
    from relack.states.shared_state import GlobalLobbyState  # noqa: WPS433

    if permissions.is_pending(user):
        return
    profile = db.load_profiles().get(user.username, user).model_copy(update=changes)
    db.save_profile(profile)
    lobby = await state.get_state(GlobalLobbyState)
    target = lobby if lobby._linked_to else await lobby._link_to("global-lobby")
    target._known_profiles = {**target._known_profiles, profile.username: profile}


async def run_command(state, user: UserProfile, text: str):
    """Returns None for text that isn't a command, else (events to return, text to post instead)."""
    from relack.states.shared_state import GlobalLobbyState, LocalUIState  # noqa: WPS433

    name, _, rest = text[1:].partition(" ")
    rest = rest.strip()
    room = state.room_name
    done = rx.toast("Done.")
    if name == "help":
        return rx.toast(HELP, duration=12000), ""
    if name == "shrug":
        return None, f"{rest} ¯\\\\\\_(ツ)\\_/¯".strip()
    if name == "me":
        return None, f"_{user.nickname or user.username} {rest}_"
    if name == "later":
        wait, _, body = rest.partition(" ")
        seconds = duration(wait)
        if seconds is None or not body.strip():
            return rx.toast("Use /later 2h your message (m, h or d)."), ""
        db.add_scheduled(user.username, room, body.strip(), time.time() + seconds)
        return rx.toast(f"Scheduled. It goes out in {wait}."), ""
    if name == "mute" or name == "unmute":
        db.set_room_pref(user.username, room, muted=name == "mute")
        return done, ""
    if name == "leave":
        return [GlobalLobbyState.set_room_left(room, True), state.__class__.handle_leave_room, LocalUIState.show_rooms], ""
    if name == "status":
        emoji, _, words = rest.partition(" ")
        await set_status(state, user, status_emoji=emoji, status_text=words, status_until=0.0)
        return done, ""
    if name == "dnd":
        seconds = duration(rest or "1h")
        if seconds is None:
            return rx.toast("Use /dnd 1h (m, h or d)."), ""
        await set_status(state, user, dnd_until=time.time() + seconds)
        return rx.toast("Notifications paused."), ""
    if name == "topic":
        info = db.load_rooms().get(room)
        return GlobalLobbyState.update_room(room, (info.title or info.name) if info else room, rest), ""
    if name == "rename":
        info = db.load_rooms().get(room)
        return GlobalLobbyState.update_room(room, rest, info.description if info else ""), ""
    if name == "archive":
        return GlobalLobbyState.set_archived(room, True), ""
    return None  # Not a command: "/usr/bin" is an ordinary message.
