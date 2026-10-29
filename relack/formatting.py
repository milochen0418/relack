"""Mentions in message text, and the Markdown a message bubble shows.

People type `@Name` (the composer's autocomplete inserts it). On send, every
`@` followed by the name or username of someone who can see the room becomes a
`<@username>` token, and `@here` / `@channel` / `@everyone` become `<!here>`
(and so on), so a mention keeps pointing at the person after a rename. Text in
`code` spans and ``` blocks is left alone.
"""

from __future__ import annotations

import re
from urllib.parse import quote

SPECIAL_MENTIONS = ("here", "channel", "everyone")
# Stored in a message's mention list for @here / @channel / @everyone.
EVERYONE = "@here"

_TOKEN_RE = re.compile(r"<@([^<>\s]+)>|<!(here|channel|everyone)>")
_CODE_RE = re.compile(r"```.*?(?:```|$)|`[^`\n]*`", re.S)
_ASCII_WORD = re.compile(r"[A-Za-z0-9_]")


def _segments(text: str):
    """Yield (is_code, piece) runs of the text."""
    pos = 0
    for m in _CODE_RE.finditer(text):
        if m.start() > pos:
            yield False, text[pos : m.start()]
        yield True, m.group(0)
        pos = m.end()
    if pos < len(text):
        yield False, text[pos:]


def resolve_mentions(text: str, people: dict[str, str]) -> tuple[str, list[str]]:
    """Turn typed `@Name` mentions into tokens.

    `people` maps the username of everyone who can see the room to their
    display name. Returns the text to store and the mentioned usernames
    (plus EVERYONE for @here / @channel / @everyone).
    """
    # Names to look for after "@", by their first letter, longest first
    # (so "@Ann Lee" wins over "@Ann").
    buckets: dict[str, list[tuple[str, str]]] = {}

    def add(name: str, token: str):
        if name:
            buckets.setdefault(name[0].casefold(), []).append((name, token))

    for username, name in people.items():
        add(username, f"<@{username}>")
        add(name, f"<@{username}>")
    for word in SPECIAL_MENTIONS:
        add(word, f"<!{word}>")
    for names in buckets.values():
        names.sort(key=lambda n: len(n[0]), reverse=True)

    mentioned: list[str] = []
    out: list[str] = []
    for is_code, piece in _segments(text):
        if is_code:
            out.append(piece)
            continue
        i = 0
        while i < len(piece):
            ch = piece[i]
            if ch == "@" and i + 1 < len(piece) and (i == 0 or not _ASCII_WORD.match(piece[i - 1])):
                for name, token in buckets.get(piece[i + 1].casefold(), ()):
                    end = i + 1 + len(name)
                    if piece[i + 1 : end].casefold() == name.casefold() and not (
                        end < len(piece) and _ASCII_WORD.match(piece[end])
                    ):
                        out.append(token)
                        who = EVERYONE if token.startswith("<!") else token[2:-1]
                        if who not in mentioned:
                            mentioned.append(who)
                        i = end
                        break
                else:
                    out.append(ch)
                    i += 1
                continue
            out.append(ch)
            i += 1
    return "".join(out), mentioned


def _replace_tokens(text: str, fmt) -> str:
    out = []
    for is_code, piece in _segments(text):
        out.append(piece if is_code else _TOKEN_RE.sub(fmt, piece))
    return "".join(out)


def plain_text(text: str, people: dict[str, str]) -> str:
    """The text with mentions as `@Name` again (edit box, search, notifications)."""

    def fmt(m: re.Match) -> str:
        if m.group(2):
            return "@" + m.group(2)
        return "@" + (people.get(m.group(1)) or m.group(1))

    return _replace_tokens(text, fmt)


def _escape_link_text(name: str) -> str:
    return name.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def render_markdown(text: str, people: dict[str, str]) -> str:
    """Markdown for the bubble: mentions become `#mention-<username>` links."""

    def fmt(m: re.Match) -> str:
        if m.group(2):
            return f"[@{m.group(2)}](#mention-{m.group(2)})"
        username = m.group(1)
        name = people.get(username) or username
        return f"[@{_escape_link_text(name)}](#mention-{quote(username, safe='')})"

    return _replace_tokens(text, fmt)


def mention_href(username: str) -> str:
    return "#mention-" + quote(username, safe="")


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def snippet(text: str, query: str, width: int = 60) -> tuple[str, str, str]:
    """Split `text` around the first match of `query` (case-insensitive)."""
    flat = " ".join(text.split())
    at = flat.lower().find(query.lower()) if query else -1
    if at < 0:
        return (flat[: width * 2] + ("…" if len(flat) > width * 2 else ""), "", "")
    start = max(0, at - width)
    end = at + len(query)
    before = ("…" if start > 0 else "") + flat[start:at]
    after = flat[end : end + width] + ("…" if end + width < len(flat) else "")
    return before, flat[at:end], after
