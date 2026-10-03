import reflex as rx
from reflex_ddns_auth.intent import Intent, IntentPage
from relack.models import UserProfile
from relack.states.people_state import PeopleState


def member_row(member: UserProfile) -> rx.Component:
    return rx.el.button(
        rx.image(
            src=f"https://api.dicebear.com/9.x/notionists/svg?seed={member.avatar_seed}",
            class_name="size-10 rounded-full bg-violet-100 shrink-0",
        ),
        rx.el.div(
            rx.el.div(
                rx.el.span(
                    rx.cond(member.nickname != "", member.nickname, member.username),
                    class_name="text-sm font-semibold text-gray-900 truncate",
                ),
                rx.icon("badge-check", class_name="h-4 w-4 text-blue-500 ml-1 shrink-0"),
                class_name="flex items-center min-w-0",
            ),
            rx.el.span(member.email, class_name="text-xs text-gray-500 truncate"),
            class_name="flex flex-col ml-3 min-w-0 text-left",
        ),
        rx.cond(
            ~IntentPage.is_active,
            rx.icon("message-circle", class_name="h-5 w-5 text-violet-500 ml-auto shrink-0"),
        ),
        on_click=PeopleState.select_member(member.username),
        class_name="w-full flex items-center p-3 rounded-xl border border-gray-100 bg-white hover:border-violet-200 hover:shadow-sm transition-all",
    )


def people_view() -> rx.Component:
    """List of verified members; picking one answers the caller when opened as an intent."""
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.h2(
                    rx.cond(IntentPage.is_active, "Pick a member", "People"),
                    class_name="text-xl font-bold text-gray-900",
                ),
                rx.el.p(
                    "Verified members · ",
                    PeopleState.members.length(),
                    class_name="text-sm text-gray-500",
                ),
            ),
            rx.cond(
                ~IntentPage.is_active,
                rx.el.button(
                    rx.icon("user-search", class_name="h-4 w-4 mr-2"),
                    "Pick member",
                    on_click=Intent.start(
                        "relack", "people.pick", on_result=PeopleState.show_picked_profile
                    ),
                    class_name="flex items-center px-3 py-2 text-sm font-medium rounded-lg bg-violet-50 text-violet-600 hover:bg-violet-100 transition-colors",
                ),
            ),
            class_name=rx.cond(
                IntentPage.is_active,
                "flex items-center justify-between mb-4 pr-10",
                "flex items-center justify-between mb-4",
            ),
        ),
        rx.el.input(
            placeholder="Search people...",
            value=PeopleState.search,
            on_change=PeopleState.set_search,
            class_name="w-full px-3 py-2.5 mb-4 bg-gray-50 rounded-xl text-sm border-none focus:ring-1 focus:ring-violet-500 placeholder:text-gray-400",
        ),
        rx.cond(
            PeopleState.filtered_members.length() > 0,
            rx.el.div(
                rx.foreach(PeopleState.filtered_members, member_row),
                class_name="flex flex-col gap-2",
            ),
            rx.el.div(
                rx.icon("users", class_name="h-12 w-12 text-gray-300 mb-3"),
                rx.el.p(
                    rx.cond(PeopleState.is_loading, "Loading...", "No verified members found."),
                    class_name="text-gray-500",
                ),
                class_name="flex flex-col items-center justify-center py-12",
            ),
        ),
        class_name=rx.cond(
            IntentPage.is_active,
            "p-6 bg-white",
            "w-full max-w-2xl mx-auto p-6",
        ),
    )
