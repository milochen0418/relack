import reflex as rx
from relack.models import UserProfile
import logging
from faker import Faker
import datetime
import random
import string

fake = Faker()


class AuthState(rx.State):
    user_profile_json: str = rx.LocalStorage("", name="reflex_chat_profile_v2")
    is_hydrated: bool = False
    guest_nickname: str = ""

    def set_guest_nickname(self, value: str):
        self.guest_nickname = value

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
        return rx.toast(f"Welcome, {profile.username}!")

    @rx.event
    def logout(self):
        """Completely clear all session and local data."""
        self.user_profile_json = ""
        self.guest_nickname = ""
        yield rx.clear_local_storage()
        yield rx.clear_session_storage()
        yield rx.redirect("/")
        yield rx.toast("Logged out successfully.")


    pass