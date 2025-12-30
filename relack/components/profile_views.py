import reflex as rx
from relack.states.auth_state import AuthState


def profile_detail_item(label: str, value: str) -> rx.Component:
    return rx.el.div(
        rx.el.p(label, class_name="text-sm font-medium text-gray-500 mb-1"),
        rx.el.p(value, class_name="text-lg font-semibold text-gray-900"),
        class_name="mb-6",
    )


from relack.states.profile_state import ProfileState


def profile_view() -> rx.Component:
    user = ProfileState.current_profile
    return rx.el.div(
        rx.cond(
            ProfileState.is_loading,
            rx.el.div(
                rx.el.div(
                    class_name="animate-pulse bg-gray-200 h-64 rounded-2xl max-w-2xl mx-auto w-full"
                ),
                class_name="min-h-[calc(100vh-80px)] p-6 bg-gray-50 flex items-center justify-center",
            ),
            rx.cond(
                user,
                rx.el.div(
                    rx.el.div(
                        rx.el.div(
                            class_name="h-32 w-full bg-gradient-to-r from-violet-500 to-indigo-600 rounded-t-2xl"
                        ),
                        rx.el.div(
                            rx.image(
                                src=f"https://api.dicebear.com/9.x/notionists/svg?seed={user.avatar_seed}",
                                class_name="h-32 w-32 rounded-full border-4 border-white shadow-lg bg-white",
                            ),
                            class_name="absolute -bottom-16 left-8",
                        ),
                        class_name="relative mb-20",
                    ),
                    rx.el.div(
                        rx.el.div(
                            rx.el.h1(
                                rx.cond(
                                    user.nickname != "", user.nickname, user.username
                                ),
                                class_name="text-3xl font-bold text-gray-900 flex items-center gap-2",
                            ),
                            rx.cond(
                                ~user.is_guest,
                                rx.icon(
                                    "badge-check", class_name="h-6 w-6 text-blue-500"
                                ),
                            ),
                            class_name="flex items-center gap-2 mb-2",
                        ),
                        rx.el.p(
                            rx.cond(user.is_guest, "Guest User", "Verified Member"),
                            class_name="text-sm font-medium text-violet-600 bg-violet-50 px-3 py-1 rounded-full w-fit mb-8",
                        ),
                        rx.el.div(
                            profile_detail_item(
                                "Bio",
                                rx.cond(user.bio != "", user.bio, "No bio available"),
                            ),
                            profile_detail_item(
                                "Member Since",
                                rx.cond(
                                    user.created_at,
                                    user.created_at.split("T")[0],
                                    "Unknown",
                                ),
                            ),
                            profile_detail_item(
                                "Status", rx.cond(user.token, "Online", "Offline")
                            ),
                            rx.cond(
                                user.email != "",
                                profile_detail_item("Verified Email", user.email),
                            ),
                            class_name="grid grid-cols-1 md:grid-cols-2 gap-4",
                        ),
                        class_name="px-8 pb-8",
                    ),
                    class_name="bg-white rounded-2xl shadow-xl border border-gray-100 max-w-2xl mx-auto w-full animate-in fade-in zoom-in duration-300",
                ),
                rx.el.div(
                    rx.icon("user-x", class_name="h-16 w-16 text-gray-300 mb-4"),
                    rx.el.h2(
                        "User not found", class_name="text-xl font-bold text-gray-700"
                    ),
                    rx.el.p(
                        "This user has not joined the lobby yet or does not exist.",
                        class_name="text-gray-500 mt-2",
                    ),
                    class_name="flex flex-col items-center justify-center h-64 bg-white rounded-2xl shadow-sm border border-gray-100 max-w-2xl mx-auto w-full",
                ),
            ),
        ),
        class_name="min-h-[calc(100vh-80px)] p-6 bg-gray-50 flex items-center justify-center",
    )