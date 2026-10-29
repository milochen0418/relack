import reflex as rx
from reflex.components.react_router.dom import ReactRouterLink
# rx.el.a is a React Router link in Reflex 0.10; Markdown links and file links
# need a plain <a> (Markdown hands over `href`, and files are not app routes).
from reflex_components_core.el.elements.inline import A as PlainLink
from relack.components.clock import day_label, local_datetime, local_time
from relack.components.client_script import CHAT_CSS, CLIENT_JS
from relack.emoji import EMOJI, QUICK_REACTIONS
from relack.states.shared_state import GlobalLobbyState, LocalUIState, RoomState
from relack.states.auth_state import AuthState
from relack.states.chat_state import MAX_UPLOAD_BYTES, ChatUIState, ComposerState, SearchState, UnreadState
from relack.models import (
    Attachment,
    ChatMessage,
    FileHit,
    IncomingCall,
    Reaction,
    RoomInfo,
    SearchHit,
    UserProfile,
)
from relack.states.call_state import CallState
from relack.components.people_views import people_view
from relack.states.people_state import PeopleState
from reflex_ddns_auth.intent import Intent

_EMOJI = rx.Var.create(EMOJI)
_ICON_BUTTON = "p-1.5 rounded-md text-gray-500 hover:text-gray-900 hover:bg-gray-100 transition-colors"


