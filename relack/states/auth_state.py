import reflex as rx
from relack.models import UserProfile
import logging
from faker import Faker
import datetime
import random
import string
from reflex_google_auth import GoogleAuthState

fake = Faker()


class AuthState(GoogleAuthState):
    user_profile_json: str = rx.LocalStorage("", name="reflex_chat_profile_v2")
    is_hydrated: bool = False
    auth_view: str = "guest"
    guest_nickname: str = ""
    reg_username: str = ""
    reg_nickname: str = ""
    reg_bio: str = ""
    _requires_registration: bool = False

    @rx.var
    def user(self) -> UserProfile | None:
        """
        Returns the current user profile from LocalStorage.
        Trusts the local storage data to allow immediate UI rendering.
        Validation happens asynchronously via check_google_auth.
        """
        if not self.user_profile_json:
            return None
        try:
            profile = UserProfile.model_validate_json(self.user_profile_json)
            return profile
        except Exception:
            logging.exception("Failed to parse user profile")
            return None

    @rx.var
    def requires_registration(self) -> bool:
        return self._requires_registration

    @rx.event
    async def check_google_auth(self):
        """Triggered after Google sign-in to check if user needs registration or can auto-login."""
        if not self.token_is_valid:
            self._requires_registration = False
            logging.debug("Token is not valid during check_google_auth")
            return
        email = self.tokeninfo.get("email", "")
        if not email:
            logging.warning("No email found in tokeninfo")
            return
        current_user = self.user
        if current_user and current_user.email == email:
            self._requires_registration = False
            logging.info(f"User {email} already authenticated locally.")
            return
        try:
            from relack.states.shared_state import GlobalLobbyState

            lobby = await self.get_state(GlobalLobbyState)
            lobby_linked = await lobby._link_to("global-lobby")
            if email in lobby_linked._google_registry:
                profile = lobby_linked._google_registry[email]
                self.user_profile_json = profile.model_dump_json()
                self._requires_registration = False
                logging.info(f"User {email} restored from global registry.")
                return rx.toast(
                    f"Welcome back, {profile.nickname or profile.username}!"
                )
            self.reg_username = email
            self.reg_nickname = email.split("@")[0]
            self._requires_registration = True
            logging.info(f"User {email} requires registration.")
        except Exception as e:
            logging.exception(f"Error in check_google_auth: {e}")
            self.reg_username = email
            self.reg_nickname = email.split("@")[0]
            self._requires_registration = True

    @rx.event
    def set_auth_view(self, view: str):
        self.auth_view = view

    @rx.event
    def handle_guest_login(self):
        if not self.guest_nickname.strip():
            return rx.toast("Please enter a nickname")
        profile = UserProfile(
            username=self.guest_nickname,
            is_guest=True,
            avatar_seed=self.guest_nickname,
            created_at=datetime.datetime.now().isoformat(),
            token=f"guest_{''.join(random.choices(string.ascii_letters, k=8))}",
            email="",
        )
        self.user_profile_json = profile.model_dump_json()
        return rx.toast(f"Welcome, {profile.username}!")

    @rx.event
    async def finish_google_registration(self):
        """Creates a profile for a newly signed-in Google user."""
        if not self.reg_username.strip():
            return rx.toast("Username (Email) is required")
        if not self.reg_nickname.strip():
            return rx.toast("Please choose a nickname")
        if not self.token_is_valid:
            return rx.toast("Session expired, please sign in again")
        google_info = self.tokeninfo
        google_id = google_info.get("sub", "")
        email = google_info.get("email", "")
        profile = UserProfile(
            username=self.reg_username,
            nickname=self.reg_nickname,
            is_guest=False,
            bio=self.reg_bio or "New Google Member",
            avatar_seed=self.reg_nickname,
            created_at=datetime.datetime.now().isoformat(),
            token=f"user_{''.join(random.choices(string.ascii_letters, k=10))}",
            google_id=google_id,
            email=email,
        )
        self.user_profile_json = profile.model_dump_json()
        from relack.states.shared_state import GlobalLobbyState

        lobby = await self.get_state(GlobalLobbyState)
        lobby_linked = await lobby._link_to("global-lobby")
        lobby_linked._google_registry[email] = profile
        lobby_linked._known_profiles[profile.username] = profile
        self._requires_registration = False
        return rx.toast(
            f"Profile created! Welcome, {profile.nickname or profile.username}!"
        )

    @rx.event
    def logout(self):
        """Completely clear all session and local data to prevent auto-login on refresh."""
        self.user_profile_json = ""
        self.guest_nickname = ""
        self.reg_username = ""
        self.reg_bio = ""
        self.auth_view = "guest"
        self._requires_registration = False
        self.id_token_json = ""
        super().logout()
        yield rx.call_script("google.accounts.id.disableAutoSelect()")
        yield rx.clear_local_storage()
        yield rx.clear_session_storage()
        yield rx.redirect("/")
        yield rx.toast("Logged out successfully.")

    pass