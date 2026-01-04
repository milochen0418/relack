import reflex as rx
from relack.states.admin_state import AdminState
from relack.states.shared_state import GlobalLobbyState
from relack.states.profile_state import ProfileState
from relack.states.permission_state import PermissionState
from relack.components.profile_views import profile_view
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
                        rx.table.column_header_cell("More"),
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
                            rx.table.cell(
                                rx.button(
                                    "More",
                                    size="2",
                                    variant="soft",
                                    class_name="text-violet-700",
                                    on_click=lambda _: ProfileState.open_admin_profile(user.username),
                                )
                            ),
                        ),
                    )
                ),
                variant="surface",
                width="100%",
            ),
            class_name="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden",
        ),
        rx.dialog.root(
            rx.dialog.content(
                profile_view(),
                class_name="max-w-3xl w-[95vw] bg-transparent shadow-none border-0 p-0",  # profile_view has its own container
            ),
            open=ProfileState.is_admin_profile_modal_open,
            on_open_change=ProfileState.close_admin_profile,
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


def data_maintenance_card():
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.h3("Data Maintenance", class_name="text-lg font-semibold text-gray-900"),
                rx.el.p(
                    "Import, export, and clear data in one place.",
                    class_name="text-sm text-gray-500",
                ),
                class_name="space-y-1",
            ),
            class_name="flex items-start justify-between",
        ),
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    rx.el.h4("Clear Data", class_name="font-semibold text-gray-800"),
                    rx.el.p(
                        "Reset rooms, profiles, and message logs to defaults.",
                        class_name="text-sm text-gray-500",
                    ),
                    rx.el.button(
                        "Clear Data",
                        on_click=GlobalLobbyState.clear_all_data,
                        class_name="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium transition-colors shadow-sm w-fit",
                    ),
                    class_name="space-y-3",
                ),
                class_name="py-4",
            ),
            rx.el.div(
                rx.el.div(
                    rx.el.h4("Export Data", class_name="font-semibold text-gray-800"),
                    rx.el.p(
                        "Generate a JSON snapshot of rooms, profiles, and messages.",
                        class_name="text-sm text-gray-500",
                    ),
                    rx.el.div(
                        rx.el.button(
                            "Export Data",
                            on_click=GlobalLobbyState.export_data,
                            class_name="px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white rounded-lg font-medium transition-colors shadow-sm",
                        ),
                        class_name="flex items-center gap-3",
                    ),
                    rx.text_area(
                        value=GlobalLobbyState.export_payload,
                        read_only=True,
                        rows="8",
                        class_name="w-full font-mono text-sm bg-gray-50 border border-gray-200 rounded-lg p-3",
                        placeholder="Click Export Data to generate JSON",
                    ),
                    rx.el.div(
                        rx.button(
                            "Copy",
                            on_click=rx.set_clipboard(GlobalLobbyState.export_payload),
                            class_name="px-3 py-2 bg-gray-800 hover:bg-black text-white rounded-lg text-sm font-medium",
                        ),
                        class_name="flex justify-end",
                    ),
                    class_name="space-y-3",
                ),
                class_name="py-4 border-t border-gray-100",
            ),
            rx.el.div(
                rx.el.div(
                    rx.el.h4("Import Data", class_name="font-semibold text-gray-800"),
                    rx.el.p(
                        "Paste a JSON snapshot to restore rooms, profiles, and messages.",
                        class_name="text-sm text-gray-500",
                    ),
                    rx.text_area(
                        value=GlobalLobbyState.import_payload,
                        on_change=GlobalLobbyState.set_import_payload,
                        rows="8",
                        class_name="w-full font-mono text-sm bg-white border border-gray-200 rounded-lg p-3",
                        placeholder="Paste exported JSON here",
                    ),
                    rx.el.div(
                        rx.el.button(
                            "Import Data",
                            on_click=lambda: GlobalLobbyState.import_data(GlobalLobbyState.import_payload),
                            class_name="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-medium transition-colors shadow-sm",
                        ),
                        class_name="flex justify-end",
                    ),
                    class_name="space-y-3",
                ),
                class_name="py-4 border-t border-gray-100",
            ),
            rx.el.div(
                rx.el.div(
                    rx.el.h4("File Operations", class_name="font-semibold text-gray-800"),
                    rx.el.p(
                        "Download a JSON snapshot or import from a JSON file.",
                        class_name="text-sm text-gray-500",
                    ),
                    rx.el.div(
                        rx.button(
                            "Export Data to File",
                            on_click=GlobalLobbyState.export_data_to_file,
                            class_name="px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white rounded-lg font-medium transition-colors shadow-sm",
                        ),
                        class_name="mb-3",
                    ),
                    rx.el.div(
                        rx.upload(
                            rx.button(
                                "Import Data from File",
                                class_name="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-medium transition-colors shadow-sm",
                            ),
                            accept="application/json",
                            max_files=1,
                            on_drop=GlobalLobbyState.import_data_from_upload,
                        ),
                        class_name="flex items-center gap-3",
                    ),
                    class_name="space-y-3",
                ),
                class_name="py-4 border-t border-gray-100",
            ),
            class_name="space-y-0",
        ),
        class_name=rx.cond(
            AdminState.active_settings_anchor == "data-maintenance",
            "bg-white p-5 rounded-2xl border border-gray-100 shadow-sm space-y-2 ring-2 ring-violet-300",
            "bg-white p-5 rounded-2xl border border-gray-100 shadow-sm space-y-2",
        ),
        id="data-maintenance",
    )


