import reflex as rx
from reflex.components.react_router.dom import ReactRouterLink
from relack.states.shared_state import GlobalLobbyState, LocalUIState, RoomState, TabSessionState
from relack.states.auth_state import AuthState
from relack.models import RoomInfo, ChatMessage, IncomingCall, MessagePart, UserProfile
from relack.states.call_state import CallState
from relack.components.people_views import people_view
from relack.states.people_state import PeopleState
from reflex_ddns_auth.intent import Intent


class CreateRoomState(rx.State):
    name: str = ""
    description: str = ""
    is_open: bool = False
    is_private: bool = False
    # Members picked via the `people.pick` intent; only used when `is_private`.
    members: list[UserProfile] = []

    def set_name(self, name: str):
        self.name = name

    def set_description(self, description: str):
        self.description = description

    def set_is_open(self, is_open: bool):
        self.is_open = is_open

    @rx.event
    def set_is_private(self, is_private: bool):
        self.is_private = is_private

    @rx.event
    def toggle(self):
        self.is_open = not self.is_open
        self.name = ""
        self.description = ""
        self.is_private = False
        self.members = []

    @rx.event
    def add_member(self, data: dict):
        """`people.pick` result handler: append the picked member once."""
        username = data.get("user", "")
        if not username or any(m.username == username for m in self.members):
            return
        self.members.append(
            UserProfile(
                username=username,
                email=data.get("email", ""),
                nickname=data.get("nickname", ""),
                avatar_seed=data.get("avatar_seed", "") or username,
                is_guest=False,
            )
        )

    @rx.event
    def remove_member(self, username: str):
        self.members = [m for m in self.members if m.username != username]

    @rx.event
    def create(self):
        yield GlobalLobbyState.create_room(
            self.name,
            self.description,
            self.is_private,
            [m.username for m in self.members],
        )
        self.is_open = False


