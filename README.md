<p align="center">
  <img src="assets/relack-icon.svg" width="96" alt="Relack icon">
</p>

<h1 align="center">Relack</h1>

<p align="center">
  <b>Your team's chat, on your own terms.</b><br>
  An open-source team chat you run on your own server, written entirely in Python with <a href="https://reflex.dev/">Reflex</a>.
</p>

<p align="center">
  <img src="docs/images/relack-tour.gif" width="720" alt="A short tour of Relack: rich messages, mentions, threads, files, search, calls, webhooks and a phone">
</p>

Every decision your team makes ends up in a chat: your plans, your customers, your code. Relack gives you the team chat you expect on a server you control. Rooms, threads, calls, search and an admin console all run on your own machine, and the history sits in one SQLite file beside one folder of uploads.

## What you get

| | |
|---|---|
| **Rooms** | Public rooms, private rooms, direct messages and group messages |
| **Messages** | Markdown, code blocks, link previews, reactions, threads, editing and deleting |
| **Mentions** | `@name`, `@here`, `@channel`, unread counts, desktop notifications and a sound |
| **Files** | Attach, paste or drop, up to 200 MB per file; pictures show in the message |
| **Search** | Messages, files and people, across every room you can see |
| **Later** | Pins, saved messages, reminders and scheduled messages |
| **Calls** | Ring a room or a person; the call keeps running while you work |
| **Automation** | Incoming webhooks and slash commands |
| **Admin** | Approval, permissions, audit log, message retention, export and import |
| **Anywhere** | English and 中文, dark mode, phones and the home screen |
| **Sign-in** | Guest nicknames and Google accounts |

## Motivation

As SaaS services like Slack continue to expand globally, they have become the standard for enterprise communication. However, this convenience comes with a cost: data sovereignty and confidentiality.

Many enterprises are increasingly concerned that storing sensitive internal communications and trade secrets on third-party servers—often located in different jurisdictions—exposes them to risks. These risks include potential access by foreign governments, data breaches, or unauthorized surveillance.

**Relack** was created to solve this problem. By providing a solution that can be fully self-hosted and controlled within your own infrastructure, Relack ensures that your organization's critical information remains private and secure, without sacrificing the modern chat experience.

## A tour

Every screen below comes from a running Relack. The people and messages are made up.

![Relack with the room list on the left and the conversation beside it](docs/images/chat-dashboard.png)

### Rooms and rich messages

Public rooms, private rooms and direct messages sit in one list. Write in Markdown or use the toolbar under the box: bold text, lists and code blocks just look right. Input methods work too: Enter never sends while a Chinese word is still being composed.

![A room with a formatted checklist, a code block and a Chinese message](docs/images/messages.png)

### Mentions and notifications

Type `@` and pick a name. They get a badge on the room, a sound and a desktop notification. `@here`, `@channel` and `@everyone` reach the whole room.

![The list of names open above the message box](docs/images/mentions.png)

### Reactions and threads

A reaction says "got it" in one tap. Replies go into a side panel, so the main room stays calm.

![A message with reactions and its thread open beside the room](docs/images/thread.png)

### Files and pictures

Attach a file, paste a screenshot or drop it on the room. Pictures show in the message and open in a viewer; other files become a card that downloads them.

![A pasted picture and a PDF in the conversation](docs/images/files.png)

### History and search

Nothing gets lost. Rooms keep their whole history, and search finds messages, files and people in every room you can see. A click takes you straight to the message.

![Search results for the word pricing](docs/images/search.png)

### Pins, reminders and scheduled messages

The `⋯` menu on a message pins it to the room, saves it for later, sets a reminder, forwards it or copies a link to it. The clock beside Send schedules a message, and **Saved & scheduled** lists everything waiting.

![The Saved and scheduled page](docs/images/saved-and-scheduled.png)

### Calls

