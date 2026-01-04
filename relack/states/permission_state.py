import reflex as rx
from relack.models import PermissionConfig


class PermissionState(rx.State):
    """Local admin-only permissions configuration (UI scaffold).

    Note: These toggles are stored client-side only until wiring is added
    to enforce them in the rest of the app.
    """

    google_requires_approval: bool = True
    guest_requires_approval: bool = True
    guest_can_create_room: bool = False
    guest_can_mention_users: bool = False
    guest_can_view_profiles: bool = False
    google_can_create_room: bool = False
    google_can_mention_users: bool = False
    google_can_view_profiles: bool = False

    def _to_config(self) -> PermissionConfig:
        return PermissionConfig(
            google_requires_approval=self.google_requires_approval,
            guest_requires_approval=self.guest_requires_approval,
            guest_can_create_room=self.guest_can_create_room,
            guest_can_mention_users=self.guest_can_mention_users,
            guest_can_view_profiles=self.guest_can_view_profiles,
            google_can_create_room=self.google_can_create_room,
            google_can_mention_users=self.google_can_mention_users,
            google_can_view_profiles=self.google_can_view_profiles,
        )

    async def _update_lobby_permissions(self):
        from relack.states.shared_state import GlobalLobbyState  # noqa: WPS433

        lobby = await self.get_state(GlobalLobbyState)
        lobby._permissions = self._to_config()

    async def _set_from_config(self, config: PermissionConfig):
        self.google_requires_approval = config.google_requires_approval
        self.guest_requires_approval = config.guest_requires_approval
        self.guest_can_create_room = config.guest_can_create_room
        self.guest_can_mention_users = config.guest_can_mention_users
        self.guest_can_view_profiles = config.guest_can_view_profiles
        self.google_can_create_room = config.google_can_create_room
        self.google_can_mention_users = config.google_can_mention_users
        self.google_can_view_profiles = config.google_can_view_profiles

    @rx.event
    async def sync_from_lobby(self):
        from relack.states.shared_state import GlobalLobbyState  # noqa: WPS433

        lobby = await self.get_state(GlobalLobbyState)
        config = lobby._permissions if hasattr(lobby, "_permissions") and lobby._permissions else PermissionConfig()
        await self._set_from_config(config)

    @rx.event
    async def set_google_requires_approval(self, value: bool):
        self.google_requires_approval = value
        await self._update_lobby_permissions()

    @rx.event
    async def set_guest_requires_approval(self, value: bool):
        self.guest_requires_approval = value
        await self._update_lobby_permissions()

    @rx.event
    async def set_guest_can_create_room(self, value: bool):
        self.guest_can_create_room = value
        await self._update_lobby_permissions()

    @rx.event
    async def set_guest_can_mention_users(self, value: bool):
        self.guest_can_mention_users = value
        await self._update_lobby_permissions()

    @rx.event
    async def set_guest_can_view_profiles(self, value: bool):
        self.guest_can_view_profiles = value
        await self._update_lobby_permissions()

    @rx.event
    async def set_google_can_create_room(self, value: bool):
        self.google_can_create_room = value
        await self._update_lobby_permissions()

    @rx.event
    async def set_google_can_mention_users(self, value: bool):
        self.google_can_mention_users = value
        await self._update_lobby_permissions()

    @rx.event
    async def set_google_can_view_profiles(self, value: bool):
        self.google_can_view_profiles = value
        await self._update_lobby_permissions()

    @rx.event
    async def save_permissions(self):
        await self._update_lobby_permissions()
        return rx.toast("Permissions saved.")

    @rx.event
    async def reset_permissions(self):
        await self._set_from_config(PermissionConfig())
        await self._update_lobby_permissions()
        return rx.toast("Permissions reset to defaults.")