def room_card(room: RoomInfo) -> rx.Component:
    return rx.el.div(
        rx.el.button(
            rx.el.div(
                rx.el.div(
                    rx.el.div(
                        rx.el.h3(
                            GlobalLobbyState.room_titles[room.name],
                            class_name="font-semibold text-gray-900",
                        ),
                        rx.cond(
                            room.is_direct,
                            rx.icon("message-circle", class_name="h-3.5 w-3.5 text-gray-400"),
                            rx.cond(
                                room.is_private,
                                rx.icon("lock", class_name="h-3.5 w-3.5 text-gray-400"),
                            ),
                        ),
                        class_name="flex items-center gap-1",
                    ),
                    rx.cond(
                        GlobalLobbyState.call_counts.contains(room.name),
                        rx.el.span(
                            rx.icon("phone-call", class_name="h-3 w-3 mr-1"),
                            GlobalLobbyState.call_counts[room.name],
                            title="Call in progress",
                            class_name="flex items-center bg-green-100 text-green-700 text-xs font-bold px-2 py-0.5 rounded-full ml-auto",
                        ),
                    ),
                    rx.cond(
                        TabSessionState.unread_counts[room.name] > 0,
                        rx.el.span(
                            TabSessionState.unread_counts[room.name],
                            class_name="bg-violet-600 text-white text-xs font-bold px-2 py-0.5 rounded-full ml-2",
                        ),
                    ),
                    class_name="flex items-center justify-between mb-1",
                ),
                rx.el.p(
                    room.description,
                    class_name="text-xs text-gray-500 text-left truncate",
                ),
                class_name="w-full",
            ),
            on_click=lambda: [LocalUIState.show_rooms, RoomState.handle_join_room(room.name)],
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


def picked_member_chip(member: UserProfile) -> rx.Component:
    return rx.el.div(
        rx.image(
            src=f"https://api.dicebear.com/9.x/notionists/svg?seed={member.avatar_seed}",
            class_name="size-5 rounded-full bg-violet-100",
        ),
        rx.el.span(
            rx.cond(member.nickname != "", member.nickname, member.username),
            class_name="text-xs font-medium text-gray-800 max-w-[140px] truncate",
        ),
        rx.el.button(
            rx.icon("x", class_name="h-3 w-3"),
            on_click=CreateRoomState.remove_member(member.username),
            aria_label="Remove " + member.username,
            class_name="p-0.5 rounded-full text-gray-400 hover:text-red-500 hover:bg-red-50",
        ),
        class_name="flex items-center gap-1.5 pl-1 pr-1.5 py-1 bg-violet-50 border border-violet-100 rounded-full",
    )


def private_members_picker() -> rx.Component:
    """Who may see the private room: the creator plus members picked via `people.pick`."""
    return rx.el.div(
        rx.el.div(
            rx.el.span(
                "Members who can see this room",
                class_name="text-sm font-medium text-gray-700",
            ),
            rx.el.button(
                rx.icon("user-plus", class_name="h-4 w-4 mr-1"),
                "Add people",
                type="button",
                on_click=Intent.start(
                    "relack", "people.pick", on_result=CreateRoomState.add_member
                ),
                class_name="flex items-center px-2 py-1 text-xs font-medium rounded-lg bg-violet-50 text-violet-600 hover:bg-violet-100 transition-colors",
            ),
            class_name="flex items-center justify-between mb-2",
        ),
        rx.el.div(
            rx.el.div(
                rx.icon("crown", class_name="h-3.5 w-3.5 text-amber-500"),
                rx.el.span("You", class_name="text-xs font-medium text-gray-800"),
                class_name="flex items-center gap-1.5 px-2 py-1 bg-amber-50 border border-amber-100 rounded-full",
            ),
            rx.foreach(CreateRoomState.members, picked_member_chip),
            class_name="flex flex-wrap gap-2 p-2 min-h-[44px] bg-gray-50 rounded-lg mb-6",
        ),
    )


def create_room_modal() -> rx.Component:
    # A plain overlay (not a Radix modal) so the `people.pick` intent dialog,
    # which renders outside this subtree, stays clickable on top of it.
    return rx.cond(
        CreateRoomState.is_open,
        rx.el.div(
            rx.el.div(
                rx.el.h2("Create New Room", class_name="text-lg font-bold mb-4"),
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
                    class_name="w-full px-3 py-2 border rounded-lg mb-4",
                ),
                rx.el.label(
                    rx.checkbox(
                        checked=CreateRoomState.is_private,
                        on_change=CreateRoomState.set_is_private,
                        color_scheme="violet",
                    ),
                    rx.icon("lock", class_name="h-4 w-4 text-gray-500"),
                    rx.el.span("Private room", class_name="text-sm font-medium text-gray-700"),
                    class_name="flex items-center gap-2 mb-4 cursor-pointer select-none",
                ),
                rx.cond(CreateRoomState.is_private, private_members_picker()),
                rx.el.div(
                    rx.el.button(
                        "Cancel",
                        on_click=CreateRoomState.toggle,
                        class_name="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg mr-2",
                    ),
                    rx.el.button(
                        "Create Room",
                        on_click=CreateRoomState.create,
                        class_name="px-4 py-2 bg-violet-600 text-white rounded-lg hover:bg-violet-700",
                    ),
                    class_name="flex justify-end",
                ),
                role="dialog",
                aria_label="Create New Room",
                on_click=rx.stop_propagation,
                class_name="bg-white rounded-2xl w-full max-w-sm shadow-2xl p-6",
            ),
            on_click=CreateRoomState.toggle,
            class_name="fixed inset-0 bg-black/50 backdrop-blur-sm z-[90] flex items-center justify-center p-4",
        ),
    )


def sidebar() -> rx.Component:
    return rx.el.aside(
        rx.el.div(
            rx.el.button(
                rx.icon("users", class_name="h-5 w-5 mr-2"),
                "People",
                on_click=[LocalUIState.show_people, PeopleState.load_members],
                class_name=rx.cond(
                    LocalUIState.main_view == "people",
                    "w-full flex items-center px-3 py-2 mb-4 rounded-xl text-sm font-semibold bg-violet-50 text-violet-600",
                    "w-full flex items-center px-3 py-2 mb-4 rounded-xl text-sm font-semibold text-gray-700 hover:bg-gray-50 transition-colors",
                ),
            ),
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
                rx.foreach(GlobalLobbyState.visible_room_list, room_card),
                class_name="flex flex-col gap-2 overflow-y-auto flex-1 pr-1",
            ),
            class_name="p-4 h-full flex flex-col",
        ),
        create_room_modal(),
        class_name=rx.cond(
            LocalUIState.is_sidebar_open,
            "w-72 bg-white border-r border-gray-200 h-full flex flex-col transition-all duration-300 ease-in-out shrink-0",
            "w-0 overflow-hidden h-full flex flex-col transition-all duration-300 ease-in-out shrink-0",
        ),
    )


