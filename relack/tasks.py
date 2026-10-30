"""Background work of the server: scheduled posts and message retention."""

import asyncio
import logging
import time

from relack import db, permissions, posting

TICK_SECONDS = 15
RETENTION_EVERY_SECONDS = 3600


async def send_due_posts():
    rooms = db.load_rooms()
    profiles = db.load_profiles()
    for row in db.due_scheduled():
        room = rooms.get(row["room"])
        profile = profiles.get(row["username"])
        try:
            if room is not None and not room.archived and room.can_view(row["username"]) and not permissions.is_pending(profile):
                name = (profile.nickname if profile else "") or row["username"]
                await posting.post(
                    room, row["username"], name, row["text"], mentions=permissions.can(profile, "mention_users")
                )
        except Exception:
            logging.exception("scheduled post %s failed", row["id"])
        db.remove_scheduled(row["id"])


def apply_retention():
    days = int(db.get_setting("retention_days", 0) or 0)
    if days > 0 and (removed := db.purge_older_than(days)):
        db.audit("system", "retention.purge", detail=f"{removed} messages older than {days} days")
        # Open rooms reload at their next heartbeat.
        db.set_setting("data_version", time.time())


async def run():
    """Lifespan task."""
    last_retention = 0.0
    while True:
        await asyncio.sleep(TICK_SECONDS)
        try:
            await send_due_posts()
            if time.time() - last_retention > RETENTION_EVERY_SECONDS:
                last_retention = time.time()
                apply_retention()
        except Exception:
            logging.exception("relack background task failed")
