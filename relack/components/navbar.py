import reflex as rx
from reflex.components.react_router.dom import ReactRouterLink
from relack.states.auth_state import AuthState
from relack.states.shared_state import GlobalLobbyState
from relack.states.admin_state import AdminState
from relack.i18n import LangState, T

_THEME_JS = """
(function () {
  function apply(dark) {
    document.documentElement.classList.toggle('relack-dark', dark);
    document.querySelectorAll('.radix-themes').forEach(function (el) {
      el.classList.toggle('dark', dark);
      el.classList.toggle('light', !dark);
    });
  }
  window.relackToggleTheme = function () {
    var dark = !document.documentElement.classList.contains('relack-dark');
    try { localStorage.setItem('relack_theme', dark ? 'dark' : 'light'); } catch (e) {}
    apply(dark);
  };
  try { apply(localStorage.getItem('relack_theme') === 'dark'); } catch (e) {}
})();
"""

_DARK_CSS = """
html.relack-dark body, html.relack-dark .bg-white, html.relack-dark .bg-white\\/80 { background-color: #111827 !important; }
html.relack-dark .bg-gray-50, html.relack-dark .bg-gray-50\\/50, html.relack-dark .bg-\\[\\#FAFAFA\\] { background-color: #0b1220 !important; }
html.relack-dark .bg-gray-100 { background-color: #1f2937 !important; }
html.relack-dark .bg-violet-50 { background-color: #2e1065 !important; }
html.relack-dark .text-gray-900, html.relack-dark .text-gray-800 { color: #f3f4f6 !important; }
html.relack-dark .text-gray-700, html.relack-dark .text-gray-600 { color: #d1d5db !important; }
html.relack-dark .text-gray-500, html.relack-dark .text-gray-400 { color: #9ca3af !important; }
html.relack-dark .border-gray-100, html.relack-dark .border-gray-200 { border-color: #374151 !important; }
html.relack-dark .bg-gray-200 { background-color: #374151 !important; }
html.relack-dark .relack-md a[href^="#mention-"]:not([href="#mention-here"]) { color: #c4b5fd; background: rgba(167, 139, 250, 0.18); }
html.relack-dark textarea, html.relack-dark input { color: #f3f4f6; background-color: transparent; }
html.relack-dark .relack-md code { background: rgba(255, 255, 255, 0.1); color: #f9a8d4; }
html.relack-dark .relack-mention-pop, html.relack-dark .relack-note { background: #1f2937; border-color: #374151; }
html.relack-dark .relack-mention-item.active { background: #2e1065; }
html.relack-dark .relack-mention-name { color: #f3f4f6; }
"""


