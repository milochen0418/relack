"""Calls in rooms, carried out by a call app through the DDNS Intent `call.join`.

relack keeps who is in which room's call (`GlobalLobbyState._calls`) and rings
people; the call itself runs in the call app, opened in the intent dialog:

    Intent.start(<call app>, "call.join", private={"room": <call id>}, keep_alive=True,
                 single=True, title=..., user=..., name=...)

Whoever starts a call chooses its app among the installed apps that provide
`call.join` (the DDNS Intent registry; `DDNS_INTENT_PROVIDER_CALL_JOIN` for
local dev), through `Intent.choose_app`, which asks only when there are several.
The call keeps that app (`CallInfo.app`), so everyone who answers or joins
later opens the same app, and so the same call, without being asked.
`RELACK_CALL_APP` names the app for every call instead.

The call id is private: anyone holding it can join the call, so it stays out of
the iframe URL. The call dialog is keep-alive: other dialogs (People,
profiles...) minimize it to the tray and the call goes on; it is single, so
joining another call closes it.
"""

import os
import secrets
import time

import reflex as rx
from reflex_ddns_auth.intent import Intent, IntentState

from relack.models import CallInfo
from relack.states.auth_state import AuthState
from relack.states.shared_state import GlobalLobbyState

CALL_APP = os.environ.get("RELACK_CALL_APP") or None
CALL_ACTION = "call.join"
# How long a new call rings the room's people.
RING_SECONDS = 45
# A tab in a call refreshes its entry this often...
TOUCH_SECONDS = 15
# ...and is dropped after this long without a heartbeat (closed tab, lost network).
# Generous because background tabs get their timers throttled.
STALE_SECONDS = 150
# The dialog opens one event after join_call; don't mistake that gap for a closed dialog.
OPENING_GRACE_SECONDS = 10


async def _lobby(state: rx.State) -> GlobalLobbyState:
    lobby = await state.get_state(GlobalLobbyState)
    if not lobby._linked_to:
        lobby = await lobby._link_to("global-lobby")
    return lobby


def _without(call: CallInfo, client_token: str) -> CallInfo:
    return call.model_copy(
        update={
            "members": {t: u for t, u in call.members.items() if t != client_token},
            "last_seen": {t: ts for t, ts in call.last_seen.items() if t != client_token},
        }
    )


def _leave(lobby: GlobalLobbyState, room_name: str, client_token: str):
    """Take a tab out of a room's call; the call ends with its last member."""
    call = lobby._calls.get(room_name)
    if call is None:
        return
    call = _without(call, client_token)
    calls = {name: c for name, c in lobby._calls.items() if name != room_name}
    if call.members:
        calls[room_name] = call
    lobby._calls = calls


