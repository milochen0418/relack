import reflex as rx
import os
from relack.states.shared_state import GlobalLobbyState

class AdminState(rx.State):
    passcode_input: str = ""
    is_authenticated: bool = False

    @rx.event
    def set_passcode_input(self, value: str):
        # Explicit setter to avoid relying on deprecated state_auto_setters
        self.passcode_input = value

    async def check_passcode(self):
        expected = os.getenv("ADMIN_PASSCODE")
        if self.passcode_input == expected:
            self.is_authenticated = True
            # Ensure we are connected to the lobby to see data
            lobby = await self.get_state(GlobalLobbyState)
            await lobby.join_lobby()
            return rx.toast("Admin access granted.")
        else:
            return rx.toast("Invalid Passcode")

    def logout(self):
        self.is_authenticated = False
        self.passcode_input = ""
