"""E2E: status, do not disturb, typing, language, dark mode, narrow screens, group message.

    poetry run ./run_test_suite.sh chat_presence
"""

import json
import os
import sys
import time

from dotenv import load_dotenv
from playwright.sync_api import expect, sync_playwright

load_dotenv()

BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000").rstrip("/")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
STAMP = str(int(time.time()))[-5:]
ALICE, BOB = "Alice" + STAMP, "Bob" + STAMP
NOTIFY_STUB = """
window.__notes = [];
window.Notification = function (t, o) { window.__notes.push(t); this.close = function () {}; };
window.Notification.permission = 'granted';
window.Notification.requestPermission = function () { return Promise.resolve('granted'); };
"""


def login(ctx, name):
    page = ctx.new_page()
    page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
    page.get_by_placeholder("CoolPanda99").fill(name)
    page.get_by_role("button", name="Continue as Guest").click()
    page.get_by_role("button", name="Browse rooms").wait_for(timeout=30000)
    return page


def general(page):
    page.locator("aside").get_by_role("heading", name="General", exact=True).click()
    page.get_by_role("textbox", name="Message", exact=True).wait_for(timeout=15000)


def run():
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    shots: dict[str, bytes] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        a_ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        b_ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        b_ctx.add_init_script(NOTIFY_STUB)
        phone = browser.new_context(viewport={"width": 390, "height": 800}, has_touch=True, is_mobile=True)
        try:
            alice = login(a_ctx, ALICE)
            bob = login(b_ctx, BOB)
            general(alice)
            general(bob)

            print("Typing indicator...")
            bob.get_by_role("textbox", name="Message", exact=True).click()
            bob.keyboard.type("hel")
            expect(alice.locator("#relack-typing")).to_contain_text(BOB, timeout=8000)
            bob.keyboard.press("Enter")
            expect(alice.locator("#relack-typing")).not_to_contain_text(BOB, timeout=12000)

            print("Status shows beside messages...")
            box = bob.get_by_role("textbox", name="Message", exact=True)
            box.click()
            bob.keyboard.type("/status 🌴 On holiday")
            bob.keyboard.press("Enter")
            expect(bob.get_by_role("button", name="Set a status")).to_contain_text("On holiday", timeout=10000)
            box.click()
            bob.keyboard.type("after status " + STAMP)
            bob.keyboard.press("Enter")
            msg = alice.locator("#relack-messages [id^=msg-]").filter(has_text="after status " + STAMP)
            expect(msg.get_by_text("🌴")).to_be_visible(timeout=10000)

            print("Do not disturb holds notifications back...")
            box.click()
            bob.keyboard.type("/dnd 1h")
            bob.keyboard.press("Enter")
            expect(bob.get_by_text("Notifications paused.")).to_be_visible(timeout=10000)
            bob.evaluate("document.hasFocus = () => false")
            alice.get_by_role("textbox", name="Message", exact=True).click()
            alice.keyboard.type(f"ping @{BOB} ")
            alice.keyboard.press("Escape")
            alice.keyboard.press("Enter")
            bob.wait_for_timeout(4000)
            assert bob.evaluate("window.__notes.length") == 0, bob.evaluate("window.__notes")
            bob.evaluate("document.hasFocus = () => true")

            print("Chinese interface...")
            alice.get_by_role("button", name="Switch language").click()
            expect(alice.get_by_role("button", name="Browse rooms")).to_have_text("瀏覽房間", timeout=10000)
            shots["chinese"] = alice.screenshot()
            alice.get_by_role("button", name="Switch language").click()
            expect(alice.get_by_role("button", name="Browse rooms")).to_have_text("Browse rooms", timeout=10000)

            print("Dark mode...")
            alice.get_by_role("button", name="Dark mode").click()
            alice.wait_for_timeout(700)  # the sidebar's colour transition
            bg = alice.evaluate("getComputedStyle(document.querySelector('aside')).backgroundColor")
            assert bg == "rgb(17, 24, 39)", bg
            shots["dark"] = alice.screenshot()
            alice.get_by_role("button", name="Dark mode").click()

            print("Narrow screen: the sidebar closes after picking a room...")
            mobile = login(phone, "Phone" + STAMP)
            mobile.wait_for_timeout(2000)
            mobile.locator("aside").get_by_role("heading", name="General", exact=True).click()
            box = mobile.get_by_role("textbox", name="Message", exact=True)
            box.wait_for(timeout=15000)
            mobile.wait_for_timeout(800)
            expect(mobile.locator("aside.relack-sidebar-closed")).to_have_count(1, timeout=10000)
            assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "sideways scroll"
            shots["phone"] = mobile.screenshot()
            manifest = mobile.request.get(f"{BASE_URL}/manifest.webmanifest")
            assert manifest.ok and json.loads(manifest.text())["name"] == "Relack", manifest.status
            print("All tests passed!")
        except Exception as e:
            print(f"TEST FAILED: {e}")
            for ctx in (a_ctx, b_ctx, phone):
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
