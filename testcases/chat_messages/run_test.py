"""E2E: writing and changing messages.

Two guests in the same room:

1. Multi-line message with Markdown (Shift+Enter, **bold**, `code`, a ``` block
   where Enter adds a line), the Bold toolbar button, and an IME guard: Enter
   while a Chinese composition is open does not send, and the composed text is
   not doubled.
2. Times are shown in the browser's time zone, with a "Today" divider.
3. Reactions (hover toolbar), a thread reply, editing ("(edited)") and
   deleting, each seen live by the other person.
4. History: a room seeded with 130 messages over three days shows the newest
   100 and "Load earlier messages" brings the rest (day dividers in between).

    poetry run ./run_test_suite.sh chat_messages
"""

import datetime
import json
import os
import re
import sys
import time

from dotenv import load_dotenv
from playwright.sync_api import expect, sync_playwright

load_dotenv()

BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000").rstrip("/")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
STAMP = str(int(time.time()))[-5:]
ALICE = "Alice" + STAMP
BOB = "Bob" + STAMP
HISTORY_ROOM = "History"
TZ = "Asia/Taipei"

NOW = time.time()
SEED = {
    "rooms": [
        {"name": "General", "description": "The main hangout spot"},
        {"name": HISTORY_ROOM, "description": "Seeded history"},
    ],
    "profiles": [],
    "messages_by_room": {
        HISTORY_ROOM: [
            {
                "id": f"seed-{i:03d}",
                "sender": "Archivist",
                "display_name": "Archivist",
                "content": f"old message {i:03d}",
                "created_at": NOW - 3 * 86400 + i * 1800,
            }
            for i in range(130)
        ]
    },
}


def seed(page):
    passcode = os.environ.get("ADMIN_PASSCODE")
    if not passcode:
        raise RuntimeError("ADMIN_PASSCODE not set (.env)")
    page.goto(f"{BASE_URL}/admin-dashboard", timeout=60000, wait_until="domcontentloaded")
    page.get_by_placeholder("Enter Admin Passcode").fill(passcode)
    page.get_by_role("button", name="Login").click()
    page.get_by_role("tab", name="Settings").click()
    page.get_by_role("button", name="Data Maintenance").click()
    page.get_by_placeholder("Paste exported JSON here").fill(json.dumps(SEED))
    page.wait_for_timeout(1000)  # let the textarea value reach the backend
    page.get_by_role("button", name="Import Data", exact=True).click()
    page.get_by_text("Import completed.").wait_for(timeout=15000)


def login_guest(context, name):
    page = context.new_page()
    page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
    page.get_by_placeholder("CoolPanda99").fill(name)
    page.get_by_role("button", name="Continue as Guest").click()
    page.locator("aside").get_by_role("heading", name="General", exact=True).wait_for(timeout=30000)
    return page


def open_room(page, room):
    page.locator("aside").get_by_role("heading", name=room, exact=True).click()
    page.get_by_role("textbox", name="Message", exact=True).wait_for(timeout=15000)


def message(page, text):
    """A message in the room's list (not its copy in the thread panel)."""
    return page.locator("#relack-messages [id^=msg-]").filter(has_text=text).last


