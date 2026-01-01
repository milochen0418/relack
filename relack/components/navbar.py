import reflex as rx
from relack.states.auth_state import AuthState
from relack.states.shared_state import GlobalLobbyState


def navbar() -> rx.Component:
    return rx.el.nav(
        rx.el.div(
            rx.el.div(
                rx.icon("message-circle", class_name="h-6 w-6 text-violet-600"),
                rx.el.div(
                    rx.el.span(
                        "Relack",
                        class_name="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-violet-600 to-indigo-600 leading-none",
                    ),
                    rx.el.span(
                        "Reflex Real-Time Chat",
                        class_name="text-[10px] text-gray-400 font-medium uppercase tracking-wider leading-none",
                    ),
                    class_name="flex flex-col",
                ),
                class_name="flex items-center gap-2",
            ),
            rx.el.div(
                rx.el.button(
                    rx.icon("link", class_name="h-4 w-4"),
                    rx.el.span("Copy Link", class_name="text-sm font-medium ml-2"),
                    on_click=[
                        rx.set_clipboard(AuthState.router.page.full_path),
                        rx.toast("Link copied to clipboard!", duration=3000),
                    ],
                    class_name="flex items-center px-4 py-2 mr-4 text-gray-500 hover:text-violet-600 hover:bg-violet-50 rounded-xl transition-all active:scale-95 border border-transparent hover:border-violet-100",
                ),
                rx.cond(
                    AuthState.user & ~AuthState.user.is_guest,
                    rx.el.button(
                        rx.icon("trash-2", class_name="h-4 w-4"),
                        rx.el.span("Clear DB", class_name="text-sm font-medium ml-2"),
                        on_click=GlobalLobbyState.clear_all_data,
                        class_name="flex items-center px-4 py-2 mr-4 text-red-500 hover:bg-red-50 rounded-xl transition-all active:scale-95 border border-transparent hover:border-red-100",
                    ),
                ),
                rx.cond(
                    AuthState.user,
                    rx.el.div(
                        rx.el.a(
                            rx.el.div(
                                rx.image(
                                    src=f"https://api.dicebear.com/9.x/notionists/svg?seed={AuthState.user.avatar_seed}",
                                    class_name="h-8 w-8 rounded-full bg-violet-100",
                                ),
                                rx.el.div(
                                    rx.el.span(
                                        rx.cond(
                                            AuthState.user.nickname != "",
                                            AuthState.user.nickname,
                                            AuthState.user.username,
                                        ),
                                        class_name="text-sm font-bold text-gray-900 leading-none",
                                    ),
                                    rx.el.div(
                                        rx.icon("ghost", class_name="h-3 w-3 mr-1"),
                                        rx.el.span(
                                            "已訪客登入",
                                            class_name="text-[10px] font-medium whitespace-nowrap",
                                        ),
                                        class_name="flex items-center text-violet-600 bg-violet-50 px-1.5 py-0.5 rounded-md mt-0.5",
                                    ),
                                    class_name="flex flex-col",
                                ),
                                class_name="flex items-center gap-3 px-4 py-2 rounded-2xl bg-white border border-gray-100 hover:border-violet-200 hover:shadow-sm transition-all",
                            ),
                            href=f"/profile/{AuthState.user.username}",
                        ),
                        rx.el.div(class_name="w-px h-8 bg-gray-100 mx-4"),
                        rx.el.button(
                            rx.el.div(
                                rx.icon("log-out", class_name="h-4 w-4"),
                                "Logout",
                                class_name="flex items-center gap-2",
                            ),
                            on_click=AuthState.logout,
                            class_name="text-sm font-medium text-gray-500 hover:text-red-600 transition-colors",
                        ),
                        class_name="flex items-center",
                    ),
                    rx.el.span(
                        "Not Connected", class_name="text-sm text-gray-400 italic"
                    ),
                ),
                class_name="flex items-center",
            ),
            class_name="flex items-center justify-between w-full max-w-7xl mx-auto",
        ),
        class_name="w-full bg-white/80 backdrop-blur-md border-b border-gray-200 px-6 py-4 sticky top-0 z-50",
    )