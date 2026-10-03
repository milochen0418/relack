import reflex as rx
from reflex_ddns_auth.intent import Intent, IntentPage
from relack.models import UserProfile
from relack.states.shared_state import GlobalLobbyState


class PeopleState(rx.State):
    """Directory of verified members (Google accounts) known to this site."""

    members: list[UserProfile] = []
    search: str = ""
    is_loading: bool = False

    @rx.var
    def filtered_members(self) -> list[UserProfile]:
        query = self.search.strip().lower()
        if not query:
            return self.members
        return [
            m
            for m in self.members
            if query in m.username.lower()
            or query in m.nickname.lower()
            or query in m.email.lower()
        ]

    @rx.event
    def set_search(self, value: str):
        self.search = value

    @rx.event
    async def load_members(self):
        self.is_loading = True
        lobby = await self.get_state(GlobalLobbyState)
        lobby_linked = await lobby._link_to("global-lobby")
        self.members = sorted(
            (p for p in lobby_linked._known_profiles.values() if not p.is_guest),
            key=lambda p: (p.nickname or p.username).lower(),
        )
        self.is_loading = False

    @rx.event
    async def open_intent(self, params: dict):
        """Entry point of the `people.pick` intent opened by other apps."""
        self.search = params.get("q", "")
        await self.load_members()

    @rx.event
    async def select_member(self, username: str):
        """Answer the caller when picking inside an intent dialog, else show the profile."""
        page = await self.get_state(IntentPage)
        if page.is_active:
            member = next((m for m in self.members if m.username == username), None)
            if member is None:
                return
            return IntentPage.finish(
                {
                    "user": member.username,
                    "email": member.email,
                    "nickname": member.nickname,
                    "avatar_seed": member.avatar_seed,
                }
            )
        return Intent.start("relack", "profile.view", user=username)

    @rx.event
    def show_picked_profile(self, data: dict):
        """`people.pick` result handler: open the picked member's profile."""
        user = data.get("user", "")
        if user:
            return Intent.start("relack", "profile.view", user=user)
