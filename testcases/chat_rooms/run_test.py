"""E2E: managing rooms.

Rename and describe a room, leave it and rejoin from Browse rooms, mute it
(no unread count), archive it (read-only, restored from Browse rooms), post
through a webhook, and use slash commands.

    poetry run ./run_test_suite.sh chat_rooms
"""

import json
import os
import sys
import time
import urllib.request

from dotenv import load_dotenv
from playwright.sync_api import expect, sync_playwright

load_dotenv()

BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000").rstrip("/")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
STAMP = str(int(time.time()))[-5:]
ROOM = "Team " + STAMP
RENAMED = "Crew " + STAMP


def login(ctx, name):
    page = ctx.new_page()
    page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
    page.get_by_placeholder("CoolPanda99").fill(name)
    page.get_by_role("button", name="Continue as Guest").click()
    page.get_by_role("button", name="Browse rooms").wait_for(timeout=30000)
    return page


def side(page, title):
    return page.locator("aside").get_by_role("heading", name=title, exact=True)


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
        try:
            owner = login(a_ctx, "Owner" + STAMP)
            member = login(b_ctx, "Member" + STAMP)
            owner.get_by_role("button", name="New room").click()
            dialog = owner.get_by_role("dialog", name="Create New Room")
            dialog.get_by_placeholder("e.g. Design Team").fill(ROOM)
            dialog.get_by_role("button", name="Create Room").click()
            side(owner, ROOM).click()
            owner.get_by_role("textbox", name="Message", exact=True).wait_for(timeout=15000)

            print("Rename...")
            owner.get_by_role("button", name="Room settings").click()
            owner.get_by_label("Room title").fill(RENAMED)
            owner.get_by_label("Room description").fill("Renamed room")
            owner.wait_for_timeout(500)
            owner.get_by_role("button", name="Save room").click()
            expect(side(member, RENAMED)).to_be_visible(timeout=15000)

            print("Leave and rejoin...")
            member.get_by_role("button", name="Browse rooms").click()
            member.get_by_role("button", name="Leave " + RENAMED).click()
            expect(side(member, RENAMED)).to_have_count(0, timeout=10000)
            member.get_by_role("button", name="Join " + RENAMED).click()
            expect(side(member, RENAMED)).to_be_visible(timeout=10000)

            print("Webhook...")
            owner.get_by_role("button", name="Room settings").click()
            owner.get_by_label("Webhook name").fill("CI")
            owner.wait_for_timeout(400)
            owner.get_by_role("button", name="Add webhook").click()
            code = owner.locator("code").filter(has_text="/api/relack/hooks/")
            expect(code).to_have_count(1, timeout=10000)
            path = code.inner_text()
            owner.keyboard.press("Escape")
            req = urllib.request.Request(
                BACKEND_URL + path, data=json.dumps({"text": "build passed " + STAMP}).encode(),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
            send(owner, "right after the bot " + STAMP)  # must not push the bot's post out
            expect(owner.get_by_text("right after the bot " + STAMP)).to_be_visible(timeout=15000)
            expect(owner.get_by_text("build passed " + STAMP)).to_be_visible(timeout=15000)
            expect(owner.get_by_text("BOT", exact=True)).to_be_visible()
            shots["webhook"] = owner.screenshot()

            print("Mute: no unread count...")
            member.get_by_role("button", name="Browse rooms").click()
            member.get_by_role("button", name="Open " + RENAMED).click()
            member.get_by_role("textbox", name="Message", exact=True).wait_for(timeout=15000)
            send(member, "/mute")
            expect(member.get_by_text("Done.").first).to_be_visible(timeout=10000)
            member.locator("aside").get_by_role("heading", name="General", exact=True).click()
            send(owner, "while muted " + STAMP)
            member.wait_for_timeout(4000)
            card = side(member, RENAMED).locator("xpath=ancestor::button")
            expect(card.locator("svg.lucide-bell-off")).to_be_visible(timeout=10000)
            expect(card.get_by_title("Unread messages")).to_have_count(0)

            print("Slash commands...")
            send(owner, "/shrug ok")
            expect(owner.locator(".relack-md").filter(has_text="ツ")).to_have_count(1, timeout=10000)
            send(owner, "/usr/bin is a path")
            expect(owner.get_by_text("/usr/bin is a path")).to_be_visible(timeout=10000)

            print("Archive and restore...")
            owner.get_by_role("button", name="Room settings").click()
            owner.get_by_role("button", name="Archive room").click()
            expect(side(member, RENAMED)).to_have_count(0, timeout=15000)
            owner.get_by_role("button", name="Browse rooms").click()
            owner.get_by_role("button", name="Open " + RENAMED).click()
            expect(owner.get_by_text("This room is archived.")).to_be_visible(timeout=15000)
            expect(owner.get_by_role("textbox", name="Message", exact=True)).to_have_count(0)
            owner.get_by_role("button", name="Browse rooms").click()
            owner.get_by_role("button", name="Restore").first.click()
            expect(side(owner, RENAMED)).to_be_visible(timeout=10000)
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
