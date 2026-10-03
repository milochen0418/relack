"""E2E: private rooms whose members are picked through the `people.pick` intent.

Verified (Google) members cannot log in from a test, so they are seeded
through the admin JSON import. Then:

1. Owner (guest) opens Create Room, ticks "Private room", adds members one by
   one through the `people.pick` dialog, removes one, and creates the room.
2. The room shows a lock in the sidebar; inside it the "Private · N members"
   popover lists who can see it.
3. Another guest does not see the private room in the sidebar.

The server must open relack intents on itself:

    DDNS_INTENT_URL_RELACK=http://localhost:3000 poetry run ./run_test_suite.sh private_room
"""

import json
import os
import sys

from dotenv import load_dotenv
from playwright.sync_api import expect, sync_playwright

load_dotenv()

BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000").rstrip("/")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
OWNER = "RoomOwner"
OUTSIDER = "Outsider"
ROOM = "Secret Lab"

MEMBERS = [
    {"username": "alice@example.com", "email": "alice@example.com", "nickname": "Alice Wonder"},
    {"username": "bob@example.com", "email": "bob@example.com", "nickname": "Bob Builder"},
]
SEED = {
    "rooms": [{"name": "General", "description": "The main hangout spot"}],
    "messages_by_room": {},
    "profiles": [
        {**m, "is_guest": False, "avatar_seed": m["email"], "created_at": "2026-01-01T00:00:00"}
        for m in MEMBERS
    ],
}


def seed_members(page):
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
    page.get_by_role("tab", name="Users").click()
    page.get_by_role("cell", name=MEMBERS[0]["email"]).first.wait_for(timeout=15000)


def login_guest(context, name):
    page = context.new_page()
    page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
    page.get_by_placeholder("CoolPanda99").fill(name)
    page.get_by_role("button", name="Continue as Guest").click()
    page.wait_for_selector(f"text={name}", timeout=30000)
    page.get_by_role("heading", name="General").wait_for(timeout=30000)
    return page


def pick(page, nickname):
    page.get_by_role("button", name="Add people").click()
    frame = page.frame_locator("#ddns-intent-frame")
    frame.get_by_role("heading", name="Pick a member").wait_for(timeout=30000)
    frame.get_by_role("button", name=nickname).click()
    expect(page.locator("#ddns-intent-frame")).to_have_count(0, timeout=15000)


def run():
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)

    # Written at the end: a new file in the project tree hot-reloads the dev
    # backend and would drop the browser's session mid-test.
    shots: dict[str, bytes] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        admin_ctx = browser.new_context()
        owner_ctx = browser.new_context()
        outsider_ctx = browser.new_context()
        try:
            print("Seeding verified members via admin import...")
            seed_members(admin_ctx.new_page())

            print("Owner opens Create Room and makes it private...")
            page = login_guest(owner_ctx, OWNER)
            page.locator("aside button:has(svg.lucide-plus)").click()
            dialog = page.get_by_role("dialog", name="Create New Room")
            dialog.get_by_placeholder("e.g. Design Team").fill(ROOM)
            dialog.get_by_placeholder("What is this room for?").fill("Top secret")
            expect(dialog.get_by_role("button", name="Add people")).to_have_count(0)
            dialog.get_by_text("Private room").click()

            print("Adding members through people.pick...")
            pick(page, "Alice Wonder")
            expect(dialog.get_by_text("Alice Wonder")).to_be_visible()
            pick(page, "Bob Builder")
            pick(page, "Alice Wonder")  # duplicates are ignored
            expect(dialog.get_by_text("Alice Wonder")).to_have_count(1)
            shots["create_private_room"] = page.screenshot()
            dialog.get_by_role("button", name="Remove bob@example.com").click()
            expect(dialog.get_by_text("Bob Builder")).to_have_count(0)
            dialog.get_by_role("button", name="Create Room").click()
            expect(dialog).to_have_count(0)

            print("Owner joins the private room and checks its members...")
            card = page.get_by_role("heading", name=ROOM)
            card.wait_for(timeout=15000)
            card.click()
            badge = page.get_by_role("button", name="Private · 2 members")
            badge.wait_for(timeout=15000)
            badge.click()
            popover = page.get_by_role("dialog").filter(has_text="Who can see this room")
            expect(popover.get_by_text(OWNER)).to_be_visible()
            expect(popover.get_by_text("Owner", exact=True)).to_be_visible()
            expect(popover.get_by_text("Alice Wonder")).to_be_visible()
            expect(popover.get_by_text("Bob Builder")).to_have_count(0)
            shots["private_room_members"] = page.screenshot()

            print("Outsider cannot see the private room...")
            other = login_guest(outsider_ctx, OUTSIDER)
            other.wait_for_timeout(2000)
            expect(other.get_by_role("heading", name=ROOM)).to_have_count(0)
            shots["outsider_sidebar"] = other.screenshot()

            print("All tests passed!")
        except Exception as e:
            print(f"TEST FAILED: {e}")
            for ctx in (admin_ctx, owner_ctx, outsider_ctx):
                for i, pg in enumerate(ctx.pages):
                    pg.screenshot(path=os.path.join(output_dir, f"failure_{id(ctx)}_{i}.png"))
            sys.exit(1)
        finally:
            browser.close()
            for name, png in shots.items():
                with open(os.path.join(output_dir, f"{name}.png"), "wb") as f:
                    f.write(png)


if __name__ == "__main__":
    run()