def permission_toggle(label: str, description: str, checked, on_change):
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.span(label, class_name="text-sm font-medium text-gray-900"),
                rx.el.p(description, class_name="text-xs text-gray-500"),
                class_name="flex-1 space-y-1",
            ),
            rx.switch(
                checked=checked,
                on_change=on_change,
                class_name="data-[state=checked]:bg-violet-600",
            ),
            class_name="flex items-center justify-between gap-3",
        ),
        class_name="py-2",
    )


def permissions_card():
    return rx.el.div(
        rx.el.div(
            rx.el.h3("Permissions", class_name="text-lg font-semibold text-gray-900"),
            rx.el.p(
                "Define guest defaults and guardrails. (UI only for now)",
                class_name="text-sm text-gray-500",
            ),
            class_name="space-y-1",
        ),
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    rx.el.span("Roles", class_name="text-sm font-semibold text-gray-800"),
                    rx.el.p(
                        "Currently editing guest defaults. Extend for more roles later.",
                        class_name="text-xs text-gray-500",
                    ),
                    class_name="space-y-1",
                ),
                class_name="py-3",
            ),
            rx.el.div(
                rx.el.span("Registration Flow", class_name="text-xs font-semibold text-gray-500 uppercase tracking-wide"),
                permission_toggle(
                    "Google login requires admin approval",
                    "If off, Google users become registered immediately after login.",
                    PermissionState.google_requires_approval,
                    PermissionState.set_google_requires_approval,
                ),
                permission_toggle(
                    "Guest login requires admin approval",
                    "If off, guest users are auto-upgraded to registered on entry.",
                    PermissionState.guest_requires_approval,
                    PermissionState.set_guest_requires_approval,
                ),
                class_name="py-3 space-y-2",
            ),
            rx.el.div(
                rx.el.span("Guest Initial Permissions", class_name="text-xs font-semibold text-gray-500 uppercase tracking-wide"),
                permission_toggle(
                    "Can create rooms",
                    "Allow guests to create new rooms.",
                    PermissionState.guest_can_create_room,
                    PermissionState.set_guest_can_create_room,
                ),
                permission_toggle(
                    "Can @mention others",
                    "Let guests tag others inside rooms.",
                    PermissionState.guest_can_mention_users,
                    PermissionState.set_guest_can_mention_users,
                ),
                permission_toggle(
                    "Can view profiles",
                    "Allow guests to open other users' profiles.",
                    PermissionState.guest_can_view_profiles,
                    PermissionState.set_guest_can_view_profiles,
                ),
                class_name="py-3 space-y-2",
            ),
            rx.el.div(
                rx.el.span("Google Initial Permissions", class_name="text-xs font-semibold text-gray-500 uppercase tracking-wide"),
                permission_toggle(
                    "Can create rooms",
                    "Allow Google users to create new rooms.",
                    PermissionState.google_can_create_room,
                    PermissionState.set_google_can_create_room,
                ),
                permission_toggle(
                    "Can @mention others",
                    "Let Google users tag others inside rooms.",
                    PermissionState.google_can_mention_users,
                    PermissionState.set_google_can_mention_users,
                ),
                permission_toggle(
                    "Can view profiles",
                    "Allow Google users to open other users' profiles.",
                    PermissionState.google_can_view_profiles,
                    PermissionState.set_google_can_view_profiles,
                ),
                class_name="py-3 space-y-2",
            ),
            rx.el.div(
                rx.el.button(
                    "Save changes",
                    on_click=PermissionState.save_permissions,
                    class_name="px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white rounded-lg font-semibold transition-colors shadow-sm",
                ),
                rx.el.button(
                    "Reset",
                    on_click=PermissionState.reset_permissions,
                    class_name="px-3 py-2 text-sm font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-50 rounded-lg border border-gray-200",
                ),
                class_name="flex items-center gap-3 pt-3",
            ),
            class_name="space-y-3",
        ),
        class_name=rx.cond(
            AdminState.active_settings_anchor == "permissions",
            "bg-white p-5 rounded-2xl border border-gray-100 shadow-sm space-y-2 ring-2 ring-violet-300",
            "bg-white p-5 rounded-2xl border border-gray-100 shadow-sm space-y-2",
        ),
        id="permissions",
    )


