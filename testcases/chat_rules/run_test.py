"""E2E: the admin's switches really apply; audit log and retention setting.

Turns on guest approval and turns off room creation and mentions for guests:
a new guest waits on the approval screen until the admin approves them, then
has no New room button and can't mention. Everything is reset at the end.

    poetry run ./run_test_suite.sh chat_rules
"""

import os
import sys
import time

from dotenv import load_dotenv
from playwright.sync_api import expect, sync_playwright

load_dotenv()

BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000").rstrip("/")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
GUEST = "Waiter" + str(int(time.time()))[-5:]


def admin_login(page):
    page.goto(f"{BASE_URL}/admin-dashboard", timeout=60000, wait_until="domcontentloaded")
    page.get_by_placeholder("Enter Admin Passcode").fill(os.environ["ADMIN_PASSCODE"])
    page.get_by_role("button", name="Login").click()
    page.get_by_role("tab", name="Settings").wait_for(timeout=30000)


def settings(page):
    page.get_by_role("tab", name="Settings").click()
    page.get_by_role("button", name="Permissions").click()


def run():
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    shots: dict[str, bytes] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        admin_ctx = browser.new_context(viewport={"width": 1400, "height": 1000})
        guest_ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        admin = admin_ctx.new_page()
        try:
            admin_login(admin)
            settings(admin)
            print("Tighten guest permissions...")
            toggles = admin.locator("#permissions").get_by_role("switch")
            if toggles.count() == 0:
                toggles = admin.locator("#permissions").get_by_role("checkbox")
            assert toggles.count() == 8, toggles.count()
            for i in (1, 2, 3):  # guest approval, guest create room, guest mention
                toggles.nth(i).click()
                admin.wait_for_timeout(400)

            print("A new guest waits for approval...")
            page = guest_ctx.new_page()
            page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
            page.get_by_placeholder("CoolPanda99").fill(GUEST)
            page.get_by_role("button", name="Continue as Guest").click()
            expect(page.get_by_text("Waiting for approval")).to_be_visible(timeout=30000)
            expect(page.locator("aside")).to_have_count(0)
            shots["pending"] = page.screenshot()

            print("Admin approves; the page opens by itself...")
            admin.get_by_role("tab", name="Users").click()
            row = admin.get_by_role("row").filter(has_text=GUEST)
            row.get_by_role("button", name="Approve").click()
            page.locator("aside").get_by_role("heading", name="General", exact=True).wait_for(timeout=20000)
            expect(page.get_by_role("button", name="New room")).to_have_count(0)

            print("No mentions for guests now...")
            page.locator("aside").get_by_role("heading", name="General", exact=True).click()
            box = page.get_by_role("textbox", name="Message", exact=True)
            box.click()
            page.keyboard.type("hi @")
            page.wait_for_timeout(600)
            expect(page.get_by_role("listbox", name="Mention someone")).to_have_count(0)

            print("Audit log records the approval; retention saves...")
            admin.get_by_role("tab", name="Audit log").click()
            expect(admin.get_by_role("row").filter(has_text="user.approve").filter(has_text=GUEST).first).to_be_visible(timeout=10000)
            settings(admin)
            admin.get_by_label("Retention days").fill("0")
            admin.get_by_role("button", name="Save retention").click()
            expect(admin.get_by_text("Messages are kept forever.")).to_be_visible(timeout=10000)

            print("Revoking shuts the guest out at once...")
            admin.get_by_role("tab", name="Users").click()
            admin.get_by_role("row").filter(has_text=GUEST).get_by_role("button", name="Revoke").click()
            expect(page.get_by_text("Waiting for approval")).to_be_visible(timeout=20000)
            settings(admin)

            print("Reset...")
            admin.get_by_role("button", name="Reset").click()
            expect(admin.get_by_text("Permissions reset to defaults.")).to_be_visible(timeout=10000)
            print("All tests passed!")
        except Exception as e:
            print(f"TEST FAILED: {e}")
            for ctx in (admin_ctx, guest_ctx):
                for i, pg in enumerate(ctx.pages):
                    shots[f"failure_{id(ctx)}_{i}"] = pg.screenshot()
            try:
                settings(admin)
                admin.get_by_role("button", name="Reset").click(timeout=5000)
                admin.wait_for_timeout(1000)
            except Exception:
                print("Reset the permissions by hand!")
            sys.exit(1)
        finally:
            browser.close()
            for name, png in shots.items():
                with open(os.path.join(output_dir, f"{name}.png"), "wb") as f:
                    f.write(png)


if __name__ == "__main__":
    run()
