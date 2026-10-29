"""E2E: mentions, unread counts and notifications.

Bob keeps another room open in a background tab (no focus); desktop
notifications are captured by a stub of the browser's Notification API.

1. Alice types "@" + part of Bob's name: the autocomplete offers him, Enter
   picks him; the message shows a mention link.
2. Bob gets a mention badge on that room, an unread count in the tab title and
   a desktop notification (sound too); opening the room clears the badge.
3. Bob's reply in Alice's thread notifies Alice; a direct message gives Bob a
   red unread count and a notification titled with the sender's name.
4. Clicking a mention opens that person's profile dialog; the bell's popover
   turns the sound off for this browser.

    poetry run ./run_test_suite.sh chat_notify
"""

import os
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
# Where the person being notified is looking meanwhile.
ELSEWHERE = "Elsewhere " + STAMP

NOTIFY_STUB = """
window.__notes = [];
window.Notification = function (title, opts) {
  window.__notes.push({title: title, body: opts && opts.body});
  this.close = function () {};
};
window.Notification.permission = 'granted';
window.Notification.requestPermission = function () { return Promise.resolve('granted'); };
"""


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


def create_room(page, name):
    page.get_by_role("button", name="New room").click()
    dialog = page.get_by_role("dialog", name="Create New Room")
    dialog.get_by_placeholder("e.g. Design Team").fill(name)
    dialog.get_by_role("button", name="Create Room").click()
    page.locator("aside").get_by_role("heading", name=name, exact=True).wait_for(timeout=15000)


def room_card(page, title):
    return page.locator("aside").get_by_role("heading", name=title, exact=True).locator("xpath=ancestor::button")


def in_background(page, background: bool):
    page.evaluate(f"document.hasFocus = () => {'false' if background else 'true'}")


def send(page, text):
    page.get_by_role("textbox", name="Message", exact=True).click()
    page.keyboard.type(text)
    page.keyboard.press("Enter")


def run():
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    shots: dict[str, bytes] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        a_ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        b_ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        a_ctx.add_init_script(NOTIFY_STUB)
        b_ctx.add_init_script(NOTIFY_STUB)
        try:
            alice = login_guest(a_ctx, ALICE)
            bob = login_guest(b_ctx, BOB)
            create_room(alice, ELSEWHERE)
            open_room(bob, ELSEWHERE)
            in_background(bob, True)
            open_room(alice, "General")

            print("Mention autocomplete...")
            alice.get_by_role("textbox", name="Message", exact=True).click()
            alice.keyboard.type("Hi @" + BOB[:-1])
            options = alice.get_by_role("listbox", name="Mention someone")
            expect(options.get_by_role("option").filter(has_text=BOB)).to_have_count(1, timeout=5000)
            shots["autocomplete"] = alice.screenshot()
            options.get_by_role("option").filter(has_text=BOB).click()
            box = alice.get_by_role("textbox", name="Message", exact=True)
            assert box.input_value() == f"Hi @{BOB} ", box.input_value()
            alice.keyboard.type("please look " + STAMP)
            alice.keyboard.press("Enter")
            link = alice.locator('.relack-md a[href="#mention-' + BOB + '"]')
            expect(link).to_have_text("@" + BOB, timeout=10000)

            print("Bob: mention badge, title count, notification...")
            general = room_card(bob, "General")
            expect(general.get_by_title("Mentions of you")).to_have_text("@1", timeout=15000)
            expect(bob).to_have_title("(1) Relack - Reflex Real-Time Chat", timeout=10000)
            bob.wait_for_function("window.__notes.length > 0", timeout=10000)
            notes = bob.evaluate("window.__notes")
            assert notes[0]["title"] == f"{ALICE} in #General", notes
            assert "please look " + STAMP in notes[0]["body"], notes
            assert bob.evaluate("window.__relackRuntime.dings || 0") >= 1
            shots["mention_badge"] = bob.screenshot()

            print("Bob opens the room: badge and title count go away...")
            in_background(bob, False)
            open_room(bob, "General")
            expect(general.get_by_title("Mentions of you")).to_have_count(0, timeout=10000)
            expect(bob).to_have_title("Relack - Reflex Real-Time Chat", timeout=10000)

            print("A reply in Alice's thread notifies her...")
            in_background(alice, True)
            open_room(alice, ELSEWHERE)
            msg = bob.locator("#relack-messages [id^=msg-]").filter(has_text="please look " + STAMP).last
            msg.hover()
            msg.get_by_role("button", name="Reply in thread").click()
            bob.get_by_role("textbox", name="Reply", exact=True).click()
            bob.keyboard.type("on it " + STAMP)
            bob.keyboard.press("Enter")
            alice.wait_for_function("window.__notes.length > 0", timeout=15000)
            notes = alice.evaluate("window.__notes")
            assert notes[-1]["title"] == f"{BOB} replied in #General", notes
            bob.get_by_role("button", name="Close thread").click()

            print("Direct message: red count and a notification from the sender...")
            open_room(bob, ELSEWHERE)
            in_background(bob, True)
            bob.evaluate("window.__notes = []")
            in_background(alice, False)
            alice.get_by_label("Search", exact=True).fill(BOB)
            alice.get_by_label("Search", exact=True).press("Enter")
            alice.locator("section[aria-label=People]").get_by_role("button", name="Message").first.click()
            alice.get_by_role("textbox", name="Message", exact=True).wait_for(timeout=15000)
            send(alice, "psst " + STAMP)
            dm = room_card(bob, ALICE)
            expect(dm.get_by_title("Unread messages")).to_have_text("1", timeout=15000)
            bob.wait_for_function("window.__notes.length > 0", timeout=10000)
            notes = bob.evaluate("window.__notes")
            assert notes[0]["title"] == ALICE and "psst " + STAMP in notes[0]["body"], notes

            print("Clicking a mention opens the profile dialog...")
            in_background(bob, False)
            open_room(bob, "General")
            bob.locator(f'.relack-md a[href="#mention-{BOB}"]').last.click()
            frame = bob.frame_locator("#ddns-intent-frame")
            expect(frame.get_by_text(BOB).first).to_be_visible(timeout=30000)
            shots["mention_profile"] = bob.screenshot()
            bob.keyboard.press("Escape")

            print("Sound off from the bell...")
            bob.get_by_role("button", name="Notification settings").click()
            popover = bob.get_by_role("dialog").filter(has_text="Desktop notifications")
            popover.get_by_role("button", name="Turn off").last.click()
            expect(bob.locator("[data-relack-me]")).to_have_attribute("data-relack-sound", "off", timeout=5000)

            print("All tests passed!")
        except Exception as e:
            print(f"TEST FAILED: {e}")
            for ctx in (a_ctx, b_ctx):
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
