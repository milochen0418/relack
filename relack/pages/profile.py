import reflex as rx
from relack.components.navbar import navbar
from relack.components.profile_views import profile_view
from relack.states.profile_state import ProfileState


def profile() -> rx.Component:
    return rx.el.div(
        navbar(),
        profile_view(),
        class_name="min-h-screen bg-gray-50/50 font-sans",
        on_mount=ProfileState.get_profile,
    )