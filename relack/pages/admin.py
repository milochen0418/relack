import reflex as rx
from relack.states.admin_state import AdminState
from relack.states.shared_state import GlobalLobbyState
from relack.components.navbar import navbar

def login_panel():
    return rx.el.div(
        rx.el.a(
            rx.el.div(
                rx.icon("arrow-left", class_name="h-4 w-4"),
                rx.el.span("Back", class_name="ml-2 font-medium"),
                class_name="flex items-center text-gray-500 hover:text-violet-600 transition-colors",
            ),
            href="/",
            class_name="absolute top-6 left-6",
        ),
        rx.el.div(
            rx.el.h1("Admin Login", class_name="text-2xl font-bold text-gray-900 mb-6 text-center"),
            rx.el.div(
                rx.el.input(
                    placeholder="Enter Admin Passcode",
                    type="password",
                    value=AdminState.passcode_input,
                    on_change=AdminState.set_passcode_input,
                    class_name="w-full px-4 py-2 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent transition-all bg-gray-50 focus:bg-white",
                ),
                class_name="mb-4",
            ),
            rx.el.button(
                "Login",
                on_click=AdminState.check_passcode,
                class_name="w-full bg-violet-600 hover:bg-violet-700 text-white font-semibold py-2 px-4 rounded-xl transition-colors shadow-sm hover:shadow-md",
            ),
            class_name="bg-white p-8 rounded-2xl shadow-xl border border-gray-100 w-full max-w-md",
        ),
        class_name="min-h-[calc(100vh-80px)] flex items-center justify-center p-4 relative",
    )

def users_table():
    return rx.el.div(
        rx.el.h2("User Profiles", class_name="text-xl font-bold text-gray-800 mb-4"),
        rx.el.div(
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Username"),
                        rx.table.column_header_cell("Nickname"),
                        rx.table.column_header_cell("Email"),
                        rx.table.column_header_cell("Is Guest"),
                        rx.table.column_header_cell("Created At"),
                    )
                ),
                rx.table.body(
                    rx.foreach(
                        GlobalLobbyState.all_profiles,
                        lambda user: rx.table.row(
                            rx.table.cell(user.username),
                            rx.table.cell(user.nickname),
                            rx.table.cell(user.email),
                            rx.table.cell(rx.cond(user.is_guest, "True", "False")),
                            rx.table.cell(user.created_at),
                        ),
                    )
                ),
                variant="surface",
                width="100%",
            ),
            class_name="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden",
        ),
        class_name="space-y-4",
    )

def rooms_table():
    return rx.el.div(
        rx.el.h2("Active Rooms", class_name="text-xl font-bold text-gray-800 mb-4"),
        rx.el.div(
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Name"),
                        rx.table.column_header_cell("Description"),
                        rx.table.column_header_cell("Participants"),
                        rx.table.column_header_cell("Created By"),
                    )
                ),
                rx.table.body(
                    rx.foreach(
                        GlobalLobbyState.room_list,
                        lambda room: rx.table.row(
                            rx.table.cell(room.name),
                            rx.table.cell(room.description),
                            rx.table.cell(room.participant_count),
                            rx.table.cell(room.created_by),
                        ),
                    )
                ),
                variant="surface",
                width="100%",
            ),
            class_name="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden",
        ),
        class_name="space-y-4",
    )


def messages_table():
    return rx.el.div(
        rx.el.h2("Recent Messages", class_name="text-xl font-bold text-gray-800 mb-4"),
        rx.el.div(
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Room"),
                        rx.table.column_header_cell("Sender"),
                        rx.table.column_header_cell("Content"),
                        rx.table.column_header_cell("Time"),
                        rx.table.column_header_cell("Type"),
                    )
                ),
                rx.table.body(
                    rx.foreach(
                        GlobalLobbyState.recent_message_logs,
                        lambda log: rx.table.row(
                            rx.table.cell(log.room_name),
                            rx.table.cell(log.message.sender),
                            rx.table.cell(log.message.content),
                            rx.table.cell(log.message.timestamp),
                            rx.table.cell(rx.cond(log.message.is_system, "System", "User")),
                        ),
                    )
                ),
                variant="surface",
                width="100%",
            ),
            class_name="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden",
        ),
        class_name="space-y-4",
    )

def admin_dashboard():
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.h1("Admin Dashboard", class_name="text-2xl font-bold text-gray-900"),
                rx.el.button(
                    "Logout",
                    on_click=AdminState.logout,
                    class_name="px-4 py-2 bg-red-50 text-red-600 hover:bg-red-100 rounded-lg font-medium transition-colors",
                ),
                class_name="flex items-center justify-between mb-8",
            ),
            rx.tabs.root(
                rx.tabs.list(
                    rx.tabs.trigger("Users", value="users"),
                    rx.tabs.trigger("Rooms", value="rooms"),
                    rx.tabs.trigger("Messages", value="messages"),
                ),
                rx.tabs.content(
                    users_table(),
                    value="users",
                    class_name="mt-6",
                ),
                rx.tabs.content(
                    rooms_table(),
                    value="rooms",
                    class_name="mt-6",
                ),
                rx.tabs.content(
                    messages_table(),
                    value="messages",
                    class_name="mt-6",
                ),
                default_value="users",
                width="100%",
            ),
            class_name="max-w-6xl mx-auto px-4 py-8",
        ),
        class_name="min-h-[calc(100vh-80px)]",
    )

def admin_page():
    return rx.el.div(
        rx.el.div(
            navbar(),
            rx.cond(
                AdminState.is_authenticated,
                admin_dashboard(),
                login_panel(),
            ),
            class_name="min-h-screen bg-gray-50/50 font-sans",
        )
    )
