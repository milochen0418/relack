import os
import reflex as rx
from relack.models import UserProfile
from relack.auth.session import (
    create_session,
    create_claim_token,
    delete_session,
    get_session,
    parse_session_id,
)
import datetime
import secrets

class AuthState(rx.State):
    guest_nickname: str = ""

    def set_guest_nickname(self, value: str):
        self.guest_nickname = value

    def _get_session_id(self) -> str:
        return parse_session_id(self.router.headers.cookie)

    def _auth_base_url(self) -> str:
        origin = self.router.page.host
        if origin and ("localhost" in origin or "127.0.0.1" in origin):
            return os.environ.get("BACKEND_URL", "http://localhost:8000")
        return origin or os.environ.get("BACKEND_URL", "http://localhost:8000")

    @rx.var
    def user(self) -> UserProfile | None:
        session_id = self._get_session_id()
        if not session_id:
            return None
        return get_session(session_id)

    @rx.event
    def handle_google_login(self):
        base = self._auth_base_url()
        yield rx.call_script(
            f"window.location.href = '{base}/auth/google/login'"
        )

    @rx.event
    def handle_guest_login(self):
        nickname = self.guest_nickname.strip()
        if not nickname:
            return rx.toast("Please enter a nickname")

        profile = UserProfile(
            username=nickname,
            is_guest=True,
            avatar_seed=nickname,
            created_at=datetime.datetime.now().isoformat(),
            token=f"guest_{secrets.token_urlsafe(8)}",
        )
        session_id = create_session(profile)
        claim = create_claim_token(session_id)
        base = self._auth_base_url()
        yield rx.call_script(
            f"window.location.href = '{base}/auth/claim?token={claim}'"
        )

    @rx.event
    async def logout(self):
        from relack.states.shared_state import RoomState, TabSessionState

        room_state = await self.get_state(RoomState)
        if room_state.in_room:
            await room_state.handle_leave_room()
        await room_state.on_disconnect()

        tab_state = await self.get_state(TabSessionState)
        tab_state.reset_tab_session()

        session_id = self._get_session_id()
        if session_id:
            delete_session(session_id)

        base = self._auth_base_url()
        yield rx.call_script(
            f"window.location.href = '{base}/auth/logout'"
        )