def avatar_url(seed) -> str:
    return f"https://api.dicebear.com/9.x/notionists/svg?seed={seed}"


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
    title = GlobalLobbyState.room_titles[room.name]
    unread = UnreadState.unread.get(room.name, 0)
    mentions = UnreadState.mentions.get(room.name, 0)
    card = rx.el.div(
        rx.el.button(
            rx.el.div(
                rx.el.div(
                    rx.el.div(
                        rx.el.h3(
                            title,
                            class_name=rx.cond(
                                (unread > 0) | (mentions > 0),
                                "font-bold text-gray-900 truncate",
                                "font-semibold text-gray-900 truncate",
                            ),
                        ),
                        rx.cond(
                            room.is_direct,
                            rx.icon("message-circle", class_name="h-3.5 w-3.5 text-gray-400 shrink-0"),
                            rx.cond(
                                room.is_private,
                                rx.icon("lock", class_name="h-3.5 w-3.5 text-gray-400 shrink-0"),
                            ),
                        ),
                        class_name="flex items-center gap-1 min-w-0",
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
                        mentions > 0,
                        rx.el.span(
                            "@",
                            mentions,
                            title="Mentions of you",
                            class_name="bg-rose-500 text-white text-xs font-bold px-2 py-0.5 rounded-full ml-2",
                        ),
                        rx.cond(
                            unread > 0,
                            rx.el.span(
                                unread,
                                title="Unread messages",
                                class_name=rx.cond(
                                    room.is_direct,
                                    "bg-rose-500 text-white text-xs font-bold px-2 py-0.5 rounded-full ml-2",
                                    "bg-violet-600 text-white text-xs font-bold px-2 py-0.5 rounded-full ml-2",
                                ),
                            ),
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
    # The search box filters the list as you type (not while showing search results).
    return rx.cond(
        title.lower().contains(SearchState.room_filter) | (LocalUIState.main_view == "search"),
        card,
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


def notification_settings() -> rx.Component:
    """Bell in the sidebar: desktop notifications and the alert sound for this browser."""
    toggle_class = "px-2.5 py-1 text-xs font-semibold rounded-lg bg-violet-50 text-violet-600 hover:bg-violet-100"
    return rx.popover.root(
        rx.popover.trigger(
            rx.el.button(
                rx.cond(
                    (UnreadState.desktop == "off") & (UnreadState.sound == "off"),
                    rx.icon("bell-off", class_name="h-5 w-5"),
                    rx.icon("bell", class_name="h-5 w-5"),
                ),
                title="Notifications",
                aria_label="Notification settings",
                class_name="p-1.5 rounded-lg text-gray-500 hover:text-violet-600 hover:bg-violet-50 transition-colors",
            ),
        ),
        rx.popover.content(
            rx.el.h4("Notifications", class_name="text-sm font-bold text-gray-900 mb-1"),
            rx.el.p(
                "For direct messages, @mentions and replies in your threads.",
                class_name="text-xs text-gray-500 mb-3",
            ),
            rx.el.div(
                rx.el.div(
                    rx.el.span("Desktop notifications", class_name="text-sm font-medium text-gray-800"),
                    rx.el.span(
                        rx.match(
                            UnreadState.permission,
                            ("granted", rx.cond(UnreadState.desktop == "off", "Off", "On")),
                            ("denied", "Blocked in the browser's site settings"),
                            ("unsupported", "Not available in this browser"),
                            "Not turned on yet",
                        ),
                        class_name="text-xs text-gray-500",
                    ),
                    class_name="flex flex-col",
                ),
                rx.match(
                    UnreadState.permission,
                    (
                        "granted",
                        rx.el.button(
                            rx.cond(UnreadState.desktop == "off", "Turn on", "Turn off"),
                            on_click=UnreadState.toggle_desktop,
                            class_name=toggle_class,
                        ),
                    ),
                    (
                        "default",
                        rx.el.button(
                            "Enable",
                            on_click=rx.call_script(
                                "Notification.requestPermission()", callback=UnreadState.set_permission
                            ),
                            class_name=toggle_class,
                        ),
                    ),
                    rx.fragment(),
                ),
                class_name="flex items-center justify-between gap-3 mb-3",
            ),
            rx.el.div(
                rx.el.div(
                    rx.el.span("Sound", class_name="text-sm font-medium text-gray-800"),
                    rx.el.span(rx.cond(UnreadState.sound == "off", "Off", "On"), class_name="text-xs text-gray-500"),
                    class_name="flex flex-col",
                ),
                rx.el.button(
                    rx.cond(UnreadState.sound == "off", "Turn on", "Turn off"),
                    on_click=UnreadState.toggle_sound,
                    class_name=toggle_class,
                ),
                class_name="flex items-center justify-between gap-3",
            ),
            side="right",
            align="start",
            class_name="w-72",
        ),
    )


def search_box() -> rx.Component:
    return rx.el.form(
        rx.el.div(
            rx.icon(
                "search",
                class_name="h-4 w-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none",
            ),
            rx.el.input(
                id="relack-search",
                name="q",
                placeholder="Search messages, files, people",
                default_value=SearchState.query,
                on_change=SearchState.set_query,
                auto_complete="off",
                aria_label="Search",
                custom_attrs={"data-relack-search": "1"},
                class_name="w-full pl-9 pr-3 py-2.5 bg-gray-50 rounded-xl text-sm border-none focus:ring-1 focus:ring-violet-500 placeholder:text-gray-400",
            ),
            class_name="relative",
        ),
        on_submit=SearchState.run,
        class_name="mb-4",
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
                rx.el.div(
                    notification_settings(),
                    rx.el.button(
                        rx.icon("plus", class_name="h-5 w-5"),
                        on_click=CreateRoomState.toggle,
                        title="New room",
                        aria_label="New room",
                        class_name="p-1.5 rounded-lg bg-violet-50 text-violet-600 hover:bg-violet-100 transition-colors",
                    ),
                    class_name="flex items-center gap-1",
                ),
                class_name="flex items-center justify-between mb-4",
            ),
            search_box(),
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


# Markdown in bubbles: no raw HTML, no math ("$5" stays text); headings are bold lines.
_MARKDOWN_MAP = {
    "p": lambda text: rx.el.p(text),
    "a": lambda text: PlainLink.create(text, target="_blank", rel="noopener noreferrer"),
    "code": lambda text: rx.el.code(text),
    "pre": lambda text, **_props: rx.el.pre(rx.el.code(text)),
    "ul": lambda text: rx.el.ul(text),
    "ol": lambda text: rx.el.ol(text),
    "li": lambda text: rx.el.li(text),
    "blockquote": lambda text: rx.el.blockquote(text),
    # Pictures from elsewhere stay links: loading them would tell that site who reads the room.
    "img": lambda text: PlainLink.create(
        rx.Var("'🖼 ' + (props.alt || 'image')", _var_type=str),
        href=rx.Var("props.src", _var_type=str),
        target="_blank",
        rel="noopener noreferrer",
    ),
    **{f"h{level}": (lambda text: rx.el.p(rx.el.strong(text))) for level in range(1, 7)},
}


def message_markdown(source) -> rx.Component:
    return rx.markdown(
        source,
        use_math=False,
        use_katex=False,
        use_raw=False,
        component_map=_MARKDOWN_MAP,
        class_name="relack-md",
    )


def attachment_view(att: Attachment) -> rx.Component:
    url = rx.get_upload_url(att.path)
    return rx.cond(
        att.is_image,
        rx.el.img(
            src=url,
            alt=att.name,
            title=att.name,
            loading="lazy",
            custom_attrs={"data-relack-image": att.name},
            class_name="block max-h-72 max-w-full w-auto rounded-lg border border-black/5 bg-white object-contain cursor-zoom-in",
        ),
        PlainLink.create(
            rx.el.div(
                rx.icon("file-text", class_name="h-5 w-5"),
                class_name="size-9 rounded-lg bg-violet-100 text-violet-600 flex items-center justify-center shrink-0",
            ),
            rx.el.div(
                rx.el.span(att.name, class_name="text-sm font-medium text-gray-900 truncate"),
                rx.el.span(att.size_label, class_name="text-xs text-gray-500"),
                class_name="flex flex-col min-w-0",
            ),
            rx.icon("download", class_name="h-4 w-4 text-gray-400 ml-auto shrink-0"),
            href=url,
            download=att.name,
            target="_blank",
            rel="noopener noreferrer",
            title="Download " + att.name,
            class_name="flex items-center gap-3 w-72 max-w-full p-2 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 transition-colors no-underline",
        ),
    )


def message_body(msg: ChatMessage) -> rx.Component:
    return rx.fragment(
        rx.cond(
            msg.deleted,
            rx.el.p("This message was deleted.", class_name="text-sm italic opacity-70"),
            rx.cond(msg.render != "", message_markdown(msg.render)),
        ),
        rx.cond(
            msg.attachments.length() > 0,
            rx.el.div(
                rx.foreach(msg.attachments, attachment_view),
                class_name="flex flex-col gap-2 mt-1",
            ),
        ),
        rx.cond(msg.preview_url != "", link_preview_card(msg)),
    )


def emoji_grid(render_item) -> rx.Component:
    return rx.el.div(
        rx.foreach(_EMOJI, render_item),
        class_name="grid grid-cols-8 gap-0.5 w-72 max-h-56 overflow-y-auto",
    )


def reaction_picker(msg: ChatMessage, trigger_class: str) -> rx.Component:
    return rx.popover.root(
        rx.popover.trigger(
            rx.el.button(
                rx.icon("smile-plus", class_name="h-4 w-4"),
                type="button",
                title="Add reaction",
                aria_label="Add reaction",
                class_name=trigger_class,
            ),
        ),
        rx.popover.content(
            emoji_grid(
                lambda emoji: rx.popover.close(
                    rx.el.button(
                        emoji,
                        type="button",
                        on_click=RoomState.toggle_reaction(msg.id, emoji),
                        aria_label="React with " + emoji,
                        class_name="size-8 text-lg rounded hover:bg-gray-100 flex items-center justify-center",
                    )
                )
            ),
            side="top",
            align="end",
            class_name="p-2",
        ),
    )


def reaction_chip(msg: ChatMessage, reaction: Reaction) -> rx.Component:
    mine = reaction.users.contains(AuthState.user.username)
    return rx.el.button(
        rx.el.span(reaction.emoji, class_name="text-sm leading-none"),
        rx.el.span(reaction.count, class_name="text-xs font-semibold"),
        on_click=RoomState.toggle_reaction(msg.id, reaction.emoji),
        title=reaction.names,
        aria_label=f"{reaction.emoji} {reaction.count}",
        class_name=rx.cond(
            mine,
            "flex items-center gap-1 px-2 py-0.5 rounded-full border border-violet-300 bg-violet-50 text-violet-700",
            "flex items-center gap-1 px-2 py-0.5 rounded-full border border-gray-200 bg-white text-gray-600 hover:border-gray-300",
        ),
    )


def message_actions(msg: ChatMessage, is_me, in_thread: bool) -> rx.Component:
    """Toolbar shown when hovering a message."""
    return rx.el.div(
        *[
            rx.el.button(
                emoji,
                type="button",
                on_click=RoomState.toggle_reaction(msg.id, emoji),
                title=f"React with {emoji}",
                aria_label=f"React with {emoji}",
                class_name="px-1.5 py-1 rounded-md hover:bg-gray-100 text-sm leading-none",
            )
            for emoji in QUICK_REACTIONS
        ],
        reaction_picker(msg, _ICON_BUTTON),
        *(
            []
            if in_thread
            else [
                rx.el.button(
                    rx.icon("message-square-text", class_name="h-4 w-4"),
                    type="button",
                    on_click=RoomState.open_thread(msg.id),
                    title="Reply in thread",
                    aria_label="Reply in thread",
                    class_name=_ICON_BUTTON,
                )
            ]
        ),
        rx.cond(
            is_me,
            rx.fragment(
                rx.el.button(
                    rx.icon("pencil", class_name="h-4 w-4"),
                    type="button",
                    on_click=ChatUIState.start_edit(msg.id),
                    title="Edit message",
                    aria_label="Edit message",
                    class_name=_ICON_BUTTON,
                ),
                rx.el.button(
                    rx.icon("trash-2", class_name="h-4 w-4"),
                    type="button",
                    on_click=ChatUIState.ask_delete(msg.id),
                    title="Delete message",
                    aria_label="Delete message",
                    class_name=_ICON_BUTTON + " hover:text-red-600",
                ),
            ),
        ),
        class_name=rx.cond(
            is_me,
            "absolute -top-4 left-0 z-10 flex items-center gap-0.5 bg-white border border-gray-200 rounded-lg shadow-sm px-1 py-0.5 opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto focus-within:opacity-100 focus-within:pointer-events-auto transition-opacity",
            "absolute -top-4 right-0 z-10 flex items-center gap-0.5 bg-white border border-gray-200 rounded-lg shadow-sm px-1 py-0.5 opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto focus-within:opacity-100 focus-within:pointer-events-auto transition-opacity",
        ),
    )


def thread_summary(msg: ChatMessage) -> rx.Component:
    return rx.cond(
        msg.reply_count > 0,
        rx.el.button(
            rx.el.div(
                rx.foreach(
                    msg.reply_seeds,
                    lambda seed: rx.image(
                        src=avatar_url(seed),
                        class_name="size-5 rounded-full border-2 border-white bg-violet-100 -ml-1 first:ml-0",
                    ),
                ),
                class_name="flex items-center",
            ),
            rx.el.span(
                msg.reply_count,
                rx.cond(msg.reply_count == 1, " reply", " replies"),
                class_name="text-xs font-semibold text-violet-600",
            ),
            rx.el.span("Last reply ", local_time(msg.last_reply_at), class_name="text-xs text-gray-400"),
            type="button",
            on_click=RoomState.open_thread(msg.id),
            class_name="flex items-center gap-2 mt-1 px-2 py-1 rounded-lg border border-transparent hover:bg-white hover:border-gray-200 transition-colors",
        ),
    )


def edit_form(msg: ChatMessage) -> rx.Component:
    return rx.el.form(
        rx.el.input(type="hidden", name="id", value=msg.id),
        rx.el.textarea(
            name="message",
            default_value=ChatUIState.edit_text,
            auto_focus=True,
            rows=2,
            aria_label="Edit message",
            custom_attrs={"data-relack-composer": "edit"},
            class_name="block w-full min-w-[18rem] resize-none rounded-xl border border-violet-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-violet-500/30",
        ),
        rx.el.div(
            rx.el.span("Esc to cancel · Enter to save", class_name="text-[11px] text-gray-400"),
            rx.el.button(
                "Cancel",
                type="button",
                on_click=ChatUIState.cancel_edit,
                custom_attrs={"data-relack-cancel": "1"},
                class_name="ml-auto px-3 py-1 text-xs font-medium rounded-lg text-gray-600 hover:bg-gray-100",
            ),
            rx.el.button(
                "Save",
                type="submit",
                class_name="px-3 py-1 text-xs font-semibold rounded-lg bg-violet-600 text-white hover:bg-violet-700",
            ),
            class_name="flex items-center gap-2 mt-1.5",
        ),
        on_submit=RoomState.save_edit,
        class_name="w-full max-w-xl",
    )


def day_divider(label) -> rx.Component:
    return rx.el.div(
        rx.el.div(class_name="flex-1 h-px bg-gray-200"),
        rx.el.span(
            label,
            class_name="text-xs font-semibold text-gray-500 bg-white border border-gray-200 rounded-full px-3 py-0.5",
        ),
        rx.el.div(class_name="flex-1 h-px bg-gray-200"),
        class_name="flex items-center gap-3 my-4",
    )


def message_item(msg: ChatMessage, prev_at, in_thread: bool = False, anchor: str = "msg-") -> rx.Component:
    """One message: a day divider when the day changes, then the bubble and its extras.

    `anchor` prefixes the element id that jumps scroll to.
    """
    is_me = (msg.sender == AuthState.user.username) | (msg.sender == AuthState.user.nickname)
    header = rx.el.div(
        rx.cond(
            ~is_me,
            rx.el.span(msg.display_name, class_name="text-xs font-semibold text-gray-700"),
        ),
        rx.el.span(
            local_time(msg.created_at, msg.timestamp),
            title=local_datetime(msg.created_at, msg.timestamp),
            class_name="text-[11px] text-gray-400",
        ),
        rx.cond(msg.edited, rx.el.span("(edited)", class_name="text-[11px] text-gray-400")),
        class_name=rx.cond(
            is_me,
            "flex items-center gap-1.5 mb-1 mr-1",
            "flex items-center gap-1.5 mb-1 ml-1",
        ),
    )
    bubble = rx.el.div(
        message_body(msg),
        class_name=rx.cond(
            is_me,
            "relack-bubble relack-mine max-w-full bg-gradient-to-br from-violet-600 to-indigo-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 shadow-sm",
            "relack-bubble max-w-full bg-white border border-gray-100 text-gray-800 rounded-2xl rounded-tl-sm px-4 py-2.5 shadow-sm",
        ),
    )
    column = rx.el.div(
        header,
        rx.cond(ChatUIState.editing_id == msg.id, edit_form(msg), bubble),
        rx.cond(
            msg.reactions.length() > 0,
            rx.el.div(
                rx.foreach(msg.reactions, lambda reaction: reaction_chip(msg, reaction)),
                reaction_picker(
                    msg,
                    "flex items-center px-1.5 py-0.5 rounded-full border border-gray-200 bg-white text-gray-500 hover:text-gray-800",
                ),
                class_name="flex flex-wrap items-center gap-1 mt-1",
            ),
        ),
        thread_summary(msg) if not in_thread else rx.fragment(),
        rx.cond(
            ~msg.deleted & (ChatUIState.editing_id != msg.id),
            message_actions(msg, is_me, in_thread),
        ),
        class_name=rx.cond(
            is_me,
            "relative flex flex-col items-end min-w-0 " + ("max-w-full" if in_thread else "max-w-[85%]"),
            "relative flex flex-col items-start min-w-0 " + ("max-w-full" if in_thread else "max-w-[85%]"),
        ),
    )
    row = rx.el.div(
        rx.cond(
            ~is_me,
            ReactRouterLink.create(
                rx.image(
                    src=avatar_url(msg.avatar_seed),
                    class_name="size-8 rounded-full bg-white border border-gray-100 shadow-sm hover:scale-105 transition-transform",
                ),
                to="/profile/" + msg.sender,
                class_name="mr-2 mt-5 self-start shrink-0",
            ),
        ),
        column,
        class_name=rx.cond(is_me, "group flex justify-end", "group flex justify-start"),
    )
    divider = rx.fragment() if in_thread else rx.cond(
        day_label(msg.created_at, prev_at) != "",
        day_divider(day_label(msg.created_at, prev_at)),
    )
    return rx.el.div(
        divider,
        rx.cond(
            msg.is_system,
            rx.el.div(
                rx.el.span(
                    msg.content,
                    class_name="text-xs text-gray-400 bg-gray-100/80 backdrop-blur-sm px-3 py-1 rounded-full border border-gray-200/50",
                ),
                class_name="flex justify-center my-4",
            ),
            row,
        ),
        id=anchor + msg.id,
        class_name=rx.cond(
            ChatUIState.highlight_id == msg.id,
            "relack-highlight w-full mb-4",
            "w-full mb-4",
        ),
    )


def pending_chip(att: Attachment) -> rx.Component:
    return rx.el.div(
        rx.cond(
            att.is_image,
            rx.el.img(src=rx.get_upload_url(att.path), alt="", class_name="size-10 rounded-md object-cover bg-gray-100"),
            rx.el.div(
                rx.icon("file-text", class_name="h-4 w-4"),
                class_name="size-10 rounded-md bg-violet-100 text-violet-600 flex items-center justify-center",
            ),
        ),
        rx.el.div(
            rx.el.span(att.name, class_name="text-xs font-medium text-gray-800 truncate max-w-[10rem]"),
            rx.el.span(att.size_label, class_name="text-[10px] text-gray-500"),
            class_name="flex flex-col min-w-0",
        ),
        rx.el.button(
            rx.icon("x", class_name="h-3 w-3"),
            type="button",
            on_click=ComposerState.remove_pending(att.id),
            title="Remove " + att.name,
            aria_label="Remove " + att.name,
            class_name="p-1 rounded-full text-gray-400 hover:text-red-500 hover:bg-red-50",
        ),
        custom_attrs={"data-relack-pending": att.id},
        class_name="flex items-center gap-2 pl-1 pr-1.5 py-1 bg-gray-50 border border-gray-200 rounded-lg",
    )


def emoji_menu(target: str) -> rx.Component:
    return rx.popover.root(
        rx.popover.trigger(
            rx.el.button(
                rx.icon("smile", class_name="h-4 w-4"),
                type="button",
                title="Emoji",
                aria_label="Emoji",
                class_name=_ICON_BUTTON,
            ),
        ),
        rx.popover.content(
            emoji_grid(
                lambda emoji: rx.popover.close(
                    rx.el.button(
                        emoji,
                        type="button",
                        custom_attrs={"data-relack-emoji": emoji, "data-relack-target": target},
                        class_name="size-8 text-lg rounded hover:bg-gray-100 flex items-center justify-center",
                    )
                )
            ),
            side="top",
            align="start",
            class_name="p-2",
        ),
    )


def composer(target: str) -> rx.Component:
    """Message box of the room ("main") or the open thread ("thread")."""
    main = target == "main"
    pending = ComposerState.pending if main else ComposerState.pending_thread
    upload_id = f"relack-upload-{target}"

    def fmt(kind: str, icon: str, label: str) -> rx.Component:
        return rx.el.button(
            rx.icon(icon, class_name="h-4 w-4"),
            type="button",
            title=label,
            aria_label=label,
            custom_attrs={"data-relack-fmt": kind},
            class_name=_ICON_BUTTON,
        )

    separator = rx.el.span(class_name="w-px h-4 bg-gray-200 mx-1")
    return rx.el.form(
        *([] if main else [rx.el.input(type="hidden", name="root_id", value=ChatUIState.thread_id)]),
        rx.el.div(
            rx.cond(
                pending.length() > 0,
                rx.el.div(rx.foreach(pending, pending_chip), class_name="flex flex-wrap gap-2 px-3 pt-3"),
            ),
            rx.cond(
                ComposerState.uploading,
                rx.el.div(
                    rx.icon("loader-circle", class_name="h-4 w-4 animate-spin"),
                    "Uploading…",
                    class_name="flex items-center gap-2 px-4 pt-2 text-xs text-gray-500",
                ),
            ),
            rx.el.textarea(
                name="message",
                placeholder=(
                    "Message " + GlobalLobbyState.room_titles[RoomState.room_name] if main else "Reply…"
                ),
                rows=1,
                aria_label="Message" if main else "Reply",
                custom_attrs={"data-relack-composer": target, "data-relack-upload": upload_id},
                class_name="block w-full resize-none bg-transparent border-0 focus:ring-0 focus:outline-none px-4 pt-3 pb-1 text-sm text-gray-900 placeholder:text-gray-400 max-h-[40vh] overflow-y-auto",
            ),
            rx.el.div(
                fmt("bold", "bold", "Bold"),
                fmt("italic", "italic", "Italic"),
                fmt("strike", "strikethrough", "Strikethrough"),
                separator,
                fmt("code", "code", "Code"),
                fmt("codeblock", "square-code", "Code block"),
                fmt("quote", "quote", "Quote"),
                fmt("ul", "list", "Bulleted list"),
                fmt("ol", "list-ordered", "Numbered list"),
                fmt("link", "link", "Link"),
                separator,
                emoji_menu(target),
                rx.el.button(
                    rx.icon("paperclip", class_name="h-4 w-4"),
                    type="button",
                    title="Attach files",
                    aria_label="Attach files",
                    custom_attrs={"data-relack-attach": upload_id},
                    class_name=_ICON_BUTTON,
                ),
                rx.el.button(
                    rx.icon("send", class_name="h-4 w-4"),
                    type="submit",
                    title="Send",
                    aria_label="Send",
                    class_name="ml-auto bg-violet-600 hover:bg-violet-700 text-white p-2 rounded-lg transition-all shadow-sm active:scale-95",
                ),
                class_name="flex items-center gap-0.5 px-2 pb-2",
            ),
            class_name="bg-white rounded-2xl border border-gray-200 shadow-sm focus-within:ring-2 focus-within:ring-violet-500/20 focus-within:border-violet-500 transition-all",
        ),
        rx.el.p(
            "Enter to send · Shift+Enter for a new line · @ to mention",
            class_name="text-[11px] text-gray-400 mt-1 px-2",
        ),
        on_submit=RoomState.send_message if main else RoomState.send_reply,
        reset_on_submit=True,
        custom_attrs={"data-mentions": RoomState.mention_candidates},
        class_name="relative w-full max-w-4xl mx-auto" if main else "relative w-full",
    )


def upload_zone(target: str) -> rx.Component:
    """Hidden upload input of a composer; the page script feeds it pasted and dropped files."""
    upload_id = f"relack-upload-{target}"
    handler = ComposerState.upload_main if target == "main" else ComposerState.upload_thread
    return rx.el.div(
        rx.upload.root(
            id=upload_id,
            multiple=True,
            max_size=MAX_UPLOAD_BYTES,
            no_click=True,
            no_keyboard=True,
            no_drag=True,
            on_drop=handler(
                rx.upload_files(upload_id=upload_id, on_upload_progress=ComposerState.upload_progress)
            ),
        ),
        id=upload_id,
        class_name="hidden",
    )


def thread_panel() -> rx.Component:
    thread_id = ChatUIState.thread_id
    replies = RoomState.thread_replies.get(thread_id, [])
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.h3("Thread", class_name="text-base font-bold text-gray-900"),
                rx.el.span(
                    "# ",
                    GlobalLobbyState.room_titles[RoomState.room_name],
                    class_name="text-xs text-gray-500 truncate",
                ),
                class_name="flex flex-col min-w-0",
            ),
            rx.el.button(
                rx.icon("x", class_name="h-5 w-5"),
                on_click=ChatUIState.close_thread,
                title="Close thread",
                aria_label="Close thread",
                class_name="p-2 rounded-lg text-gray-500 hover:bg-gray-100",
            ),
            class_name="h-16 px-4 border-b border-gray-200 flex items-center justify-between shrink-0",
        ),
        rx.el.div(
            rx.cond(
                RoomState.thread_roots.contains(thread_id),
                # Also in the room's list, which keeps the plain msg- id.
                message_item(RoomState.thread_roots[thread_id], 0, in_thread=True, anchor="thread-root-"),
                # Loaded again if the room let go of this thread.
                rx.el.p(
                    "Loading…",
                    on_mount=RoomState.open_thread(thread_id),
                    class_name="text-sm text-gray-400",
                ),
            ),
            rx.el.div(
                rx.el.span(
                    replies.length(),
                    rx.cond(replies.length() == 1, " reply", " replies"),
                    class_name="text-xs font-semibold text-gray-500",
                ),
                rx.el.div(class_name="flex-1 h-px bg-gray-200"),
                class_name="flex items-center gap-3 mb-4",
            ),
            rx.foreach(replies, lambda reply: message_item(reply, 0, in_thread=True)),
            id="relack-thread-messages",
            custom_attrs={"data-room": thread_id},
            class_name="flex-1 overflow-y-auto p-4 flex flex-col",
        ),
        rx.el.div(composer("thread"), class_name="p-3 border-t border-gray-200"),
        custom_attrs={"data-relack-drop": "relack-upload-thread"},
        class_name="w-[420px] max-w-[45vw] bg-white border-l border-gray-200 h-full flex flex-col shrink-0",
    )


def delete_dialog() -> rx.Component:
    return rx.alert_dialog.root(
        rx.alert_dialog.content(
            rx.alert_dialog.title("Delete message"),
            rx.alert_dialog.description(
                "Delete this message for everyone? This can't be undone.",
                size="2",
            ),
            rx.el.div(
                rx.alert_dialog.cancel(rx.button("Cancel", variant="soft", color_scheme="gray")),
                rx.alert_dialog.action(
                    rx.button(
                        "Delete",
                        color_scheme="red",
                        on_click=[RoomState.delete_message(ChatUIState.deleting_id), ChatUIState.cancel_delete],
                    )
                ),
                class_name="flex justify-end gap-3 mt-4",
            ),
            max_width="420px",
        ),
        open=ChatUIState.deleting_id != "",
        on_open_change=ChatUIState.set_delete_open,
    )


def search_message_row(hit: SearchHit) -> rx.Component:
    return rx.el.button(
        rx.image(src=avatar_url(hit.avatar_seed), class_name="size-8 rounded-full bg-violet-100 shrink-0"),
        rx.el.div(
            rx.el.div(
                rx.el.span(hit.display_name, class_name="text-sm font-semibold text-gray-900"),
                rx.el.span("in # ", hit.room_title, class_name="text-xs text-gray-500"),
                rx.cond(
                    hit.parent_id != "",
                    rx.el.span("thread reply", class_name="text-[10px] uppercase tracking-wide text-gray-400"),
                ),
                rx.el.span(local_datetime(hit.created_at), class_name="text-xs text-gray-400 ml-auto"),
                class_name="flex items-center gap-2",
            ),
            rx.el.p(
                hit.before,
                rx.el.mark(hit.match, class_name="bg-yellow-200 text-gray-900 rounded px-0.5"),
                hit.after,
                class_name="text-sm text-gray-700 mt-0.5 break-words",
            ),
            class_name="flex flex-col flex-1 min-w-0 text-left",
        ),
        on_click=ChatUIState.jump_to(hit.room, hit.message_id, hit.parent_id),
        class_name="w-full flex items-start gap-3 p-3 rounded-xl border border-gray-100 bg-white hover:border-violet-200 hover:shadow-sm transition-all",
    )


def search_file_row(hit: FileHit) -> rx.Component:
    url = rx.get_upload_url(hit.file.path)
    return rx.el.div(
        rx.cond(
            hit.file.is_image,
            rx.el.img(src=url, alt="", class_name="size-12 rounded-lg object-cover bg-gray-100 shrink-0"),
            rx.el.div(
                rx.icon("file-text", class_name="h-5 w-5"),
                class_name="size-12 rounded-lg bg-violet-100 text-violet-600 flex items-center justify-center shrink-0",
            ),
        ),
        rx.el.div(
            PlainLink.create(
                hit.file.name,
                href=url,
                target="_blank",
                rel="noopener noreferrer",
                class_name="text-sm font-semibold text-gray-900 hover:text-violet-600 truncate",
            ),
            rx.el.span(
                hit.file.size_label,
                " · ",
                hit.uploader,
                " in # ",
                hit.room_title,
                " · ",
                local_datetime(hit.created_at),
                class_name="text-xs text-gray-500 truncate",
            ),
            class_name="flex flex-col min-w-0 flex-1",
        ),
        rx.el.button(
            "Show in room",
            on_click=ChatUIState.jump_to(hit.room, hit.message_id, hit.parent_id),
            class_name="px-3 py-1.5 text-xs font-medium rounded-lg bg-violet-50 text-violet-600 hover:bg-violet-100 shrink-0",
        ),
        class_name="flex items-center gap-3 p-3 rounded-xl border border-gray-100 bg-white",
    )


def search_person_row(person: UserProfile) -> rx.Component:
    return rx.el.div(
        rx.image(src=avatar_url(person.avatar_seed), class_name="size-9 rounded-full bg-violet-100 shrink-0"),
        rx.el.div(
            rx.el.span(
                rx.cond(person.nickname != "", person.nickname, person.username),
                class_name="text-sm font-semibold text-gray-900 truncate",
            ),
            rx.el.span(
                rx.cond(person.email != "", person.email, rx.cond(person.is_guest, "Guest", person.username)),
                class_name="text-xs text-gray-500 truncate",
            ),
            class_name="flex flex-col min-w-0 flex-1",
        ),
        rx.el.button(
            "Profile",
            on_click=Intent.start("relack", "profile.view", user=person.username),
            class_name="px-3 py-1.5 text-xs font-medium rounded-lg text-gray-600 hover:bg-gray-100 shrink-0",
        ),
        rx.cond(
            person.username != AuthState.user.username,
            rx.el.button(
                "Message",
                on_click=GlobalLobbyState.open_direct_message(person.username),
                class_name="px-3 py-1.5 text-xs font-medium rounded-lg bg-violet-50 text-violet-600 hover:bg-violet-100 shrink-0",
            ),
        ),
        class_name="flex items-center gap-3 p-3 rounded-xl border border-gray-100 bg-white",
    )


def search_section(title: str, count, items, empty: str) -> rx.Component:
    return rx.el.section(
        rx.el.h3(
            title,
            rx.el.span(count, class_name="ml-2 text-xs font-semibold text-gray-400"),
            class_name="text-sm font-bold text-gray-700 uppercase tracking-wider mb-3",
        ),
        rx.cond(
            count > 0,
            rx.el.div(items, class_name="flex flex-col gap-2"),
            rx.el.p(empty, class_name="text-sm text-gray-400"),
        ),
        class_name="mb-8",
        aria_label=title,
    )


def search_view() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.h2("Search results", class_name="text-xl font-bold text-gray-900"),
                rx.el.p('for "', SearchState.searched, '"', class_name="text-sm text-gray-500"),
            ),
            rx.el.button(
                rx.icon("x", class_name="h-5 w-5"),
                on_click=SearchState.close,
                title="Close search",
                aria_label="Close search",
                class_name="p-2 rounded-lg text-gray-500 hover:bg-gray-100",
            ),
            class_name="flex items-start justify-between mb-6",
        ),
        search_section(
            "Messages",
            SearchState.messages.length(),
            rx.foreach(SearchState.messages, search_message_row),
            "No messages match.",
        ),
        search_section(
            "Files",
            SearchState.files.length(),
            rx.foreach(SearchState.files, search_file_row),
            "No files match.",
        ),
        search_section(
            "People",
            SearchState.people.length(),
            rx.foreach(SearchState.people, search_person_row),
            "No people match.",
        ),
        class_name="w-full max-w-3xl mx-auto p-6",
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


def message_list() -> rx.Component:
    return rx.el.div(
        rx.cond(
            rx.cond(ChatUIState.older.length() > 0, ChatUIState.has_older, RoomState.window_has_older),
            rx.el.button(
                rx.icon("history", class_name="h-3.5 w-3.5 mr-1.5"),
                "Load earlier messages",
                on_click=ChatUIState.load_earlier,
                custom_attrs={"data-relack-older": "1"},
                class_name="self-center flex items-center mb-4 px-3 py-1.5 text-xs font-medium rounded-full bg-white border border-gray-200 text-gray-600 hover:text-violet-600 hover:border-violet-200 transition-colors",
            ),
            rx.el.p(
                "This is the very beginning of ",
                rx.el.strong(GlobalLobbyState.room_titles[RoomState.room_name]),
                ".",
                class_name="self-center mb-6 text-xs text-gray-400",
            ),
        ),
        rx.foreach(
            ChatUIState.older,
            lambda msg, i: message_item(msg, rx.cond(i == 0, 0, ChatUIState.older[i - 1].created_at)),
        ),
        rx.foreach(
            RoomState.messages,
            lambda msg, i: message_item(
                msg, rx.cond(i == 0, ChatUIState.last_older_at, RoomState.messages[i - 1].created_at)
            ),
        ),
        id="relack-messages",
        custom_attrs={"data-room": RoomState.room_name},
        class_name="flex-1 overflow-y-auto p-6 flex flex-col",
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
                message_list(),
                rx.el.div(
                    composer("main"),
                    class_name="px-6 pt-3 pb-2 bg-white border-t border-gray-200",
                ),
                custom_attrs={"data-relack-drop": "relack-upload-main"},
                class_name="flex-1 flex flex-col h-full overflow-hidden bg-[#FAFAFA] min-w-0",
            ),
            rx.cond(ChatUIState.thread_id != "", thread_panel(), users_panel()),
            class_name="flex-1 flex overflow-hidden",
        ),
        class_name="flex-1 flex flex-col h-full bg-[#FAFAFA] overflow-hidden min-w-0",
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


_HEARTBEAT_JS = """
if (window.__relack_hb) clearInterval(window.__relack_hb);
window.__relack_hb = setInterval(function() {
    // In front, the open room counts as read; otherwise its messages stay unread.
    var front = document.visibilityState === 'visible' && document.hasFocus();
    var el = document.getElementById(front ? 'heartbeat-trigger' : 'heartbeat-hidden-trigger');
    if (el) { el.click(); }
    else { clearInterval(window.__relack_hb); window.__relack_hb = null; }
}, 3000);
"""


def _hidden_button(element_id: str, on_click) -> rx.Component:
    return rx.el.button(id=element_id, on_click=on_click, tab_index=-1, aria_hidden="true", class_name="sr-only")


def chat_dashboard() -> rx.Component:
    return rx.el.div(
        rx.el.style(CHAT_CSS),
        # Mentions of the viewer stand out.
        rx.el.style(
            '.relack-md a[href="' + AuthState.mention_href + '"] { color: #92400e !important; background: #fef3c7 !important; }'
        ),
        sidebar(),
        rx.match(
            LocalUIState.main_view,
            ("people", rx.el.div(people_view(), class_name="flex-1 overflow-y-auto")),
            ("search", rx.el.div(search_view(), class_name="flex-1 overflow-y-auto")),
            rx.cond(RoomState.in_room, chat_area(), empty_state()),
        ),
        incoming_calls(),
        delete_dialog(),
        upload_zone("main"),
        upload_zone("thread"),
        rx.el.input(
            id="relack-bridge",
            on_change=ChatUIState.bridge,
            tab_index=-1,
            aria_hidden="true",
            class_name="hidden",
        ),
        rx.el.span(GlobalLobbyState.activity, id="relack-activity", class_name="hidden"),
        rx.el.span(UnreadState.total, id="relack-unread-total", class_name="hidden"),
        rx.el.span(RoomState.history_rev, id="relack-history-rev", class_name="hidden"),
        _hidden_button("relack-refresh-older", ChatUIState.refresh_older),
        _hidden_button("heartbeat-trigger", [RoomState.heartbeat, CallState.heartbeat, UnreadState.sync(True)]),
        _hidden_button("heartbeat-hidden-trigger", [RoomState.heartbeat, CallState.heartbeat, UnreadState.sync(False)]),
        _hidden_button("unread-sync-visible", UnreadState.sync(True)),
        _hidden_button("unread-sync-hidden", UnreadState.sync(False)),
        rx.script(_HEARTBEAT_JS),
        rx.script(CLIENT_JS),
        custom_attrs={
            "data-relack-me": AuthState.user.username,
            "data-relack-room": RoomState.room_name,
            "data-relack-thread": ChatUIState.thread_id,
            "data-relack-sound": UnreadState.sound,
            "data-relack-desktop": UnreadState.desktop,
        },
        class_name="flex h-[calc(100vh-85px)] overflow-hidden bg-gray-50/50",
        # Ensure lobby link exists so room list is populated even after reloads.
        on_mount=[
            GlobalLobbyState.join_lobby,
            RoomState.rejoin_last_room,
            RoomState.heartbeat,
            UnreadState.sync(True),
            rx.call_script(
                "typeof Notification === 'undefined' ? 'unsupported' : Notification.permission",
                callback=UnreadState.set_permission,
            ),
        ],
        on_unmount=RoomState.handle_leave_room,
        on_focus=RoomState.heartbeat,
        on_mouse_enter=RoomState.heartbeat,
        on_mouse_move=RoomState.heartbeat.throttle(2000),
        tab_index=0,
    )
