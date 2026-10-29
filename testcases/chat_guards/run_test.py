"""E2E: identities and rooms that must stay apart.

1. A guest can't take a member's name: nicknames with "@" (Google accounts are
   their email address) and "System" (owner of the default rooms) are refused.
2. Room names starting with "dm-" are kept for direct messages.
3. Rooms whose names differ only in case or spacing don't share messages: a
   private "Plans <n>" and a public "plans <n>" each see only their own.

    poetry run ./run_test_suite.sh chat_guards
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


def try_guest(context, name):
    page = context.new_page()
    page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
    page.get_by_placeholder("CoolPanda99").fill(name)
    page.get_by_role("button", name="Continue as Guest").click()
    return page


def create_room(page, name, private=False):
    page.get_by_role("button", name="New room").click()
    dialog = page.get_by_role("dialog", name="Create New Room")
    dialog.get_by_placeholder("e.g. Design Team").fill(name)
    if private:
        dialog.get_by_text("Private room").click()
    dialog.get_by_role("button", name="Create Room").click()


def run():
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    shots: dict[str, bytes] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        a_ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        b_ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        try:
            print("Guests can't use a member's name...")
            page = try_guest(a_ctx, f"boss{STAMP}@example.com")
            expect(page.get_by_text("Guest nicknames can't contain @.")).to_be_visible(timeout=15000)
            expect(page.get_by_role("button", name="Continue as Guest")).to_be_visible()
            page.get_by_placeholder("CoolPanda99").fill("System")
            page.get_by_role("button", name="Continue as Guest").click()
            expect(page.get_by_text("That name is taken. Please choose another nickname.")).to_be_visible(timeout=15000)
            page.close()

            alice = try_guest(a_ctx, "Alice" + STAMP)
            alice.get_by_role("button", name="New room").wait_for(timeout=30000)
            bob = try_guest(b_ctx, "Bob" + STAMP)
            bob.get_by_role("button", name="New room").wait_for(timeout=30000)

            print("dm- names are kept for direct messages...")
            create_room(bob, "dm-" + STAMP)
            expect(bob.get_by_text("Room names can't start with dm-.")).to_be_visible(timeout=10000)
            bob.keyboard.press("Escape")
            bob.reload(wait_until="domcontentloaded")
            bob.get_by_role("button", name="New room").wait_for(timeout=30000)

            print("A private room and a public look-alike stay apart...")
            secret, lookalike = f"Plans {STAMP}", f"plans {STAMP}"
            create_room(alice, secret, private=True)
            alice.locator("aside").get_by_role("heading", name=secret, exact=True).click()
            create_room(bob, lookalike)
            bob.locator("aside").get_by_role("heading", name=lookalike, exact=True).click()
            bob.get_by_role("textbox", name="Message", exact=True).wait_for(timeout=15000)
            expect(bob.locator("aside").get_by_role("heading", name=secret, exact=True)).to_have_count(0)
            box = alice.get_by_role("textbox", name="Message", exact=True)
            box.click()
            alice.keyboard.type("top secret " + STAMP)
            alice.keyboard.press("Enter")
            expect(alice.get_by_text("top secret " + STAMP)).to_be_visible(timeout=10000)
            bob.wait_for_timeout(3000)
            expect(bob.get_by_text("top secret " + STAMP)).to_have_count(0)
            shots["lookalike_room"] = bob.screenshot()

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
