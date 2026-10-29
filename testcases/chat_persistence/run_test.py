"""E2E: nothing is lost when the server restarts and Reflex's state files are gone.

Rooms, messages, threads, reactions and logins live in relack.db. The test
writes some, closes the browser, deletes `.states/` (as Reflex does for files
untouched for an hour) and restarts the dev backend by touching a code file.
Then the same browser profile is still logged in and sees everything again.
The lobby's activity counter starting over shows the restart really happened.

Needs the dev server (`reflex run`, hot reload) of this checkout:

    poetry run ./run_test_suite.sh chat_persistence
"""

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import expect, sync_playwright

load_dotenv()

BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000").rstrip("/")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
ROOT = Path(__file__).resolve().parents[2]
STAMP = str(int(time.time()))[-5:]
USER = "Keeper" + STAMP
ROOM = "Keep " + STAMP


def wipe_states():
    shutil.rmtree(ROOT / ".states", ignore_errors=True)
    (ROOT / ".states").mkdir(exist_ok=True)


def run():
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    shots: dict[str, bytes] = {}
    storage = os.path.join(tempfile.mkdtemp(), "state.json")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        try:
            print("Writing a room, a message, a reaction and a thread reply...")
            page = context.new_page()
            page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
            page.get_by_placeholder("CoolPanda99").fill(USER)
            page.get_by_role("button", name="Continue as Guest").click()
            page.get_by_role("button", name="New room").click()
            dialog = page.get_by_role("dialog", name="Create New Room")
            dialog.get_by_placeholder("e.g. Design Team").fill(ROOM)
            dialog.get_by_role("button", name="Create Room").click()
            page.locator("aside").get_by_role("heading", name=ROOM, exact=True).click()
            box = page.get_by_role("textbox", name="Message", exact=True)
            box.click()
            page.keyboard.type("remember me " + STAMP)
            page.keyboard.press("Enter")
            msg = page.locator("#relack-messages [id^=msg-]").filter(has_text="remember me " + STAMP)
            expect(msg).to_have_count(1, timeout=10000)
            msg.hover()
            msg.get_by_role("button", name="React with ✅").click()
            expect(msg.get_by_role("button", name="✅ 1")).to_be_visible(timeout=10000)
            msg.hover()
            msg.get_by_role("button", name="Reply in thread").click()
            page.get_by_role("textbox", name="Reply", exact=True).click()
            page.keyboard.type("kept reply")
            page.keyboard.press("Enter")
            expect(msg.get_by_text("1 reply")).to_be_visible(timeout=10000)
            activity = int(page.locator("#relack-activity").text_content())
            assert activity >= 2, activity
            context.storage_state(path=storage)
            context.close()

            print("Deleting .states and restarting the backend...")
            wipe_states()
            (ROOT / "relack" / "__init__.py").touch()
            time.sleep(12)
            wipe_states()  # anything the old process wrote on its way out

            context = browser.new_context(viewport={"width": 1400, "height": 900}, storage_state=storage)
            page = context.new_page()
            page.goto(BASE_URL, timeout=90000, wait_until="domcontentloaded")
            card = page.locator("aside").get_by_role("heading", name=ROOM, exact=True)
            card.wait_for(timeout=90000)
            expect(page.get_by_placeholder("CoolPanda99")).to_have_count(0)
            expect(page.locator("#relack-activity")).to_have_text("0", timeout=10000)
            print("Still logged in after a restart with fresh state files...")
            card.click()
            msg = page.locator("#relack-messages [id^=msg-]").filter(has_text="remember me " + STAMP)
            expect(msg).to_have_count(1, timeout=15000)
            expect(msg.get_by_role("button", name="✅ 1")).to_be_visible()
            expect(msg.get_by_text("1 reply")).to_be_visible()
            msg.get_by_text("1 reply").click()
            expect(page.locator("#relack-thread-messages").get_by_text("kept reply")).to_be_visible(timeout=10000)
            shots["after_restart"] = page.screenshot()
            print("All tests passed!")
        except Exception as e:
            print(f"TEST FAILED: {e}")
            for i, pg in enumerate(context.pages):
                shots[f"failure_{i}"] = pg.screenshot()
            sys.exit(1)
        finally:
            browser.close()
            for name, png in shots.items():
                with open(os.path.join(output_dir, f"{name}.png"), "wb") as f:
                    f.write(png)


if __name__ == "__main__":
    run()