Start a call from any room or direct message and everyone gets rung. The call runs in a separate call app, such as the self-hosted [LiveKit audio chat](https://github.com/milochen0418/reflex_ddns_livekit_audio_chat), and keeps running in a small tray while you go back to work. See [Calls](#calls) for the details.

![A call between two people, in a dialog over the room](docs/images/call.png)

### Webhooks and slash commands

Your tools can post into a room. Create a webhook in the room's settings, then send it JSON:

```bash
curl -X POST https://your-server/api/relack/hooks/<token> \
  -H "Content-Type: application/json" \
  -d '{"text": "✅ Build #482 passed on `main`, ready to deploy"}'
```

Commands such as `/status 🌴 On holiday`, `/later 2h text` and `/dnd 1h` keep your hands on the keyboard; `/help` lists them all.

![The Room settings dialog with a webhook, its address blurred here](docs/images/room-settings.png)

### Admin controls

Everything is open until you tighten it. Decide who gets in and who can create rooms, see who did what in the audit log, and set how long messages are kept.

<table>
  <tr>
    <td><img src="docs/images/admin-permissions.png" alt="Permissions settings"></td>
    <td><img src="docs/images/admin-audit-log.png" alt="The audit log"></td>
  </tr>
</table>

### Your way, on any screen

English and 中文, light and dark, desktop and phone. The site can also be added to a phone's home screen.

<table>
  <tr>
    <td width="42%"><img src="docs/images/dark-mode.png" alt="Relack in dark mode"></td>
    <td width="42%"><img src="docs/images/chinese.png" alt="Relack in Chinese"></td>
    <td width="16%"><img src="docs/images/phone.png" alt="Relack on a phone"></td>
  </tr>
</table>

### Sign in your way

Guests join with a nickname in seconds, and Google accounts keep a permanent profile.

<table>
  <tr>
    <td><img src="docs/images/guest-login.png" alt="Signing in as a guest"></td>
    <td><img src="docs/images/google-login.png" alt="Signing in with Google"></td>
  </tr>
</table>

## Getting Started

This project is managed with [Poetry](https://python-poetry.org/).

### Prerequisites

- Python 3.15 (`pyproject.toml` allows 3.11 – 3.15)
- Poetry

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/milochen0418/relack.git
   cd relack
   ```

2. Install dependencies:
   ```bash
   poetry env use python3.15
   poetry install
   ```

### Environment variables (.env)

Copy the template and fill in the values before running the app:

```bash
cp .env.template .env
```

Set these in `.env`:

- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
   1) In Google Cloud Console, create OAuth 2.0 credentials → Web application.
   2) Authorized JavaScript origins: add `http://localhost:3000` (plus your deploy domain later).
   3) Authorized redirect URIs: add `http://localhost:3000/auth/google/callback` (plus your deploy domain later).
   4) Paste the client ID/secret into `.env`. Wrong or missing values will raise "Invalid audience" during Google login. Reference: https://github.com/masenf/reflex-google-auth
- `ADMIN_PASSCODE`: Any secret string you define. It unlocks the in-app admin dashboard (via the "Administrator Settings" link). Keep it private and change it for your environment.

### Running the App

Start the development server (via Poetry env):

```bash
poetry run reflex run
```

The application will be available at `http://localhost:3000`.

For quick restarts during development (kills anything on ports 3000/8000, then restarts Reflex):

```bash
poetry run ./reflex_rerun.sh
```

### Python version help (common first-run issue)

If you see an error like `Current Python version (3.x) is not allowed by the project (>=3.11,<3.16)`, point Poetry at a 3.15 interpreter and retry:

macOS (Homebrew Python 3.15):

```bash
brew install python@3.15
poetry env use /opt/homebrew/bin/python3.15
poetry install
```

If you already have `python3.15` on your PATH (e.g., from an existing install), you can simply run:

```bash
poetry env use python3.15
poetry install
```

After switching, rerun the server:

```bash
poetry run reflex run
```

## Messages