def settings_panel():
    return rx.el.div(
        rx.el.h2("Settings", class_name="text-xl font-bold text-gray-800 mb-4"),
        rx.el.div(
            data_maintenance_card(),
            permissions_card(),
            class_name="grid gap-6 lg:grid-cols-2",
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
                rx.el.div(
                    rx.tabs.list(
                        rx.tabs.trigger("Users", value="users", on_click=AdminState.close_settings_menu),
                        rx.tabs.trigger("Rooms", value="rooms", on_click=AdminState.close_settings_menu),
                        rx.tabs.trigger("Messages", value="messages", on_click=AdminState.close_settings_menu),
                        rx.tabs.trigger(
                            rx.el.div(
                                rx.el.span("Settings", class_name="mr-1"),
                                rx.icon(
                                    "chevron-down",
                                    class_name="h-4 w-4 transition-transform",
                                    style={"transform": rx.cond(AdminState.is_settings_menu_open, "rotate(180deg)", "rotate(0deg)")},
                                ),
                                class_name="flex items-center",
                            ),
                            value="settings",
                            on_click=AdminState.toggle_settings_menu,
                            class_name="relative",
                        ),
                        class_name="relative w-full flex gap-6",
                    ),
                    rx.cond(
                        AdminState.is_settings_menu_open,
                        rx.el.div(
                            rx.el.button(
                                "Data Maintenance",
                                on_click=lambda: AdminState.go_to_settings_anchor("data-maintenance"),
                                class_name="w-48 text-left px-3 py-2 text-sm font-medium hover:bg-gray-50",
                            ),
                            rx.el.button(
                                "Permissions",
                                on_click=lambda: AdminState.go_to_settings_anchor("permissions"),
                                class_name="w-48 text-left px-3 py-2 text-sm font-medium hover:bg-gray-50",
                            ),
                            class_name="absolute right-0 mt-2 bg-white border border-gray-200 rounded-lg shadow-lg z-30 divide-y divide-gray-100",
                        ),
                    ),
                    class_name="relative block w-full sticky bg-white/95 backdrop-blur-md px-1 py-2 z-40",
                    style={"top": "72px"},
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
                rx.tabs.content(
                    settings_panel(),
                    value="settings",
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
