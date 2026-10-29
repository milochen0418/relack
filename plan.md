# Relack — Current Feature Map

## Auth & Identity
- Guest login with nickname; Google OAuth login (profile stored in LocalStorage)
- Logout clears LocalStorage / SessionStorage and redirects home
- Profile page with nickname/bio editing (self only); avatars via seeded images

## Rooms & Messaging
- Global lobby shared state with default rooms (General / Tech Talk / Random)
- Create / delete rooms (creator-only delete); join/leave rooms; remember last room per tab
- Rooms, profiles, messages, settings and logins stored in SQLite (`relack/db.py`, `relack.db`); open rooms keep their latest 100 messages in shared state, older ones load per tab
- Messages: Markdown (toolbar, Shift+Enter, IME-safe Enter), local times with day dividers, reactions, threads (side panel), edit / delete own messages
- Files: paperclip, paste, drag and drop (`uploaded_files/relack/`), pictures inline
- Search: rooms as you type; messages (FTS5 trigram), files and people on Enter, with jump to the message
- **Optimized Room Joining:** Prevents UI flicker and unselected state when clicking the already active room (early return logic).
- **Persistent Selection:** Ensures room selection remains active on UI during room switches.

## Presence & Unread
- Per-room online user list with stale-session pruning via heartbeat/disconnect
- Read positions per user in the database: unread and mention badges, total in the tab title
- @mentions with autocomplete; desktop notifications and a sound for direct messages, mentions and thread replies
- **Reliable Tab State:** Fixes regression where leaving a room accidentally cleared the session's selected room state.

## Admin & Permissions
- Admin passcode gate; admin menu toggle and tabs
- Permission toggles scaffold (guest/google create room, mention, view profile, approvals)
- Global clear/reset data (rooms, profiles, messages, permissions)
- Export/import lobby snapshot (JSON) and download

## UI/UX
- Responsive dual-pane layout (sidebar + chat area); modern styled navbar, sidebar, badges
- Room list with unread badge, creator metadata, and quick create button
- Online users panel with status indicator; smooth hover/active styles
- **Stable Navigation:** clicking the current room updates status without resetting the view.
