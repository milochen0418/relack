"""E2E: relack's `profile.view` DDNS Intent embedded by another app.

A fake caller page is served at http://localhost:3999 by a local HTTP
server. It embeds relack's /intent/profile-view in an iframe the way
`reflex_ddns_auth.intent.intent_host()` does, and records the postMessages.
"""

import html
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000").rstrip("/")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
HOST_ORIGIN = "http://localhost:3999"
NICKNAME = "IntentTester"
CALL_ID = "e2e123"

HOST_PAGE = """<!doctype html><html><body>
<iframe id="frame" src="%s" style="width:720px;height:480px;border:0"></iframe>
<script>
  window.msgs = [];
  window.addEventListener("message", (ev) => {
    if (ev.data && ev.data.type === "ddns-intent") window.msgs.push({origin: ev.origin, ...ev.data});
  });
</script></body></html>"""


def intent_url(origin: str) -> str:
    return (
        f"{BASE_URL}/intent/profile-view?user={NICKNAME}"
        f"&_intent_id={CALL_ID}&_intent_origin={origin}"
    )


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


def open_host(page, iframe_src: str):
    from urllib.parse import quote

    page.goto(f"{HOST_ORIGIN}/?src={quote(iframe_src, safe='')}", wait_until="domcontentloaded")
    return page.frame_locator("#frame")


def messages(page) -> list[dict]:
    return page.evaluate("window.msgs")


def run():
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)

    server = ThreadingHTTPServer(("localhost", 3999), HostHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page = context.new_page()
        try:
            print("Logging in to relack as guest so the profile exists in the lobby...")
            page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
            page.get_by_placeholder("CoolPanda99").fill(NICKNAME)
            page.get_by_role("button", name="Continue as Guest").click()
            page.wait_for_selector(f"text={NICKNAME}", timeout=30000)

            print("Embedding the intent from a trusted caller...")
            host = context.new_page()
            frame = open_host(host, intent_url(HOST_ORIGIN))
            frame.get_by_text("Approval").wait_for(timeout=60000)
            frame.get_by_role("heading", name=NICKNAME).wait_for(timeout=10000)
            host.wait_for_function(
                "window.msgs.some(m => m.event === 'ready') && window.msgs.some(m => m.event === 'resize')",
                timeout=15000,
            )
            msgs = messages(host)
            print("Messages:", json.dumps(msgs))
            expected_origin = BASE_URL.split("/", 3)[0] + "//" + BASE_URL.split("/", 3)[2]
            for m in msgs:
                assert m["origin"] == expected_origin, f"unexpected origin {m['origin']}"
                assert m["id"] == CALL_ID, f"unexpected id {m['id']}"
                assert m["v"] == 1
            height = max(m["data"] for m in msgs if m["event"] == "resize")
            assert 150 < height < 1200, f"implausible content height {height}"
            host.screenshot(path=os.path.join(output_dir, "embedded_profile.png"))

            print("Clicking Close inside the dialog...")
            frame.get_by_role("button", name="Close").click()
            host.wait_for_function("window.msgs.some(m => m.event === 'cancel')", timeout=10000)
            print("Cancel message received.")

            print("Embedding from an untrusted caller origin...")
            evil = context.new_page()
            frame = open_host(evil, intent_url("https://evil.example.com"))
            frame.get_by_text("Approval").wait_for(timeout=60000)
            frame.get_by_text("Exit Profile").wait_for(timeout=10000)
            evil.wait_for_timeout(1500)
            assert messages(evil) == [], f"untrusted caller received {messages(evil)}"
            print("Untrusted caller got no messages and no Close button.")

            print("All tests passed!")
        except Exception as e:
            print(f"TEST FAILED: {e}")
            for i, pg in enumerate(context.pages):
                pg.screenshot(path=os.path.join(output_dir, f"failure_{i}.png"))
            sys.exit(1)
        finally:
            browser.close()
            server.shutdown()


if __name__ == "__main__":
    run()
