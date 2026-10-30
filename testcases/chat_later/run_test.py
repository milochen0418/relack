"""E2E: pin, save, remind, schedule, forward, link to a message.

The reminder is made due by editing relack.db, so this needs a local server.

    poetry run ./run_test_suite.sh chat_later
"""

import os
import sqlite3
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import expect, sync_playwright

load_dotenv()

BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000").rstrip("/")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
DB = Path(__file__).resolve().parents[2] / ".relack" / "relack.db"
STAMP = str(int(time.time()))[-5:]
USER = "Later" + STAMP
ROOM = "Notes " + STAMP
OTHER = "Inbox " + STAMP


def menu(page, msg, action):
    msg.hover()
    msg.get_by_role("button", name="More actions").click()
    page.get_by_role("button", name=action, exact=True).click()


def run():
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    shots: dict[str, bytes] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900}, permissions=["clipboard-read", "clipboard-write"])
        page = ctx.new_page()
        try:
            page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
            page.get_by_placeholder("CoolPanda99").fill(USER)
            page.get_by_role("button", name="Continue as Guest").click()
            for name in (OTHER, ROOM):
                page.get_by_role("button", name="New room").click()
                dialog = page.get_by_role("dialog", name="Create New Room")
                dialog.get_by_placeholder("e.g. Design Team").fill(name)
                dialog.get_by_role("button", name="Create Room").click()
                page.locator("aside").get_by_role("heading", name=name, exact=True).wait_for(timeout=15000)
                page.wait_for_timeout(500)
            page.locator("aside").get_by_role("heading", name=ROOM, exact=True).click()
            box = page.get_by_role("textbox", name="Message", exact=True)
            box.click()
            page.keyboard.type("keep this " + STAMP)
            page.keyboard.press("Enter")
            msg = page.locator("#relack-messages [id^=msg-]").filter(has_text="keep this " + STAMP)
            expect(msg).to_have_count(1, timeout=10000)

            print("Pin...")
            menu(page, msg, "Pin to room")
            expect(msg.locator("svg.lucide-pin")).to_be_visible(timeout=10000)
            page.get_by_role("button", name="Pinned messages").click()
            expect(page.get_by_role("dialog").get_by_text("keep this " + STAMP)).to_be_visible(timeout=10000)
            page.keyboard.press("Escape")

            print("Save, then see it under Saved & scheduled...")
            menu(page, msg, "Save for later")
            page.wait_for_timeout(500)
            print("Reminder...")
            menu(page, msg, "Remind me in 1 hour")
            page.wait_for_timeout(800)
            with sqlite3.connect(DB) as db:
                db.execute("UPDATE saved SET remind_at = 1 WHERE remind_at > 0 AND username = ?", (USER,))
            expect(page.locator(".relack-note").get_by_text("keep this " + STAMP)).to_be_visible(timeout=15000)

            print("Forward...")
            menu(page, msg, "Forward")
            page.get_by_role("button", name="Forward to " + OTHER).click()
            expect(page.get_by_text("Forwarded.")).to_be_visible(timeout=10000)

            print("Copy link and open it...")
            menu(page, msg, "Copy link")
            page.wait_for_timeout(300)
            link = page.evaluate("window.__relackRuntime.copied")
            assert "/?m=" in link, link
            page.locator("aside").get_by_role("heading", name=OTHER, exact=True).click()
            expect(page.locator("#relack-messages .relack-md blockquote").filter(has_text="keep this " + STAMP)).to_be_visible(timeout=15000)
            page.goto(link, wait_until="domcontentloaded")
            expect(page.locator("#relack-messages .relack-highlight")).to_contain_text("keep this " + STAMP, timeout=30000)

            print("Schedule from the clock button, cancel; /later 1m goes out by itself...")
            box = page.get_by_role("textbox", name="Message", exact=True)
            box.click()
            page.keyboard.type("cancel me " + STAMP)
            page.get_by_role("button", name="Send later").click()
            page.get_by_role("button", name="In 1 hour").click()
            expect(box).to_have_value("", timeout=5000)
            box.click()
            page.keyboard.type("/later 1m on time " + STAMP)
            page.keyboard.press("Enter")
            expect(page.get_by_text("Scheduled. It goes out in 1m.")).to_be_visible(timeout=10000)
            page.get_by_role("button", name="Saved & scheduled").click()
            expect(page.locator("#relack-saved").get_by_text("keep this " + STAMP)).to_be_visible(timeout=10000)
            scheduled = page.locator("#relack-scheduled")
            expect(scheduled.get_by_text("cancel me " + STAMP)).to_be_visible(timeout=10000)
            shots["later"] = page.screenshot()
            scheduled.get_by_role("button", name="Cancel scheduled message").last.click()  # latest due
            expect(scheduled.get_by_text("cancel me " + STAMP)).to_have_count(0, timeout=10000)
            page.locator("aside").get_by_role("heading", name=ROOM, exact=True).click()
            expect(page.locator("#relack-messages").get_by_text("on time " + STAMP)).to_be_visible(timeout=100000)
            print("All tests passed!")
        except Exception as e:
            print(f"TEST FAILED: {e}")
            shots["failure"] = page.screenshot()
            sys.exit(1)
        finally:
            browser.close()
            for name, png in shots.items():
                with open(os.path.join(output_dir, f"{name}.png"), "wb") as f:
                    f.write(png)


if __name__ == "__main__":
    run()