def message_part(part: MessagePart, is_me) -> rx.Component:
    return rx.cond(
        part.href != "",
        rx.el.a(
            part.text,
            href=part.href,
            target="_blank",
            rel="noopener noreferrer",
            class_name=rx.cond(
                is_me,
                "underline underline-offset-2 break-all text-white hover:text-violet-100",
                "underline underline-offset-2 break-all text-violet-600 hover:text-violet-800",
            ),
        ),
        rx.el.span(part.text),
    )


def link_preview_card(msg: ChatMessage) -> rx.Component:
    return rx.el.a(
        rx.cond(
            msg.preview_image != "",
            rx.el.img(
                src=msg.preview_image,
                alt="",
                loading="lazy",
                class_name="w-full max-h-48 object-cover bg-gray-100",
            ),
        ),
        rx.el.div(
            rx.el.div(msg.preview_site, class_name="text-[11px] uppercase tracking-wide text-gray-400 truncate"),
            rx.el.div(msg.preview_title, class_name="text-sm font-semibold text-gray-900 line-clamp-2"),
            rx.cond(
                msg.preview_description != "",
                rx.el.div(msg.preview_description, class_name="text-xs text-gray-500 mt-0.5 line-clamp-3"),
            ),
            class_name="px-3 py-2",
        ),
        href=msg.preview_url,
        target="_blank",
        rel="noopener noreferrer",
        class_name="block mt-2 w-72 max-w-full overflow-hidden rounded-xl border border-gray-200 bg-white hover:bg-gray-50 transition-colors no-underline",
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
                    ReactRouterLink.create(
                        rx.image(
                                src=f"https://api.dicebear.com/9.x/notionists/svg?seed={avatar_seed}",
                            class_name="size-8 rounded-full bg-white border border-gray-100 shadow-sm hover:scale-105 transition-transform",
                        ),
                        to=f"/profile/{msg.sender}",
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
                            rx.el.p(
                                rx.cond(
                                    msg.parts.length() > 0,
                                    rx.foreach(
                                        msg.parts,
                                        lambda part: message_part(part, is_me),
                                    ),
                                    msg.content,
                                ),
                                class_name="text-sm leading-relaxed whitespace-pre-wrap break-words",
                            ),
                            rx.cond(
                                msg.preview_url != "",
                                link_preview_card(msg),
                            ),
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
    return ReactRouterLink.create(
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
        to=f"/profile/{user.username}",
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
            LocalUIState.is_user_list_open,
            "w-64 bg-white border-l border-gray-200 h-full flex flex-col p-4 transition-all duration-300 ease-in-out shrink-0",
            "w-0 overflow-hidden h-full flex flex-col p-0 border-none transition-all duration-300 ease-in-out shrink-0",
        ),
    )


def room_member_item(user: UserProfile) -> rx.Component:
    return rx.el.div(
        rx.image(
            src=f"https://api.dicebear.com/9.x/notionists/svg?seed={user.avatar_seed}",
            class_name="size-7 rounded-full bg-violet-100 shrink-0",
        ),
        rx.el.div(
            rx.el.div(
                rx.el.span(
                    rx.cond(user.nickname != "", user.nickname, user.username),
                    class_name="text-sm font-medium text-gray-900 truncate",
                ),
                rx.cond(
                    user.username == RoomState.room_creator_username,
                    rx.el.span(
                        "Owner",
                        class_name="ml-1.5 text-[10px] font-semibold uppercase text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded",
                    ),
                ),
                class_name="flex items-center min-w-0",
            ),
            rx.cond(
                user.email != "",
                rx.el.span(user.email, class_name="text-xs text-gray-500 truncate"),
            ),
            class_name="flex flex-col ml-2 min-w-0",
        ),
        class_name="flex items-center p-1.5",
    )


def room_members_popover() -> rx.Component:
    """Private-room badge; opens the list of people allowed to see the room."""
    return rx.popover.root(
        rx.popover.trigger(
            rx.el.button(
                rx.icon("lock", class_name="h-3.5 w-3.5 mr-1"),
                "Private · ",
                RoomState.room_allowed_members.length(),
                " members",
                class_name="flex items-center px-2 py-1 text-xs font-medium rounded-lg bg-gray-100 text-gray-600 hover:bg-violet-50 hover:text-violet-600 transition-colors",
            ),
        ),
        rx.popover.content(
            rx.el.h4(
                "Who can see this room",
                class_name="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2",
            ),
            rx.el.div(
                rx.foreach(RoomState.room_allowed_members, room_member_item),
                class_name="flex flex-col max-h-72 overflow-y-auto",
            ),
            class_name="w-72",
        ),
    )


def call_button() -> rx.Component:
    """Start the room's call, or join it while one is in progress."""
    count = GlobalLobbyState.call_counts.get(RoomState.room_name, 0)
    return rx.cond(
        count > 0,
        rx.el.button(
            rx.icon("phone-call", class_name="h-4 w-4 mr-1.5"),
            "Join call · ",
            count,
            on_click=CallState.join_call(RoomState.room_name),
            class_name="flex items-center px-3 py-1.5 mr-2 text-sm font-semibold rounded-lg bg-green-600 text-white hover:bg-green-700 transition-colors",
        ),
        rx.el.button(
            rx.icon("phone", class_name="h-5 w-5"),
            on_click=CallState.join_call(RoomState.room_name),
            title="Start a call",
            aria_label="Start a call",
            class_name="p-2 mr-2 rounded-lg text-gray-500 hover:text-green-600 hover:bg-green-50 transition-colors",
        ),
    )


def incoming_call_card(call: IncomingCall) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.icon("phone-incoming", class_name="h-5 w-5 text-white"),
            class_name="size-10 rounded-full bg-green-500 flex items-center justify-center shrink-0 animate-pulse",
        ),
        rx.el.div(
            rx.el.span("Incoming call", class_name="text-xs font-semibold uppercase tracking-wide text-green-600"),
            rx.el.span(
                rx.cond(call.is_direct, call.caller, "# " + call.title),
                class_name="text-sm font-bold text-gray-900 truncate",
            ),
            rx.cond(
                ~call.is_direct,
                rx.el.span(call.caller + " is calling", class_name="text-xs text-gray-500 truncate"),
            ),
            class_name="flex flex-col min-w-0 flex-1",
        ),
        rx.el.button(
            rx.icon("phone-off", class_name="h-4 w-4"),
            on_click=CallState.decline_call(call.room_name),
            title="Decline",
            aria_label="Decline",
            class_name="p-2.5 rounded-full bg-red-100 text-red-600 hover:bg-red-200 transition-colors shrink-0",
        ),
        rx.el.button(
            rx.icon("phone", class_name="h-4 w-4"),
            on_click=[
                LocalUIState.show_rooms,
                RoomState.handle_join_room(call.room_name),
                CallState.join_call(call.room_name),
            ],
            title="Accept",
            aria_label="Accept",
            class_name="p-2.5 rounded-full bg-green-600 text-white hover:bg-green-700 transition-colors shrink-0",
        ),
        role="alertdialog",
        aria_label="Incoming call",
        class_name="w-80 flex items-center gap-3 p-3 bg-white rounded-2xl border border-gray-100 shadow-2xl",
    )


