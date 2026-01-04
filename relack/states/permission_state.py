import reflex as rx


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

    @rx.event
    def set_google_requires_approval(self, value: bool):
        self.google_requires_approval = value

    @rx.event
    def set_guest_requires_approval(self, value: bool):
        self.guest_requires_approval = value

    @rx.event
    def set_guest_can_create_room(self, value: bool):
        self.guest_can_create_room = value

    @rx.event
    def set_guest_can_mention_users(self, value: bool):
        self.guest_can_mention_users = value

    @rx.event
    def set_guest_can_view_profiles(self, value: bool):
        self.guest_can_view_profiles = value

    @rx.event
    def set_google_can_create_room(self, value: bool):
        self.google_can_create_room = value

    @rx.event
    def set_google_can_mention_users(self, value: bool):
        self.google_can_mention_users = value

    @rx.event
    def set_google_can_view_profiles(self, value: bool):
        self.google_can_view_profiles = value

    @rx.event
    def save_permissions(self):
        return rx.toast("Permissions saved (UI only). Wire to enforcement as needed.")

    @rx.event
    def reset_permissions(self):
        self.google_requires_approval = True
        self.guest_requires_approval = True
        self.guest_can_create_room = False
        self.guest_can_mention_users = False
        self.guest_can_view_profiles = False
        self.google_can_create_room = False
        self.google_can_mention_users = False
        self.google_can_view_profiles = False
        return rx.toast("Permissions reset to defaults.")
