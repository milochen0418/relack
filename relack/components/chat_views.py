import reflex as rx
from relack.states.shared_state import GlobalLobbyState, RoomState
from relack.states.auth_state import AuthState
from relack.models import RoomInfo, ChatMessage, UserProfile


class CreateRoomState(rx.State):
    name: str = ""
    description: str = ""
    is_open: bool = False

    def set_name(self, name: str):
        self.name = name

    def set_description(self, description: str):
        self.description = description

    def set_is_open(self, is_open: bool):
        self.is_open = is_open

    @rx.event
    def toggle(self):
        self.is_open = not self.is_open
        self.name = ""
        self.description = ""

    @rx.event
    def create(self):
        yield GlobalLobbyState.create_room(self.name, self.description)
        self.is_open = False


def room_card(room: RoomInfo) -> rx.Component:
    return rx.el.div(
        rx.el.button(
            rx.el.div(
                rx.el.div(
                    rx.el.div(
                        rx.el.h3(room.name, class_name="font-semibold text-gray-900"),
                        class_name="flex items-center gap-1",
                    ),
                    class_name="flex items-center justify-between mb-1",
                ),
                rx.el.p(
                    room.description,
                    class_name="text-xs text-gray-500 text-left truncate",
                ),
                class_name="w-full",
            ),
            on_click=lambda: RoomState.handle_join_room(room.name),
            class_name="w-full text-left",
        ),
        rx.cond(
            (AuthState.user.username == room.created_by)
            & (AuthState.user.username != ""),
            rx.el.button(
                rx.icon("trash-2", class_name="h-4 w-4"),
                on_click=lambda: GlobalLobbyState.delete_room(room.name),
                class_name="absolute right-2 bottom-2 p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors opacity-0 group-hover:opacity-100",
            ),
        ),
        class_name=rx.cond(
            RoomState.room_name == room.name,
            "relative group w-full p-3 bg-violet-50 border border-violet-200 rounded-xl transition-all ring-1 ring-violet-200",
            "relative group w-full p-3 bg-white border border-gray-100 rounded-xl hover:border-violet-200 hover:shadow-sm transition-all",
        ),
    )


def create_room_modal() -> rx.Component:
    return rx.radix.primitives.dialog.root(
        rx.radix.primitives.dialog.portal(
            rx.radix.primitives.dialog.overlay(
                class_name="fixed inset-0 bg-black/50 backdrop-blur-sm z-[90]"
            ),
            rx.radix.primitives.dialog.content(
                rx.radix.primitives.dialog.title(
                    "Create New Room", class_name="text-lg font-bold mb-4"
                ),
                rx.el.div(
                    rx.el.label(
                        "Room Name",
                        class_name="text-sm font-medium text-gray-700 mb-1 block",
                    ),
                    rx.el.input(
                        placeholder="e.g. Design Team",
                        on_change=CreateRoomState.set_name,
                        class_name="w-full px-3 py-2 border rounded-lg mb-4",
                    ),
                    rx.el.label(
                        "Description",
                        class_name="text-sm font-medium text-gray-700 mb-1 block",
                    ),
                    rx.el.input(
                        placeholder="What is this room for?",
                        on_change=CreateRoomState.set_description,
                        class_name="w-full px-3 py-2 border rounded-lg mb-6",
                    ),
                    rx.el.div(
                        rx.radix.primitives.dialog.close(
                            rx.el.button(
                                "Cancel",
                                on_click=CreateRoomState.toggle,
                                class_name="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg mr-2",
                            )
                        ),
                        rx.el.button(
                            "Create Room",
                            on_click=CreateRoomState.create,
                            class_name="px-4 py-2 bg-violet-600 text-white rounded-lg hover:bg-violet-700",
                        ),
                        class_name="flex justify-end",
                    ),
                    class_name="bg-white p-6 rounded-2xl w-full shadow-2xl",
                ),
                class_name="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-2xl w-full max-w-sm z-[100] p-6",
            ),
        ),
        open=CreateRoomState.is_open,
        on_open_change=CreateRoomState.set_is_open,
    )


def sidebar() -> rx.Component:
    return rx.el.aside(
        rx.el.div(
            rx.el.div(
                rx.el.h2("Rooms", class_name="text-lg font-bold text-gray-800"),
                rx.el.button(
                    rx.icon("plus", class_name="h-5 w-5"),
                    on_click=CreateRoomState.toggle,
                    class_name="p-1.5 rounded-lg bg-violet-50 text-violet-600 hover:bg-violet-100 transition-colors",
                ),
                class_name="flex items-center justify-between mb-4",
            ),
            rx.el.div(
                rx.el.input(
                    placeholder="Search rooms...",
                    class_name="w-full px-3 py-2.5 bg-gray-50 rounded-xl text-sm border-none focus:ring-1 focus:ring-violet-500 placeholder:text-gray-400",
                ),
                class_name="mb-4",
            ),
            rx.el.div(
                rx.foreach(GlobalLobbyState.room_list, room_card),
                class_name="flex flex-col gap-2 overflow-y-auto flex-1 pr-1",
            ),
            class_name="p-4 h-full flex flex-col",
        ),
        create_room_modal(),
        class_name=rx.cond(
            RoomState.is_sidebar_open,
            "w-72 bg-white border-r border-gray-200 h-full flex flex-col transition-all duration-300 ease-in-out shrink-0",
            "w-0 overflow-hidden h-full flex flex-col transition-all duration-300 ease-in-out shrink-0",
        ),
    )


