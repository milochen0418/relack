import reflex as rx
import os
from relack import db, permissions
from relack.models import AuditEntry, ChatMessageLog, RoomInfo, UserProfile
from relack.states.auth_state import AuthState
from relack.states.shared_state import GlobalLobbyState
from relack.states.permission_state import PermissionState

class AdminState(rx.State):
    passcode_input: str = ""
    is_authenticated: bool = False
    is_settings_menu_open: bool = False
    active_settings_anchor: str = "data-maintenance"
    active_tab: str = "users"
    # The admin tables, loaded from relack.db into this tab only (they hold
    # private rooms, DMs and everyone's profile).
    profiles: list[UserProfile] = []
    rooms: list[RoomInfo] = []
    message_logs: list[ChatMessageLog] = []
    export_payload: str = ""
    import_payload: str = ""
    admin_accounts: list[str] = []
    audit: list[AuditEntry] = []
    # The admin account this tab entered as ("" with the passcode).
    _account: str = ""
    # Days messages are kept ("0": forever).
    retention_days: str = "0"

    @rx.event
    async def enter_as_account(self):
        """Admin accounts need no passcode."""
        auth = await self.get_state(AuthState)
        if permissions.is_admin(auth.user) and not self.is_authenticated:
            self.is_authenticated = True
            self._account = auth.user.username
            await (await self.get_state(GlobalLobbyState)).join_lobby()
            permission_state = await self.get_state(PermissionState)
            await permission_state.sync_from_lobby()
            self.load_admin_data()

    @rx.event
    async def set_account_admin(self, username: str, admin: bool):
        if not await self.still_admin():
            return
        profile = db.load_profiles().get(username)
        if admin and (profile is None or profile.is_guest):
            return rx.toast("Only Google accounts can be admins (guests have no password).")
        permissions.set_admin(username, admin)
        db.audit(self._account or "admin", "admin.grant" if admin else "admin.remove", username)
        self.admin_accounts = permissions.admins()

    @rx.event
    def set_passcode_input(self, value: str):
        # Explicit setter to avoid relying on deprecated state_auto_setters
        self.passcode_input = value

    @rx.event
    def set_active_tab(self, value: str):
        self.active_tab = value

    @rx.event
    def set_import_payload(self, value: str):
        self.import_payload = value

    async def still_admin(self) -> bool:
        """An account stops being admin as soon as that's taken away, open tabs included."""
        if self.is_authenticated and self._account:
            auth = await self.get_state(AuthState)
            if not permissions.is_admin(auth.user) or auth.user.username != self._account:
                self.logout()
        return self.is_authenticated

    def load_admin_data(self):
        if not self.is_authenticated:
            return
        self._fill_users_and_rooms()
        self._fill_messages()
        self._fill_audit()
        self.retention_days = str(db.get_setting("retention_days", 0) or 0)

    def _fill_audit(self):
        self.audit = db.audit_entries()

    @rx.event
    async def load_audit(self):
        if await self.still_admin():
            self._fill_audit()

    @rx.event
    def set_retention_days(self, value: str):
        self.retention_days = value

    @rx.event
    async def save_retention(self):
        if not await self.still_admin():
            return
        try:
            days = max(0, int(self.retention_days or 0))
        except ValueError:
            return rx.toast("Enter a number of days.")
        db.set_setting("retention_days", days)
        db.audit("admin", "retention.set", detail=f"{days} days")
        self._fill_audit()
        return rx.toast("Saved. Older messages are deleted within the hour." if days else "Messages are kept forever.")

    @rx.event
    async def load_users_and_rooms(self):
        if await self.still_admin():
            self._fill_users_and_rooms()

    def _fill_users_and_rooms(self):
        self.profiles = list(db.load_profiles().values())
        self.rooms = list(db.load_rooms().values())
        self.admin_accounts = permissions.admins()

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
            self.load_admin_data()
            return rx.toast("Admin access granted.")
        else:
            return rx.toast("Invalid Passcode")

    @rx.event
    async def load_messages(self):
        if await self.still_admin():
            self._fill_messages()

    def _fill_messages(self):
        rooms = db.load_rooms()
        names = db.display_names()
        self.message_logs = [
            ChatMessageLog(
                room_name=msg.room,
                room_title=db.room_title(rooms[msg.room], "", names) if msg.room in rooms else msg.room,
                message=msg,
            )
            for msg in db.recent_messages(200)
        ]

    def logout(self):
        self.is_authenticated = False
        self._account = ""
        self.passcode_input = ""
        self.active_tab = "users"
        self.profiles = []
        self.rooms = []
        self.message_logs = []
        self.export_payload = ""
        self.import_payload = ""

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
