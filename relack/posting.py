"""Messages that don't come from an open tab: scheduled posts and webhooks.

They go straight into relack.db; rooms pick them up on their next heartbeat
(RoomState._catch_up) and everyone's unread counts follow.
"""

from relack import db
from relack.formatting import plain_text, resolve_mentions
from relack.link_preview import fetch_preview, first_url, split_message
from relack.models import RoomInfo

MAX_MESSAGE_CHARS = 20000


async def post(room: RoomInfo, sender: str, display_name: str, text: str, *, mentions: bool = True) -> str:
    people = db.room_people(room) if mentions else {}
    content, mentioned = resolve_mentions(text[:MAX_MESSAGE_CHARS], people)
    plain = plain_text(content, db.display_names())
    url = first_url(split_message(plain))
    preview = await fetch_preview(url) if url else None
    msg_id, _seq = db.insert_message(
        room=room.name, sender=sender, display_name=display_name, content=content,
        plain=plain, mentions=mentioned, preview=preview,
    )
    return msg_id