def message_bubble(msg: ChatMessage) -> rx.Component:
    is_me = (msg.sender == AuthState.user.username) | (
        msg.sender == AuthState.user.nickname
    )
    display_name = rx.cond(
        msg.display_name != "",
        msg.display_name,
        msg.sender,
    )
    avatar_seed = rx.cond(
        RoomState.avatar_seed_map.get(msg.sender, "") != "",
        RoomState.avatar_seed_map.get(msg.sender, ""),
        msg.sender,
    )
    return rx.el.div(
        rx.cond(
            msg.is_system,
            rx.el.div(
                rx.el.span(
                    msg.content,
                    class_name="text-xs text-gray-400 bg-gray-100/80 backdrop-blur-sm px-3 py-1 rounded-full border border-gray-200/50",
                ),
                class_name="flex justify-center my-4",
            ),
            rx.el.div(
                rx.cond(
                    ~is_me,
                    rx.el.a(
                        rx.image(
                                src=f"https://api.dicebear.com/9.x/notionists/svg?seed={avatar_seed}",
                            class_name="size-8 rounded-full bg-white border border-gray-100 shadow-sm hover:scale-105 transition-transform",
                        ),
                        href=f"/profile/{msg.sender}",
                        class_name="mr-2 self-end mb-1",
                    ),
                ),
                rx.el.div(
                    rx.el.div(
                        rx.cond(
                            ~is_me,
                            rx.el.span(
                                    display_name,
                                class_name="text-xs font-semibold text-gray-500 mb-1 ml-1 block",
                            ),
                        ),
                        rx.el.div(
                            rx.el.p(msg.content, class_name="text-sm leading-relaxed"),
                            rx.el.span(
                                msg.timestamp,
                                class_name=rx.cond(
                                    is_me,
                                    "text-[10px] text-violet-200 mt-1 block text-right opacity-80",
                                    "text-[10px] text-gray-400 mt-1 block text-right",
                                ),
                            ),
                            class_name=rx.cond(
                                is_me,
                                "bg-gradient-to-br from-violet-600 to-indigo-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 max-w-md shadow-sm",
                                "bg-white border border-gray-100 text-gray-800 rounded-2xl rounded-tl-sm px-4 py-2.5 max-w-md shadow-sm",
                            ),
                        ),
                    ),
                    class_name=rx.cond(
                        is_me, "flex flex-col items-end", "flex flex-col items-start"
                    ),
                ),
                class_name=rx.cond(
                    is_me, "flex justify-end mb-4", "flex justify-start mb-4"
                ),
            ),
        ),
        class_name="w-full animate-in fade-in slide-in-from-bottom-2 duration-300",
    )


def user_list_item(user: UserProfile) -> rx.Component:
    return rx.el.a(
        rx.el.div(
            rx.image(
                src=f"https://api.dicebear.com/9.x/notionists/svg?seed={user.avatar_seed}",
                class_name="size-8 rounded-full bg-violet-100",
            ),
            rx.el.div(
                rx.el.div(
                    rx.el.span(
                        rx.cond(user.nickname != "", user.nickname, user.username),
                        class_name="text-sm font-medium text-gray-900 truncate max-w-[120px]",
                    ),
                    rx.cond(
                        ~user.is_guest,
                        rx.icon(
                            "badge-check", class_name="h-3.5 w-3.5 text-blue-500 ml-1"
                        ),
                    ),
                    class_name="flex items-center",
                ),
                rx.el.span("Online", class_name="text-xs text-green-600 font-medium"),
                class_name="flex flex-col ml-3",
            ),
            class_name="flex items-center",
        ),
        href=f"/profile/{user.username}",
        class_name="flex items-center p-2 rounded-xl hover:bg-gray-50 transition-colors cursor-pointer",
    )


def users_panel() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.h3(
                "Online Users",
                class_name="text-sm font-bold text-gray-900 uppercase tracking-wider",
            ),
            class_name="flex items-center justify-between mb-4 px-2",
        ),
        rx.el.div(
            rx.foreach(RoomState.online_users_list, user_list_item),
            class_name="flex flex-col gap-1 overflow-y-auto flex-1",
        ),
        class_name=rx.cond(
            RoomState.is_user_list_open,
            "w-64 bg-white border-l border-gray-200 h-full flex flex-col p-4 transition-all duration-300 ease-in-out shrink-0",
            "w-0 overflow-hidden h-full flex flex-col p-0 border-none transition-all duration-300 ease-in-out shrink-0",
        ),
    )


