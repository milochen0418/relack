import reflex as rx
from relack.states.auth_state import AuthState
from reflex_google_auth import google_login


def input_field(
    label: str,
    placeholder: str,
    value_var: rx.Var,
    on_change_event,
    type_: str = "text",
) -> rx.Component:
    return rx.el.div(
        rx.el.label(label, class_name="block text-sm font-medium text-gray-700 mb-1.5"),
        rx.el.input(
            type=type_,
            placeholder=placeholder,
            default_value=value_var,
            on_change=on_change_event,
            class_name="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:border-violet-500 focus:ring-2 focus:ring-violet-500/20 outline-none transition-all bg-gray-50/50 focus:bg-white text-gray-900 placeholder:text-gray-400",
        ),
        class_name="mb-4",
    )


def guest_view() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.icon("ghost", class_name="h-10 w-10 text-violet-500 mb-4"),
            rx.el.h3("Guest Access", class_name="text-xl font-bold text-gray-900 mb-2"),
            rx.el.p(
                "Join the conversation quickly with a temporary nickname.",
                class_name="text-gray-500 mb-6 text-center",
            ),
            class_name="flex flex-col items-center",
        ),
        input_field(
            "Nickname",
            "CoolPanda99",
            AuthState.guest_nickname,
            AuthState.set_guest_nickname,
        ),
        rx.el.button(
            "Continue as Guest",
            on_click=AuthState.handle_guest_login,
            class_name="w-full bg-violet-600 hover:bg-violet-700 text-white font-medium py-2.5 rounded-xl transition-all shadow-sm hover:shadow-md active:scale-[0.98]",
        ),
    )


def google_signin_view() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.icon("brain_cog", class_name="h-10 w-10 text-indigo-500 mb-4"),
            rx.el.h3(
                "Sign In with Google", class_name="text-xl font-bold text-gray-900 mb-2"
            ),
            rx.el.p(
                "Use your Google account to access your permanent profile.",
                class_name="text-gray-500 mb-6 text-center",
            ),
            class_name="flex flex-col items-center",
        ),
        rx.el.div(
            google_login(on_success=AuthState.check_google_auth),
            class_name="flex justify-center w-full py-2",
        ),
        class_name="w-full",
    )


def google_registration_view() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.icon("user-check", class_name="h-10 w-10 text-emerald-500 mb-4"),
            rx.el.h3(
                "Finish Profile", class_name="text-xl font-bold text-gray-900 mb-2"
            ),
            rx.el.p(
                "Complete your registration by choosing a nickname.",
                class_name="text-gray-500 mb-6 text-center",
            ),
            class_name="flex flex-col items-center",
        ),
        input_field(
            "Email (Username)",
            "your@email.com",
            AuthState.reg_username,
            AuthState.set_reg_username,
        ),
        input_field(
            "Nickname",
            "Choose a display name",
            AuthState.reg_nickname,
            AuthState.set_reg_nickname,
        ),
        input_field(
            "Bio (Optional)",
            "Tell us about yourself",
            AuthState.reg_bio,
            AuthState.set_reg_bio,
        ),
        rx.el.button(
            "Create Profile",
            on_click=AuthState.finish_google_registration,
            class_name="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-medium py-2.5 rounded-xl transition-all shadow-sm hover:shadow-md active:scale-[0.98]",
        ),
    )


def auth_container() -> rx.Component:
    return rx.el.div(
        rx.cond(
            AuthState.token_is_valid & AuthState.requires_registration,
            google_registration_view(),
            rx.el.div(
                rx.el.div(
                    rx.el.button(
                        "Guest",
                        on_click=lambda: AuthState.set_auth_view("guest"),
                        class_name=rx.cond(
                            AuthState.auth_view == "guest",
                            "flex-1 py-2 text-sm font-medium text-violet-700 border-b-2 border-violet-600",
                            "flex-1 py-2 text-sm font-medium text-gray-500 hover:text-gray-700",
                        ),
                    ),
                    rx.el.button(
                        "Google Login",
                        on_click=lambda: AuthState.set_auth_view("google"),
                        class_name=rx.cond(
                            AuthState.auth_view == "google",
                            "flex-1 py-2 text-sm font-medium text-indigo-700 border-b-2 border-indigo-600",
                            "flex-1 py-2 text-sm font-medium text-gray-500 hover:text-gray-700",
                        ),
                    ),
                    class_name="flex border-b border-gray-200 mb-6",
                ),
                rx.match(
                    AuthState.auth_view,
                    ("guest", guest_view()),
                    ("google", google_signin_view()),
                    guest_view(),
                ),
            ),
        ),
        class_name="bg-white rounded-2xl shadow-xl border border-gray-100 p-8 w-full max-w-md mx-auto",
    )