- **History**: rooms, messages, people, settings and logins are kept in a SQLite database, `relack.db`, so they survive restarts. A room opens with its latest 100 messages; **Load earlier messages** goes further back. Times show in each viewer's own time zone, with a divider where the day changes.
- **Writing**: Enter sends, Shift+Enter starts a new line (Enter never sends while an input method such as Zhuyin is still composing), and Enter inside a ` ``` ` block adds a line. Messages are Markdown: `**bold**`, `_italic_`, `~~strike~~`, `` `code` ``, ` ``` ` code blocks, `>` quotes and lists; the toolbar under the box (and Ctrl/Cmd+B, Ctrl/Cmd+I) adds the marks for you. Links show a preview as before.
- **Reactions, threads, edit, delete**: hover a message for quick reactions, the emoji picker, **Reply in thread** (replies open in a side panel; the message shows how many replies it has), and, on your own messages, **Edit** (shows "(edited)") and **Delete**. A deleted message that has replies stays as "This message was deleted." until its last reply goes.
- **Files**: attach files with the paperclip, paste a screenshot into the box, or drop files on the room. They wait above the box until you send. Pictures show in the message; other files as a card that downloads them. Files are stored under `uploaded_files/relack/` at unguessable addresses (anyone holding a link can open it). The limit is 200 MB per file (`RELACK_MAX_UPLOAD_MB`).
- **Search**: the box above the room list filters rooms as you type; Enter searches messages, files and people in every room you can see. Clicking a message opens it in its room (or thread), highlighted.
- **Mentions and notifications**: type `@` to pick someone (or `@here`, `@channel`, `@everyone` for everyone who has opened the room). Unread counts belong to the person, not the browser tab: the room list shows them (red for mentions and direct messages) and the tab title shows the total. Direct messages, mentions and replies in threads you started or replied in also bring a desktop notification and a sound; the bell above the room list turns them on or off for that browser.

A guest's nickname is their identity, so it can't contain `@` (Google accounts are their email address), be "System" (owner of the default rooms) or be a member's username. Room names starting with `dm-` are kept for direct messages. Import, export and approvals need the admin passcode.

Where `relack.db` lives: in the App Store, beside the app's `reflex.db` on its own volume (SQLite files must not be shared with the host); run locally, in `.relack/` (which the dev server's hot reload ignores). `RELACK_DB_PATH` sets another place. **Admin → Data Maintenance → Export Data** saves everything except the files themselves.

E2E suites:

```bash
poetry run ./run_test_suite.sh chat_messages      # formatting, IME, reactions, threads, edit, delete, history
poetry run ./run_test_suite.sh chat_notify        # @mentions, unread counts, notifications
poetry run ./run_test_suite.sh chat_files_search  # attach, paste, drop, search
poetry run ./run_test_suite.sh chat_persistence   # restart with Reflex's state files deleted
poetry run ./run_test_suite.sh chat_guards        # guest names, dm- names, look-alike rooms
poetry run ./run_test_suite.sh chat_rules         # permissions, approval, audit log
poetry run ./run_test_suite.sh chat_rooms         # rename, leave, mute, archive, webhooks, commands
poetry run ./run_test_suite.sh chat_later         # pin, save, remind, forward, links, scheduling
poetry run ./run_test_suite.sh chat_presence      # status, typing, language, dark mode, phones
poetry run ./run_test_suite.sh chat_layout        # every panel opens and closes at 10 screen widths
```

`chat_messages` replaces all data through the admin import (like `private_room` and `people_intent`), so run the suites against a test server.

## Rooms, people and admin

- **Rooms**: the gear in a room's header renames it, edits its description, adds or removes members of a private room, mutes it for you, manages webhooks and archives it (read-only, restored from **Browse rooms**). **Browse rooms** also leaves and rejoins public rooms. **New room → Group message** starts a direct message with several people.
- **Message menu (⋯)**: pin to the room, save for later, remind me, forward, copy a link to the message. **Saved & scheduled** lists saved and scheduled messages; the clock beside Send schedules a message.
- **Status**: a status with an emoji shows beside your messages; pausing notifications holds them back (reminders still come). "Who is typing" shows above the box.
- **Commands**: `/help`, `/shrug`, `/me`, `/later 2h text`, `/mute`, `/unmute`, `/leave`, `/status 🌴 text`, `/dnd 1h`, `/topic text`, `/rename name`, `/archive`.
- **Webhooks**: `POST /api/relack/hooks/<token>` with `{"text": "..."}` (optionally `"username"`) posts in the room; each room's settings create and delete them. Anyone holding the address can post, so treat it as a password.
- **Admin**: everything is open until the admin tightens it under **Settings → Permissions** (approval, creating rooms, mentions, profiles; guests and Google accounts apart). A Google account can be made an admin in **Users**: no passcode needed, can delete anyone's messages and rooms, and only admins can use **Clear DB**. **Audit log** records logins, room, member and admin actions; **Message retention** deletes messages and their files after a number of days.
- **Interface**: the top bar switches English / 中文 and dark mode for that browser. Below 768 px wide the room list is a drawer (close it with its button, a tap beside it or Esc); below 1100 px threads and online users slide over the chat. Phones get a one-column layout; the site can be added to the home screen. Push notifications to a closed phone app are not included.

