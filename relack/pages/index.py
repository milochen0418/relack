import reflex as rx
from relack.components.navbar import navbar
from relack.components.auth_views import auth_container
from relack.components.chat_views import chat_dashboard
from relack.states.auth_state import AuthState
from relack.states.shared_state import GlobalLobbyState
from reflex_google_auth import google_oauth_provider


def welcome_hero() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.h1(
                "Relack: Real-Time Chat Evolved.",
                class_name="text-4xl md:text-6xl font-bold text-gray-900 tracking-tight mb-6",
            ),
            rx.el.p(
                "Join rooms, meet people, and chat in real-time with Relack. Choose your identity or jump in as a guest.",
                class_name="text-lg text-gray-600 max-w-2xl mx-auto mb-12",
            ),
            auth_container(),
            class_name="max-w-4xl mx-auto text-center px-4",
        ),
        class_name="min-h-[calc(100vh-80px)] flex items-center justify-center py-20",
    )


def index() -> rx.Component:
    return rx.el.div(
        google_oauth_provider(
            rx.el.div(
                navbar(),
                rx.cond(AuthState.user, chat_dashboard(), welcome_hero()),
                class_name="min-h-screen bg-gray-50/50 font-sans",
                on_mount=[GlobalLobbyState.join_lobby, AuthState.check_google_auth],
            )
        )
    )