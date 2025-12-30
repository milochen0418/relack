import reflex as rx
from typing import Optional
from relack.models import UserProfile
from relack.states.auth_state import AuthState
from relack.states.shared_state import GlobalLobbyState


class ProfileState(rx.State):
    current_profile: Optional[UserProfile] = None
    is_loading: bool = True

    @rx.event
    async def get_profile(self):
        self.is_loading = True
        username = self.router.url.query_parameters.get("username")
        if not username:
            self.is_loading = False
            return
        auth = await self.get_state(AuthState)
        if auth.user and auth.user.username == username:
            self.current_profile = auth.user
            self.is_loading = False
            return
        lobby = await self.get_state(GlobalLobbyState)
        lobby_linked = await lobby._link_to("global-lobby")
        if username in lobby_linked._known_profiles:
            self.current_profile = lobby_linked._known_profiles[username]
        else:
            self.current_profile = None
        self.is_loading = False