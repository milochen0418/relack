"""E2E: the People view and relack's `people.pick` DDNS Intent.

Verified (Google) members cannot log in from a test, so they are seeded
through the admin JSON import. Then:

1. In-app: sidebar People lists verified members only; clicking one opens its
   profile through the `profile.view` intent dialog.
2. In-app chain: "Pick member" opens `people.pick` in the dialog; picking a
   member closes it and opens that member's `profile.view` intent.
3. External caller (fake host on :3999): picking a member posts a `result`
   message carrying the member.

The server must open relack intents on itself:

    DDNS_INTENT_URL_RELACK=http://localhost:3000 poetry run ./run_test_suite.sh people_intent
"""

import html
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from dotenv import load_dotenv
from playwright.sync_api import expect, sync_playwright

load_dotenv()

BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000").rstrip("/")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
HOST_ORIGIN = "http://localhost:3999"
CALL_ID = "pick123"
GUEST = "PeopleTester"

MEMBERS = [
    {"username": "alice@example.com", "email": "alice@example.com", "nickname": "Alice Wonder"},
    {"username": "bob@example.com", "email": "bob@example.com", "nickname": "Bob Builder"},
]
SEED = {
    "rooms": [],
    "messages_by_room": {},
    "profiles": [
        {**m, "is_guest": False, "avatar_seed": m["email"], "created_at": "2026-01-01T00:00:00"}
        for m in MEMBERS
    ]
    + [{"username": "SomeGuest", "is_guest": True, "avatar_seed": "SomeGuest"}],
}

HOST_PAGE = """<!doctype html><html><body>
<iframe id="frame" src="%s" style="width:720px;height:480px;border:0"></iframe>
<script>
  window.msgs = [];
  window.addEventListener("message", (ev) => {
    if (ev.data && ev.data.type === "ddns-intent") window.msgs.push({origin: ev.origin, ...ev.data});
  });
</script></body></html>"""


class HostHandler(BaseHTTPRequestHandler):
    """Serves the fake caller page; ?src= is the iframe URL."""

    def do_GET(self):
        src = parse_qs(urlparse(self.path).query).get("src", [""])[0]
        body = (HOST_PAGE % html.escape(src, quote=True)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


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


def run():
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)

    # Written at the end: a new file in the project tree hot-reloads the dev
    # backend and would drop the browser's session mid-test.
    shots: dict[str, bytes] = {}

    server = ThreadingHTTPServer(("localhost", 3999), HostHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page = context.new_page()
        try:
            print("Seeding verified members via admin import...")
            seed_members(page)

            print("Logging in as guest...")
            page = context.new_page()
            page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
            page.get_by_placeholder("CoolPanda99").fill(GUEST)
            page.get_by_role("button", name="Continue as Guest").click()
            page.wait_for_selector(f"text={GUEST}", timeout=30000)

            print("Opening People from the sidebar...")
            page.get_by_role("button", name="People", exact=True).click()
            expect(page.get_by_role("heading", name="People")).to_be_visible(timeout=10000)
            for m in MEMBERS:
                expect(page.get_by_role("button", name=m["nickname"])).to_be_visible()
            expect(page.get_by_text("SomeGuest")).to_have_count(0)
            expect(page.get_by_role("button", name=GUEST)).to_have_count(0)
            page.get_by_placeholder("Search people...").fill("bob")
            expect(page.get_by_role("button", name="Alice Wonder")).to_have_count(0)
            page.get_by_placeholder("Search people...").fill("")
            shots["people_view"] = page.screenshot()

            print("Clicking a member opens its profile intent...")
            page.get_by_role("button", name="Alice Wonder").click()
            frame = page.frame_locator("#ddns-intent-frame")
            frame.get_by_role("heading", name="Alice Wonder").wait_for(timeout=30000)
            shots["member_profile_dialog"] = page.screenshot()
            page.get_by_role("button", name="Close").click()
            expect(page.locator("#ddns-intent-frame")).to_have_count(0)

            print("Pick member -> people.pick dialog -> profile.view dialog...")
            page.get_by_role("button", name="Pick member").click()
            frame = page.frame_locator("#ddns-intent-frame")
            frame.get_by_role("heading", name="Pick a member").wait_for(timeout=30000)
            expect(frame.get_by_role("button", name="Pick member")).to_have_count(0)
            shots["pick_dialog"] = page.screenshot()
            frame.get_by_role("button", name="Bob Builder").click()
            frame = page.frame_locator("#ddns-intent-frame")
            frame.get_by_role("heading", name="Bob Builder").wait_for(timeout=30000)
            frame.get_by_text("Approval").wait_for(timeout=10000)
            shots["picked_profile_dialog"] = page.screenshot()

            print("External caller receives the picked member as result...")
            host = context.new_page()
            src = f"{BASE_URL}/intent/people-pick?_intent_id={CALL_ID}&_intent_origin={HOST_ORIGIN}"
            host.goto(f"{HOST_ORIGIN}/?src={quote(src, safe='')}", wait_until="domcontentloaded")
            ext = host.frame_locator("#frame")
            ext.get_by_role("button", name="Alice Wonder").click(timeout=60000)
            host.wait_for_function("window.msgs.some(m => m.event === 'result')", timeout=15000)
            result = next(m for m in host.evaluate("window.msgs") if m["event"] == "result")
            print("Result:", json.dumps(result))
            assert result["id"] == CALL_ID
            assert result["data"]["user"] == "alice@example.com", result
            assert result["data"]["email"] == "alice@example.com", result

            print("All tests passed!")
        except Exception as e:
            print(f"TEST FAILED: {e}")
            for i, pg in enumerate(context.pages):
                pg.screenshot(path=os.path.join(output_dir, f"failure_{i}.png"))
            sys.exit(1)
        finally:
            browser.close()
            for name, png in shots.items():
                with open(os.path.join(output_dir, f"{name}.png"), "wb") as f:
                    f.write(png)
            server.shutdown()


if __name__ == "__main__":
    run()
