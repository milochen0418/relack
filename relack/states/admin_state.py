import reflex as rx
import os
from relack.states.shared_state import GlobalLobbyState
from relack.states.permission_state import PermissionState

class AdminState(rx.State):
    passcode_input: str = ""
    is_authenticated: bool = False
    is_settings_menu_open: bool = False
    active_settings_anchor: str = "data-maintenance"
    active_tab: str = "users"

    @rx.event
    def set_passcode_input(self, value: str):
        # Explicit setter to avoid relying on deprecated state_auto_setters
        self.passcode_input = value

    @rx.event
    def set_active_tab(self, value: str):
        self.active_tab = value

    async def check_passcode(self):
        expected = os.getenv("ADMIN_PASSCODE")
        if self.passcode_input == expected:
            self.is_authenticated = True
            # Reset tab to first tab after successful login
            self.active_tab = "users"
            # Ensure we are connected to the lobby to see data
            lobby = await self.get_state(GlobalLobbyState)
            await lobby.join_lobby()
            # Sync permissions UI from shared snapshot
            permission_state = await self.get_state(PermissionState)
            await permission_state.sync_from_lobby()
            return rx.toast("Admin access granted.")
        else:
            return rx.toast("Invalid Passcode")

    def logout(self):
        self.is_authenticated = False
        self.passcode_input = ""
        self.active_tab = "users"

    @rx.event
    def toggle_settings_menu(self):
        self.is_settings_menu_open = not self.is_settings_menu_open

    @rx.event
    def close_settings_menu(self):
        self.is_settings_menu_open = False

    @rx.event
    def go_to_settings_anchor(self, anchor: str):
        self.active_settings_anchor = anchor
        self.is_settings_menu_open = False
        return rx.scroll_to(anchor)
