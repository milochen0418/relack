import reflex as rx
from relack.pages.index import index
from relack.pages.profile import profile
from relack.pages.admin import admin_page
from relack.auth.routes import auth_routes
from relack.components.profile_views import profile_view
from relack.states.profile_state import ProfileState
from relack.components.people_views import people_view
from relack.states.people_state import PeopleState
from reflex_ddns_auth.intent import install_intent_host, intent
from relack.components.chat_views import call_keepalive

app = rx.App(
    theme=rx.theme(appearance="light"),
    api_transformer=auth_routes,
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
    ],
    head_components=[
        rx.el.link(rel="preconnect", href="https://fonts.googleapis.com"),
        rx.el.link(rel="preconnect", href="https://fonts.gstatic.com", cross_origin=""),
    ],
)
# Intent dialogs (calls, pickers, profiles) live above every page, so a call in
# the tray keeps running while the user moves between pages.
install_intent_host(app)
app.extra_app_wraps[(8, "RelackCallKeepalive")] = lambda stateful: rx.fragment(call_keepalive())

app.add_page(index, route="/", title="Relack - Reflex Real-Time Chat")
# on_load (not on_mount): runs again when moving from one profile to another.
app.add_page(
    profile, route="/profile/[username]", title="User Profile", on_load=ProfileState.get_profile
)
app.add_page(admin_page, route="/admin-dashboard", title="Admin Dashboard")


# Pages other *.reflex-ddns.com apps can open as dialogs (DDNS Intent).
@intent(
    app,
    action="profile.view",
    on_open=ProfileState.open_intent,
    title="User Profile",
    params={"user": str},
    required=("user",),
)
def profile_intent() -> rx.Component:
    return profile_view()


@intent(
    app,
    action="people.pick",
    on_open=PeopleState.open_intent,
    title="Pick a Member",
    params={"q": str},
)
def people_intent() -> rx.Component:
    return people_view()