def navbar() -> rx.Component:
    return rx.el.nav(
        rx.el.style(_DARK_CSS),
        rx.script(_THEME_JS),
        rx.el.div(
            rx.el.div(
                rx.icon("message-circle", class_name="h-6 w-6 text-violet-600"),
                rx.el.div(
                    rx.el.span(
                        "Relack",
                        class_name="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-violet-600 to-indigo-600 leading-none",
                    ),
                    rx.el.span(
                        "Reflex Real-Time Chat",
                        class_name="text-[10px] text-gray-400 font-medium uppercase tracking-wider leading-none",
                    ),
                    class_name="flex flex-col",
                ),
                class_name="flex items-center gap-2",
            ),
            rx.el.div(
                rx.el.button(
                    rx.cond(LangState.lang == "zh", "EN", "中"),
                    on_click=LangState.toggle,
                    title="中文 / English",
                    aria_label="Switch language",
                    class_name="px-2 py-1 mr-2 text-sm font-semibold text-gray-500 hover:text-violet-600 rounded-lg",
                ),
                rx.el.button(
                    rx.icon("moon", class_name="h-4 w-4"),
                    on_click=rx.call_script("window.relackToggleTheme()"),
                    title="Dark mode",
                    aria_label="Dark mode",
                    class_name="p-2 mr-2 text-gray-500 hover:text-violet-600 rounded-lg",
                ),
                rx.el.button(
                    rx.icon("link", class_name="h-4 w-4"),
                    rx.el.span(T("Copy Link"), class_name="text-sm font-medium ml-2"),
                    on_click=[
                        rx.set_clipboard(AuthState.router.url),
                        rx.toast("Link copied to clipboard!", duration=3000),
                    ],
                    class_name="relack-navbar-extra flex items-center px-4 py-2 mr-4 text-gray-500 hover:text-violet-600 hover:bg-violet-50 rounded-xl transition-all active:scale-95 border border-transparent hover:border-violet-100",
                ),
                rx.cond(
                    AuthState.is_admin,
                    rx.el.button(
                        rx.icon("trash-2", class_name="h-4 w-4"),
                        rx.el.span("Clear DB", class_name="text-sm font-medium ml-2"),
                        on_click=GlobalLobbyState.clear_all_data,
                        class_name="flex items-center px-4 py-2 mr-4 text-red-500 hover:bg-red-50 rounded-xl transition-all active:scale-95 border border-transparent hover:border-red-100",
                    ),
                ),
                rx.cond(
                    AuthState.user,
                    rx.el.div(
                        ReactRouterLink.create(
                            rx.el.div(
                                rx.image(
                                    src=f"https://api.dicebear.com/9.x/notionists/svg?seed={AuthState.user.avatar_seed}",
                                    class_name="h-8 w-8 rounded-full bg-violet-100",
                                ),
                                rx.el.div(
                                    rx.el.span(
                                        rx.cond(
                                            AuthState.user.nickname != "",
                                            AuthState.user.nickname,
                                            AuthState.user.username,
                                        ),
                                        class_name="text-sm font-bold text-gray-900 leading-none",
                                    ),
                                    rx.el.div(
                                        rx.cond(
                                            AuthState.user.is_guest,
                                            rx.el.div(
                                                rx.icon("ghost", class_name="h-3 w-3 mr-1"),
                                                rx.el.span(
                                                    T("Signed in as guest"),
                                                    class_name="text-[10px] font-medium whitespace-nowrap",
                                                ),
                                                class_name="flex items-center text-violet-600 bg-violet-50 px-1.5 py-0.5 rounded-md mt-0.5",
                                            ),
                                            rx.el.div(
                                                rx.icon("circle-check", class_name="h-3 w-3 mr-1"),
                                                rx.el.span(
                                                    T("Signed in with Google"),
                                                    class_name="text-[10px] font-medium whitespace-nowrap",
                                                ),
                                                class_name="flex items-center text-green-600 bg-green-50 px-1.5 py-0.5 rounded-md mt-0.5",
                                            ),
                                        ),
                                    ),
                                    class_name="flex flex-col",
                                ),
                                class_name="flex items-center gap-3 px-4 py-2 rounded-2xl bg-white border border-gray-100 hover:border-violet-200 hover:shadow-sm transition-all",
                            ),
                            to=f"/profile/{AuthState.user.username}",
                        ),
                        rx.el.div(class_name="w-px h-8 bg-gray-100 mx-4"),
                        rx.el.button(
                            rx.el.div(
                                rx.icon("log-out", class_name="h-4 w-4"),
                                T("Logout"),
                                class_name="flex items-center gap-2",
                            ),
                            on_click=AuthState.logout,
                            class_name="text-sm font-medium text-gray-500 hover:text-red-600 transition-colors",
                        ),
                        class_name="flex items-center",
                    ),
                    rx.cond(
                        AdminState.is_authenticated,
                        rx.el.div(
                            rx.el.div(
                                rx.icon("shield-check", class_name="h-4 w-4 text-white"),
                                "Admin Mode",
                                class_name="flex items-center gap-2 px-3 py-1 bg-gray-900 text-white text-sm font-medium rounded-full",
                            ),
                            rx.el.button(
                                rx.icon("log-out", class_name="h-4 w-4"),
                                "Exit",
                                on_click=AdminState.logout,
                                class_name="flex items-center gap-2 text-sm text-gray-500 hover:text-red-600 transition-colors ml-4",
                            ),
                            class_name="flex items-center",
                        ),
                        rx.el.span(
                            "Not Connected", class_name="text-sm text-gray-400 italic"
                        ),
                    ),
                ),
                class_name="flex items-center",
            ),
            class_name="flex items-center justify-between w-full max-w-7xl mx-auto",
        ),
        class_name="relack-navbar w-full bg-white/80 backdrop-blur-md border-b border-gray-200 px-6 py-4 sticky top-0 z-50",
    )