def run():
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    # Written at the end: a new file in the project tree hot-reloads the dev backend.
    shots: dict[str, bytes] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        admin_ctx = browser.new_context()
        a_ctx = browser.new_context(viewport={"width": 1400, "height": 900}, timezone_id=TZ)
        b_ctx = browser.new_context(viewport={"width": 1400, "height": 900}, timezone_id=TZ)
        try:
            print("Seeding a room with 130 old messages...")
            seed(admin_ctx.new_page())

            alice = login_guest(a_ctx, ALICE)
            bob = login_guest(b_ctx, BOB)
            open_room(alice, "General")
            open_room(bob, "General")
            box = alice.get_by_role("textbox", name="Message", exact=True)

            print("Multi-line Markdown message...")
            box.click()
            alice.keyboard.type("Hello **world**")
            alice.keyboard.press("Shift+Enter")
            alice.keyboard.type("second line with `code` " + STAMP)
            alice.keyboard.press("Enter")
            first = message(bob, "second line with")
            expect(first.locator(".relack-md strong")).to_have_text("world", timeout=10000)
            expect(first.locator(".relack-md code")).to_have_text("code")
            expect(first.locator(".relack-md p")).to_contain_text("Hello world\nsecond line")
            expect(box).to_have_value("")

            print("Code block: Enter adds lines until the block is closed...")
            box.click()
            alice.keyboard.type("```")
            alice.keyboard.press("Enter")
            alice.keyboard.type("print('hi')")
            alice.keyboard.press("Enter")
            alice.keyboard.type("```")
            assert box.input_value() == "```\nprint('hi')\n```", box.input_value()
            alice.keyboard.press("Enter")
            expect(bob.locator(".relack-md pre").filter(has_text="print('hi')")).to_have_count(1, timeout=10000)

            print("Bold toolbar button wraps the selection...")
            box.click()
            alice.keyboard.type("make me strong")
            box.evaluate("t => t.setSelectionRange(8, 14)")
            alice.get_by_role("button", name="Bold").first.click()
            assert box.input_value() == "make me **strong**", box.input_value()
            alice.keyboard.press("Enter")
            expect(bob.locator(".relack-md strong").filter(has_text="strong")).to_have_count(1, timeout=10000)

            print("IME: Enter while composing does not send, text is not doubled...")
            box.click()
            cdp = a_ctx.new_cdp_session(alice)
            for step in ["ㄋ", "ㄋㄧ", "ㄋㄧˇ"]:
                cdp.send("Input.imeSetComposition", {"text": step, "selectionStart": len(step), "selectionEnd": len(step)})
                alice.wait_for_timeout(350)
            box.evaluate(
                "t => t.dispatchEvent(new KeyboardEvent('keydown', "
                "{key: 'Enter', keyCode: 229, isComposing: true, bubbles: true, cancelable: true}))"
            )
            cdp.send("Input.insertText", {"text": "你好" + STAMP})
            alice.wait_for_timeout(800)
            assert box.input_value() == "你好" + STAMP, box.input_value()
            alice.keyboard.press("Enter")
            expect(bob.locator(".relack-bubble").filter(has_text="你好" + STAMP)).to_have_count(1, timeout=10000)

            print("Local time and day divider...")
            expect(bob.locator("#relack-messages").get_by_text("Today", exact=True)).to_be_visible()
            shown = message(bob, "你好" + STAMP).locator("span[title]").first.inner_text()
            local_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
            assert re.fullmatch(r"\d\d:\d\d", shown), shown
            minutes = int(shown[:2]) * 60 + int(shown[3:])
            assert abs(minutes - (local_now.hour * 60 + local_now.minute)) <= 2, (shown, local_now)
            shots["formatting"] = bob.screenshot()

            print("Reaction from the hover toolbar...")
            target = message(bob, "second line with")
            target.hover()
            target.get_by_role("button", name="React with 👍").click()
            expect(message(alice, "second line with").get_by_role("button", name="👍 1")).to_be_visible(timeout=10000)
            target.get_by_role("button", name="👍 1").click()  # take it back
            expect(message(alice, "second line with").get_by_role("button", name="👍 1")).to_have_count(0, timeout=10000)

            print("Thread reply...")
            target.hover()
            target.get_by_role("button", name="Reply in thread").click()
            reply_box = bob.get_by_role("textbox", name="Reply", exact=True)
            reply_box.click()
            bob.keyboard.type("a reply in the thread")
            bob.keyboard.press("Enter")
            expect(bob.locator("#relack-thread-messages").get_by_text("a reply in the thread")).to_be_visible(timeout=10000)
            expect(message(alice, "second line with").get_by_text("1 reply")).to_be_visible(timeout=10000)
            message(alice, "second line with").get_by_text("1 reply").click()
            expect(alice.locator("#relack-thread-messages").get_by_text("a reply in the thread")).to_be_visible(timeout=10000)
            shots["thread"] = alice.screenshot()
            alice.get_by_role("button", name="Close thread").click()

            print("Edit...")
            mine = message(alice, "second line with")
            mine.hover()
            mine.get_by_role("button", name="Edit message").click()
            edit_box = alice.get_by_role("textbox", name="Edit message")
            expect(edit_box).to_have_value(re.compile(r"^Hello \*\*world\*\*\nsecond line"))
            edit_box.press("End")
            alice.keyboard.type(" (now edited)")
            alice.keyboard.press("Enter")
            edited = message(bob, "now edited")
            expect(edited.get_by_text("(edited)")).to_be_visible(timeout=10000)
            expect(edited.get_by_text("1 reply")).to_be_visible()

            print("Delete...")
            box.click()
            alice.keyboard.type("to be deleted " + STAMP)
            alice.keyboard.press("Enter")
            expect(bob.get_by_text("to be deleted " + STAMP)).to_be_visible(timeout=10000)
            doomed = message(alice, "to be deleted " + STAMP)
            doomed.hover()
            doomed.get_by_role("button", name="Delete message").click()
            alice.get_by_role("alertdialog").get_by_role("button", name="Delete").click()
            expect(alice.get_by_role("alertdialog")).to_have_count(0, timeout=10000)
            expect(bob.get_by_text("to be deleted " + STAMP)).to_have_count(0, timeout=10000)

            print("History: newest 100, then Load earlier messages...")
            open_room(bob, HISTORY_ROOM)
            expect(bob.get_by_text("old message 129")).to_be_visible(timeout=10000)
            expect(bob.locator("#relack-messages [id^=msg-]")).to_have_count(100)
            bob.get_by_role("button", name="Load earlier messages").click()
            expect(bob.locator("#relack-messages [id^=msg-]")).to_have_count(130, timeout=10000)
            expect(bob.get_by_text("This is the very beginning of")).to_be_visible()
            dividers = bob.locator("#relack-messages span.rounded-full.border").all_inner_texts()
            # Three days of messages: one divider per day.
            assert len(dividers) >= 3, dividers
            shots["history"] = bob.screenshot()

            print("All tests passed!")
        except Exception as e:
            print(f"TEST FAILED: {e}")
            for ctx in (admin_ctx, a_ctx, b_ctx):
                for i, pg in enumerate(ctx.pages):
                    shots[f"failure_{id(ctx)}_{i}"] = pg.screenshot()
            sys.exit(1)
        finally:
            browser.close()
            for name, png in shots.items():
                with open(os.path.join(output_dir, f"{name}.png"), "wb") as f:
                    f.write(png)


if __name__ == "__main__":
    run()