## Calls

Every room (public, private, or direct message) has a call button in its header. The call itself runs in a separate call app, opened in a dialog through the DDNS Intent `call.join`. relack doesn't name the call app: it uses whichever installed app provides `call.join`, as reported by the re-ddns intent registry (for example the self-hosted [LiveKit audio chat](https://github.com/milochen0418/reflex_ddns_livekit_audio_chat) at `livekit.reflex-ddns.com`).

- **Choosing the call app**: if several apps provide `call.join` (e.g. audio, video and avatar chat), whoever starts the call chooses one. The call keeps that choice: everyone who answers or joins later goes straight into the same app, without being asked, because calls in different apps can't reach each other. The next call is chosen afresh.
- **Who gets rung**: everyone who can see the room for private rooms and direct messages, and the people who have it open for public rooms. A popup offers Accept / Decline for about 45 seconds. After that, a room in a call shows a green badge in the sidebar and a **Join call** button in its header.
- **Keeps running**: other dialogs (People → Pick member, profiles…), the **–** button, a click outside the call or Escape minimize the call to a tray at the bottom left; you keep talking while you use relack, including on other pages such as profiles. Click the tray (or **Join call**) to bring it back.
- **Picture-in-picture**: drag the tray's bar along the bottom to move it. Drag it up and it becomes a small window of the call, showing the call as it looks in full, view only: its buttons don't respond. Click the window to bring the call back, drag its corner to resize it, or push it down to the bottom to turn it back into the bar. The window stays where you left it, also after a reload.
- **Leaving**: hanging up, the call's **×** (in the dialog or the tray), or starting another call takes you out of the call. The call ends when its last person leaves.
- **Privacy**: each call gets a random id, so the call of a private room can't be guessed from its name. The id is passed to the call app privately (by postMessage), so it never appears in the dialog's URL.

Settings (all optional):

- `DDNS_INTENT_PROVIDER_CALL_JOIN`: the app(s) that handle `call.join` when there is no registry, e.g. `livekit` for local development. Any app implementing the intent works; see the [contract](https://github.com/milochen0418/reflex_ddns_livekit_audio_chat#-calls-from-other-apps-ddns-intent-calljoin).
- `DDNS_INTENT_URL_LIVEKIT`: where that app runs, for local development (e.g. `http://localhost:3200`).
- `RELACK_CALL_APP`: always use this app, skipping the registry.

E2E suite (the call app must be running at `DDNS_INTENT_URL_LIVEKIT`, on media ports that are free locally):

```bash
DDNS_INTENT_PROVIDER_CALL_JOIN=livekit DDNS_INTENT_URL_LIVEKIT=http://localhost:3200 \
DDNS_INTENT_URL_RELACK=http://localhost:3000 poetry run ./run_test_suite.sh call_intent
```

Choosing among several call apps: the same call app also stands in as a second one, `livekit-alt`, reached at `127.0.0.1` (another origin):

```bash
DDNS_INTENT_PROVIDER_CALL_JOIN=livekit,livekit-alt DDNS_INTENT_URL_LIVEKIT=http://localhost:3200 \
DDNS_INTENT_URL_LIVEKIT_ALT=http://127.0.0.1:3200 poetry run ./run_test_suite.sh call_app_choice
```

The minimized call's bar and picture-in-picture window:

```bash
DDNS_INTENT_PROVIDER_CALL_JOIN=livekit DDNS_INTENT_URL_LIVEKIT=http://localhost:3200 \
poetry run ./run_test_suite.sh call_pip
```

## Architecture & Design

Interested in how Relack is built? Check out our [Project Design and Architecture Overview](docs/Relack%20Project%20Design%20and%20Architecture%20Overview.pdf).

## License

MIT. See [LICENSE](LICENSE).