def chat_area() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.button(
                    rx.icon("panel-left", class_name="h-5 w-5"),
                    on_click=RoomState.toggle_sidebar,
                    class_name=f"p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors {rx.cond(RoomState.is_sidebar_open, 'text-violet-600 bg-violet-50', '')}",
                ),
                rx.el.div(
                    rx.el.h2(
                        RoomState.room_name,
                        class_name="text-lg font-bold text-gray-900",
                    ),
                    rx.cond(
                        RoomState.room_creator_username != "",
                        rx.cond(
                            RoomState.room_creator_username == "System",
                            rx.el.span(
                                "By " + RoomState.room_creator_display,
                                class_name="text-xs font-medium text-gray-500",
                            ),
                            rx.el.a(
                                rx.el.span(
                                    "By " + RoomState.room_creator_display,
                                    class_name="text-xs font-medium text-gray-500 hover:text-gray-700 hover:underline",
                                ),
                                href="/profile/" + RoomState.room_creator_username,
                                class_name="text-xs text-gray-500",
                            ),
                        ),
                    ),
                    class_name="flex items-center gap-3 ml-4",
                ),
                class_name="flex items-center",
            ),
            rx.el.div(
                rx.el.button(
                    rx.icon("users", class_name="h-5 w-5"),
                    on_click=RoomState.toggle_user_list,
                    class_name=f"p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors mr-2 {rx.cond(RoomState.is_user_list_open, 'text-violet-600 bg-violet-50', '')}",
                ),
                rx.el.button(
                    rx.icon("log-out", class_name="h-5 w-5"),
                    on_click=RoomState.handle_leave_room,
                    class_name="text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors p-2 rounded-lg",
                ),
                class_name="flex items-center",
            ),
            class_name="h-16 border-b border-gray-200 flex items-center justify-between px-4 bg-white/80 backdrop-blur-sm sticky top-0 z-10",
        ),
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    rx.foreach(RoomState.messages, message_bubble),
                    class_name="flex-1 overflow-y-auto p-6 flex flex-col",
                ),
                rx.el.div(
                    rx.el.form(
                        rx.el.div(
                            rx.el.input(
                                placeholder="Type a message...",
                                name="message",
                                autocomplete="off",
                                class_name="flex-1 bg-gray-50 border-0 focus:ring-0 rounded-xl px-4 py-3 text-gray-900 placeholder:text-gray-400",
                            ),
                            rx.el.button(
                                rx.icon("send", class_name="h-5 w-5"),
                                type="submit",
                                class_name="bg-violet-600 hover:bg-violet-700 text-white p-3 rounded-xl transition-all shadow-sm active:scale-95",
                            ),
                            class_name="flex items-center gap-3 bg-white p-2 rounded-2xl border border-gray-200 shadow-sm focus-within:ring-2 focus-within:ring-violet-500/20 focus-within:border-violet-500 transition-all",
                        ),
                        on_submit=RoomState.send_message,
                        reset_on_submit=True,
                        class_name="w-full max-w-4xl mx-auto",
                    ),
                    class_name="p-6 bg-white border-t border-gray-200",
                ),
                class_name="flex-1 flex flex-col h-full overflow-hidden bg-[#FAFAFA] min-w-0",
            ),
            users_panel(),
            class_name="flex-1 flex overflow-hidden",
        ),
        class_name="flex-1 flex flex-col h-full bg-[#FAFAFA] overflow-hidden",
    )


def empty_state() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.icon("message-square-dashed", class_name="h-16 w-16 text-gray-300 mb-4"),
            rx.el.h3(
                "No Room Selected", class_name="text-xl font-bold text-gray-900 mb-2"
            ),
            rx.el.p(
                "Choose a room from the sidebar to start chatting.",
                class_name="text-gray-500 max-w-sm",
            ),
            class_name="flex flex-col items-center text-center",
        ),
        class_name="flex-1 flex items-center justify-center bg-gray-50/50",
    )


def chat_dashboard() -> rx.Component:
    return rx.el.div(
        sidebar(),
        rx.cond(RoomState.in_room, chat_area(), empty_state()),
        class_name="flex h-[calc(100vh-73px)] overflow-hidden bg-gray-50/50",
        # Ensure lobby link exists so room list is populated even after reloads.
        on_mount=[GlobalLobbyState.join_lobby, RoomState.rejoin_last_room, RoomState.heartbeat, RoomState.seed_all_room_read_counts],
        on_focus=RoomState.heartbeat,
        on_mouse_enter=RoomState.heartbeat,
        on_mouse_move=RoomState.heartbeat,
        tab_index=0,
    )