def incoming_calls() -> rx.Component:
    # Above the intent dialog (z-index 1000), so a call can be answered from inside another.
    return rx.el.div(
        rx.foreach(GlobalLobbyState.incoming_calls, incoming_call_card),
        class_name="fixed bottom-6 right-6 z-[1001] flex flex-col gap-3",
    )


_CALL_HEARTBEAT_JS = """
if (window.__relackCallHb) clearInterval(window.__relackCallHb);
window.__relackCallHb = setInterval(function () {
    var el = document.getElementById('call-heartbeat-trigger');
    if (!el) { clearInterval(window.__relackCallHb); window.__relackCallHb = null; return; }
    // On the chat page, its own heartbeat already covers the call.
    if (!document.getElementById('heartbeat-trigger')) el.click();
}, 3000);
"""


@rx.memo
def call_keepalive() -> rx.Component:
    """While in a call, keep its heartbeat going on every page.

    The call runs in the app-wide intent dialogs, so it survives leaving the chat
    page (e.g. to see a profile); without heartbeats it would look abandoned.
    """
    return rx.cond(
        CallState.current_room != "",
        rx.el.button(
            id="call-heartbeat-trigger",
            on_click=CallState.heartbeat,
            on_mount=rx.call_script(_CALL_HEARTBEAT_JS),
            tab_index=-1,
            aria_hidden="true",
            class_name="sr-only",
        ),
    )