class CallState(rx.State):
    """This tab's side of a call: the room whose call it is in."""

    current_room: str = ""
    _call_id: str = ""
    # The call's app (CallInfo.app), to put the call back as it was.
    _call_app: str = ""
    _joined_at: float = 0.0
    # Room of the call this tab starts, while its caller chooses the call app.
    _starting_room: str = ""

    @rx.event
    async def join_call(self, room_name: str):
        """Start the room's call, or join the one in progress, and open it in the dialog."""
        return await self._join(room_name, CALL_APP or "")

    @rx.event
    async def start_call(self, data: dict):
        """The caller chose the call app: start the room's call in it."""
        room_name, self._starting_room = self._starting_room, ""
        if room_name and data.get("app"):
            # Joins instead if someone started the room's call meanwhile.
            return await self._join(room_name, data["app"])

    async def _join(self, room_name: str, app: str):
        """Join the room's call in its app, or start the call in ``app``.

        Without ``app``, a new call first lets the caller choose it
        (``start_call`` comes back here with it).
        """
        auth = await self.get_state(AuthState)
        if not auth.user:
            return rx.toast("Please log in to call.")
        me = auth.user.username
        lobby = await _lobby(self)
        room = lobby._rooms.get(room_name)
        if room is None or not room.can_view(me):
            return rx.toast("This room is private.")
        dialog = await self.get_state(IntentState)
        if self.current_room == room_name and CALL_ACTION in dialog.open_actions:
            # Already in this call (maybe minimized): bring it back rather than rejoin.
            return Intent.show(CALL_ACTION)
        if room_name not in lobby._calls and not app:
            # Everyone who joins later opens the app chosen now: other apps can't reach the call.
            self._starting_room = room_name
            return Intent.choose_app(CALL_ACTION, on_result=CallState.start_call)

        now = time.time()
        client_token = self.router.session.client_token
        if self.current_room and self.current_room != room_name:
            # Switching calls: the old dialog's on_cancel comes too late to know which one.
            _leave(lobby, self.current_room, client_token)
        call = lobby._calls.get(room_name) or CallInfo(
            room_name=room_name,
            call_id=secrets.token_urlsafe(12),
            app=app,
            started_by=me,
            started_at=now,
        )
        call = call.model_copy(
            update={
                "members": {**call.members, client_token: me},
                "last_seen": {**call.last_seen, client_token: now},
                "responded": [*call.responded, me] if me not in call.responded else call.responded,
            }
        )
        lobby._calls = {**lobby._calls, room_name: call}
        self.current_room = room_name
        self._call_id = call.call_id
        # A call saved before CallInfo.app existed has none: the registry picks one.
        self._call_app = getattr(call, "app", "")
        self._joined_at = now
        title = lobby._room_title(room, me)
        return Intent.start(
            self._call_app,
            CALL_ACTION,
            on_result=CallState.call_closed,
            on_cancel=CallState.call_closed,
            private={"room": call.call_id},
            keep_alive=True,
            single=True,
            label=f"Call · {title}",
            title=title,
            user=me,
            name=auth.user.nickname or me,
        )

    @rx.event
    async def call_closed(self, data: dict):
        """The call dialog closed (hung up or closed): leave the call.

        Other dialogs only minimize it (keep-alive), so being replaced means
        another call took its place (single): join_call already moved us.
        """
        if data.get("reason") == "replaced" and data.get("by") == CALL_ACTION:
            return
        room_name = self.current_room
        self.current_room = ""
        self._call_id = ""
        if room_name:
            _leave(await _lobby(self), room_name, self.router.session.client_token)

    @rx.event
    async def decline_call(self, room_name: str):
        auth = await self.get_state(AuthState)
        if not auth.user:
            return
        lobby = await _lobby(self)
        call = lobby._calls.get(room_name)
        if call is None or auth.user.username in call.responded:
            return
        lobby._calls = {
            **lobby._calls,
            room_name: call.model_copy(update={"responded": [*call.responded, auth.user.username]}),
        }

    @rx.event
    async def heartbeat(self):
        """Keep this tab's call entry fresh; stop ringing and drop stale entries for everyone."""
        lobby = await _lobby(self)
        if not lobby._calls and not self.current_room:
            return
        now = time.time()
        client_token = self.router.session.client_token
        me = ""
        if self.current_room:
            dialog = await self.get_state(IntentState)
            in_dialog = CALL_ACTION in dialog.open_actions  # in front or minimized
            if in_dialog or now - self._joined_at < OPENING_GRACE_SECONDS:
                auth = await self.get_state(AuthState)
                me = auth.user.username if auth.user else ""
            if not me:
                # The dialog went away without telling us: we are not in the call.
                self.current_room = ""
                self._call_id = ""

        calls: dict[str, CallInfo] = {}
        for name, call in lobby._calls.items():
            fresh = call
            if me and name == self.current_room and (
                now - call.last_seen.get(client_token, 0) > TOUCH_SECONDS
            ):
                fresh = fresh.model_copy(
                    update={
                        "members": {**fresh.members, client_token: me},
                        "last_seen": {**fresh.last_seen, client_token: now},
                    }
                )
            for token, seen in fresh.last_seen.items():
                if now - seen > STALE_SECONDS:
                    fresh = _without(fresh, token)
            if fresh.ringing and now - fresh.started_at > RING_SECONDS:
                fresh = fresh.model_copy(update={"ringing": False})
            if fresh.members:
                calls[name] = fresh
        if me and self.current_room not in calls:
            # Our call was dropped (e.g. this tab slept past STALE_SECONDS) while
            # the dialog still runs it: put it back so others can see and join it.
            calls[self.current_room] = CallInfo(
                room_name=self.current_room,
                call_id=self._call_id,
                app=self._call_app,
                started_by=me,
                started_at=now,
                ringing=False,
                members={client_token: me},
                last_seen={client_token: now},
            )
        if calls != lobby._calls:
            lobby._calls = calls
