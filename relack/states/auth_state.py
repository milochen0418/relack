import reflex as rx
from relack.models import UserProfile
from reflex_google_auth import GoogleAuthState
import logging
from faker import Faker
import datetime
import random
import string
from google.oauth2.id_token import verify_oauth2_token
from google.auth.transport import requests
from reflex_google_auth.state import TokenCredential

fake = Faker()


class AuthState(GoogleAuthState):
    user_profile_json: str = rx.LocalStorage("", name="reflex_chat_profile_v2")
    is_hydrated: bool = False
    guest_nickname: str = ""

    def set_guest_nickname(self, value: str):
        self.guest_nickname = value

    @rx.var(cache=True)
    def tokeninfo(self) -> TokenCredential:
        try:
            return TokenCredential(
                verify_oauth2_token(
                    self.id_token,
                    requests.Request(),
                    self.client_id,
                    clock_skew_in_seconds=60
                )
            )
        except Exception as exc:
            if self.token_response_json:
                print(f"Error verifying token: {exc!r}")
                self.token_response_json = ""
        return {}

    @rx.var
    def user(self) -> UserProfile | None:
        """
        Returns the current user profile from LocalStorage.
        Trusts the local storage data to allow immediate UI rendering.
        """
        if not self.user_profile_json:
            return None
        try:
            profile = UserProfile.model_validate_json(self.user_profile_json)
            return profile
        except Exception:
            logging.exception("Failed to parse user profile")
            return None

    @rx.event
    async def on_success_google_auth(self, id_token: dict):
        logging.info(f"Google Auth Success Data: {id_token}")
        
        # 1. Let the base class handle the standard storage
        yield GoogleAuthState.on_success(id_token)

        # 2. Manually verify to get the email immediately and handle errors
        try:
            # Extract the JWT token string
            token = ""
            if "credential" in id_token:
                token = id_token["credential"]
            elif "id_token" in id_token:
                token = id_token["id_token"]
            
            if not token:
                logging.error("No credential found in response")
                yield rx.toast("Login failed: No credential received")
                return

            # Verify the token
            # Note: We might need to handle clock skew if the server time is behind
            id_info = verify_oauth2_token(
                token, 
                requests.Request(), 
                self.client_id,
                clock_skew_in_seconds=10 # Allow some clock skew
            )
            
            email = id_info.get("email")
            if not email:
                logging.error("No email in token info")
                yield rx.toast("Login failed: Email not found in token")
                return

            # Try to preserve existing profile fields (e.g., bio) from storage or lobby
            existing_profile = self.user
            from relack.states.shared_state import GlobalLobbyState
            lobby_state = await self.get_state(GlobalLobbyState)
            lobby_linked = await lobby_state._link_to("global-lobby")
            if email in lobby_linked._known_profiles:
                existing_profile = lobby_linked._known_profiles[email]

            profile = UserProfile(
                username=email,
                email=email,
                nickname=(existing_profile.nickname if existing_profile and existing_profile.nickname else id_info.get("name", email)),
                is_guest=False,
                avatar_seed=(existing_profile.avatar_seed if existing_profile and existing_profile.avatar_seed else email),
                created_at=(existing_profile.created_at if existing_profile and existing_profile.created_at else datetime.datetime.now().isoformat()),
                token=id_info.get("sub", ""),
                bio=(existing_profile.bio if existing_profile else ""),
            )
            self.user_profile_json = profile.model_dump_json()
            
            # Notify lobby about the new user
            from relack.states.shared_state import GlobalLobbyState
            yield GlobalLobbyState.join_lobby
            
            yield rx.toast(f"Welcome, {profile.nickname}!")

        except ValueError as e:
            logging.error(f"Token verification failed: {e}")
            yield rx.toast(f"Login failed: {str(e)}")
        except Exception as e:
            logging.exception("Unexpected error during Google Login")
            yield rx.toast("An unexpected error occurred during login")

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
        )
        self.user_profile_json = profile.model_dump_json()
        
        # Notify lobby about the new user
        from relack.states.shared_state import GlobalLobbyState
        yield GlobalLobbyState.join_lobby
        
        return rx.toast(f"Welcome, {profile.username}!")

    @rx.event
    async def logout(self):
        """Completely clear all session and local data."""
        from relack.states.shared_state import RoomState, TabSessionState
        room_state = await self.get_state(RoomState)
        
        # Ensure we properly clean up presence before logout
        if room_state.in_room:
            # Call leave room to remove from active users
            await room_state.handle_leave_room()
        
        # Also explicitly trigger disconnect cleanup
        await room_state.on_disconnect()

        # Clear tab-scoped session snapshots before wiping browser storage.
        tab_state = await self.get_state(TabSessionState)
        tab_state.reset_tab_session()

        self.user_profile_json = ""
        self.guest_nickname = ""
        yield rx.clear_local_storage()
        yield rx.clear_session_storage()
        yield rx.redirect("/")
        yield rx.toast("Logged out successfully.")


    pass