def chat_area() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.button(
                    rx.icon("panel-left", class_name="h-5 w-5"),
                    on_click=LocalUIState.toggle_sidebar,
                    class_name=f"p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors {rx.cond(LocalUIState.is_sidebar_open, 'text-violet-600 bg-violet-50', '')}",
                ),
                rx.el.div(
                    rx.el.h2(
                        GlobalLobbyState.room_titles[RoomState.room_name],
                        class_name="text-lg font-bold text-gray-900",
                    ),
                    rx.cond(
                        RoomState.room_is_direct,
                        rx.el.span(
                            rx.icon("message-circle", class_name="h-3.5 w-3.5 mr-1"),
                            "Direct message",
                            class_name="flex items-center px-2 py-1 text-xs font-medium rounded-lg bg-gray-100 text-gray-600",
                        ),
                        rx.cond(RoomState.room_is_private, room_members_popover()),
                    ),
                    rx.cond(
                        RoomState.room_creator_username != "",
                        rx.cond(
                            RoomState.room_creator_username == "System",
                            rx.el.span(
                                "By " + RoomState.room_creator_display,
                                class_name="text-xs font-medium text-gray-500",
                            ),
                            ReactRouterLink.create(
                                rx.el.span(
                                    "By " + RoomState.room_creator_display,
                                    class_name="text-xs font-medium text-gray-500 hover:text-gray-700 hover:underline",
                                ),
                                to="/profile/" + RoomState.room_creator_username,
                                class_name="text-xs text-gray-500",
                            ),
                        ),
                    ),
                    class_name="flex items-center gap-3 ml-4",
                ),
                class_name="flex items-center",
            ),
            rx.el.div(
                call_button(),
                rx.el.button(
                    rx.icon("users", class_name="h-5 w-5"),
                    on_click=LocalUIState.toggle_user_list,
                    class_name=f"p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors mr-2 {rx.cond(LocalUIState.is_user_list_open, 'text-violet-600 bg-violet-50', '')}",
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
        rx.cond(
            LocalUIState.main_view == "people",
            rx.el.div(people_view(), class_name="flex-1 overflow-y-auto"),
            rx.cond(RoomState.in_room, chat_area(), empty_state()),
        ),
        incoming_calls(),
        rx.el.button(
            id="heartbeat-trigger",
            on_click=[RoomState.heartbeat, CallState.heartbeat],
            class_name="sr-only",
        ),
        rx.script(
            """
            if (window.__relack_hb) clearInterval(window.__relack_hb);
            window.__relack_hb = setInterval(function() {
                var el = document.getElementById('heartbeat-trigger');
                if (el) { el.click(); }
                else { clearInterval(window.__relack_hb); window.__relack_hb = null; }
            }, 3000);
            """
        ),
        class_name="flex h-[calc(100vh-73px)] overflow-hidden bg-gray-50/50",
        # Ensure lobby link exists so room list is populated even after reloads.
        on_mount=[GlobalLobbyState.join_lobby, RoomState.rejoin_last_room, RoomState.heartbeat, RoomState.seed_all_room_read_counts],
        on_unmount=RoomState.handle_leave_room,
        on_focus=RoomState.heartbeat,
        on_mouse_enter=RoomState.heartbeat,
        on_mouse_move=RoomState.heartbeat,
        tab_index=0,
    )