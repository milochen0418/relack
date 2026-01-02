import reflex as rx
from typing import Optional
from relack.models import UserProfile
from relack.states.auth_state import AuthState
from relack.states.shared_state import GlobalLobbyState


class ProfileState(rx.State):
    current_profile: Optional[UserProfile] = None
    is_loading: bool = True
    is_editing: bool = False
    edited_nickname: str = ""
    edited_bio: str = ""

    @rx.event
    async def get_profile(self):
        self.is_loading = True
        username = self.router.page.params.get("username")
        if not username:
            self.is_loading = False
            return
        
        auth = await self.get_state(AuthState)
        
        # Check if it's the current user
        if auth.user and auth.user.username == username:
            self.current_profile = auth.user
        else:
            # Check global lobby
            lobby = await self.get_state(GlobalLobbyState)
            lobby_linked = await lobby._link_to("global-lobby")
            if username in lobby_linked._known_profiles:
                self.current_profile = lobby_linked._known_profiles[username]
            else:
                self.current_profile = None
        
        # Initialize edit fields if profile found
        if self.current_profile:
            self.edited_nickname = self.current_profile.nickname
            self.edited_bio = self.current_profile.bio
            
        self.is_loading = False

    @rx.event
    def toggle_edit(self):
        self.is_editing = not self.is_editing
        if self.current_profile and not self.is_editing:
            # Reset fields on cancel
            self.edited_nickname = self.current_profile.nickname
            self.edited_bio = self.current_profile.bio

    @rx.event
    def set_edited_nickname(self, value: str):
        self.edited_nickname = value

    @rx.event
    def set_edited_bio(self, value: str):
        self.edited_bio = value

    @rx.event
    async def save_profile(self):
        auth = await self.get_state(AuthState)
        if not auth.user or not self.current_profile:
            return
        
        if auth.user.username != self.current_profile.username:
            return rx.toast("You can only edit your own profile.")

        # Update AuthState (Current User)
        auth.user.nickname = self.edited_nickname
        auth.user.bio = self.edited_bio
        auth.user_profile_json = auth.user.model_dump_json()
        
        # Update Local Profile State
        self.current_profile = auth.user
        
        # Update Global Lobby
        lobby = await self.get_state(GlobalLobbyState)
        lobby_linked = await lobby._link_to("global-lobby")
        lobby_linked._known_profiles[auth.user.username] = auth.user
        
        self.is_editing = False
        return rx.toast("Profile updated successfully!")