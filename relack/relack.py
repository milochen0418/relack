import reflex as rx
from relack.pages.index import index
from relack.pages.profile import profile
from relack.pages.admin import admin_page

app = rx.App(
    theme=rx.theme(appearance="light"),
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
    ],
    head_components=[
        rx.el.link(rel="preconnect", href="https://fonts.googleapis.com"),
        rx.el.link(rel="preconnect", href="https://fonts.gstatic.com", cross_origin=""),
    ],
)
app.add_page(index, route="/", title="Relack - Reflex Real-Time Chat")
app.add_page(profile, route="/profile/[username]", title="User Profile")
app.add_page(admin_page, route="/admin-dashboard", title="Admin Dashboard")