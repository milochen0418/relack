import reflex as rx
from relack.states.auth_state import AuthState


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


def auth_container() -> rx.Component:
    return rx.el.div(
        guest_view(),
        class_name="bg-white rounded-2xl shadow-xl border border-gray-100 p-8 w-full max-w-md mx-auto",
    )