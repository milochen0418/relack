"""E2E: sharing files and searching.

1. Attach a file with the paperclip (file chooser) and send it with text: the
   message shows a file card whose link downloads it.
2. Paste a screenshot into the box: it is named "Pasted image <date>" and shows
   as a picture, which opens in a viewer when clicked; a file dropped on the
   room is added too and can be removed before sending.
3. Search (Enter in the sidebar box) finds the message, the file and the
   person; clicking the message opens its room with it highlighted. Typing
   alone filters the room list.

    poetry run ./run_test_suite.sh chat_files_search
"""

import base64
import os
import sys
import tempfile
import time
import urllib.request

from dotenv import load_dotenv
from playwright.sync_api import expect, sync_playwright

load_dotenv()

BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000").rstrip("/")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
STAMP = str(int(time.time()))[-5:]
USER = "Filer" + STAMP
ROOM = "Files " + STAMP
# A 16x16 PNG.
PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAKklEQVR42mNk+M9Qz0AEYBxVSF+F/4F4"
    "QwMDA8P/BgYGBlIUDqMQAQBVtwgRe0p3CQAAAABJRU5ErkJggg=="
)


def run():
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    shots: dict[str, bytes] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()
        try:
            page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
            page.get_by_placeholder("CoolPanda99").fill(USER)
            page.get_by_role("button", name="Continue as Guest").click()
            page.get_by_role("button", name="New room").click()
            dialog = page.get_by_role("dialog", name="Create New Room")
            dialog.get_by_placeholder("e.g. Design Team").fill(ROOM)
            dialog.get_by_role("button", name="Create Room").click()
            page.locator("aside").get_by_role("heading", name=ROOM, exact=True).click()
            box = page.get_by_role("textbox", name="Message", exact=True)
            box.wait_for(timeout=15000)
            pending = page.locator("[data-relack-pending]")

            print("Attach a file with the paperclip...")
            report = os.path.join(tempfile.mkdtemp(), f"report-{STAMP}.txt")
            with open(report, "w") as f:
                f.write("quarterly numbers\n" * 50)
            with page.expect_file_chooser() as chooser:
                page.get_by_role("button", name="Attach files").first.click()
            chooser.value.set_files(report)
            expect(pending).to_have_count(1, timeout=15000)
            box.click()
            page.keyboard.type("Here is the report " + STAMP)
            page.keyboard.press("Enter")
            card = page.get_by_title(f"Download report-{STAMP}.txt")
            expect(card).to_be_visible(timeout=15000)
            expect(pending).to_have_count(0)
            with urllib.request.urlopen(card.get_attribute("href")) as resp:
                assert resp.status == 200 and resp.read().startswith(b"quarterly numbers"), resp.status

            print("Paste a screenshot...")
            box.click()
            box.evaluate(
                """(t, b64) => {
                    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
                    const dt = new DataTransfer();
                    dt.items.add(new File([bytes], 'image.png', {type: 'image/png'}));
                    t.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
                }""",
                PNG,
            )
            expect(pending).to_have_count(1, timeout=15000)
            expect(pending).to_contain_text("Pasted image")
            page.keyboard.press("Enter")
            expect(pending).to_have_count(0, timeout=15000)
            picture = page.locator(".relack-bubble img[alt^='Pasted image']")
            expect(picture).to_have_count(1, timeout=15000)
            page.wait_for_function(
                "() => { const i = document.querySelector(\".relack-bubble img[alt^='Pasted image']\"); "
                "return i && i.naturalWidth === 16; }",
                timeout=15000,
            )
            picture.first.click()
            viewer = page.get_by_role("dialog", name=picture.first.get_attribute("alt"))
            expect(viewer).to_be_visible(timeout=5000)
            expect(viewer.get_by_role("link", name="Download")).to_be_visible()
            page.keyboard.press("Escape")
            expect(viewer).to_have_count(0)

            print("Drop a file, then remove it before sending...")
            page.evaluate(
                """() => {
                    const dt = new DataTransfer();
                    dt.items.add(new File(['dropped data'], 'dropped-notes.md', {type: 'text/markdown'}));
                    const zone = document.querySelector('[data-relack-drop="relack-upload-main"]');
                    zone.dispatchEvent(new DragEvent('dragover', {dataTransfer: dt, bubbles: true, cancelable: true}));
                    zone.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true}));
                }"""
            )
            expect(pending).to_have_count(1, timeout=15000)
            page.get_by_role("button", name="Remove dropped-notes.md").click()
            expect(pending).to_have_count(0, timeout=10000)
            shots["files"] = page.screenshot()

            print("Search messages, files and people...")
            for i in range(3):
                box.click()
                page.keyboard.type(f"filler {i}")
                page.keyboard.press("Enter")
            search = page.get_by_label("Search", exact=True)
            search.fill("report " + STAMP)
            search.press("Enter")
            expect(page.get_by_role("heading", name="Search results")).to_be_visible(timeout=10000)
            hits = page.locator("section[aria-label=Messages] button")
            expect(hits).to_have_count(1, timeout=10000)
            expect(hits.first.locator("mark")).to_have_text("report " + STAMP)
            search.fill(f"report-{STAMP}")
            search.press("Enter")
            expect(page.locator("section[aria-label=Files]").get_by_text(f"report-{STAMP}.txt")).to_be_visible(timeout=10000)
            search.fill(USER)
            search.press("Enter")
            expect(page.locator("section[aria-label=People]").get_by_text(USER).first).to_be_visible(timeout=10000)
            # Showing results, the room list is not filtered by the query.
            expect(page.locator("aside").get_by_role("heading", name=ROOM, exact=True)).to_be_visible()
            shots["search"] = page.screenshot()

            print("Clicking a result jumps to the message...")
            search.fill("report " + STAMP)
            search.press("Enter")
            hits.first.click()
            highlighted = page.locator("#relack-messages .relack-highlight")
            expect(highlighted).to_have_count(1, timeout=10000)
            expect(highlighted).to_contain_text("Here is the report " + STAMP)

            print("Typing filters the room list...")
            search.fill("")
            expect(page.locator("aside").get_by_role("heading", name="General", exact=True)).to_be_visible()
            search.fill(ROOM.lower())
            expect(page.locator("aside").get_by_role("heading", name="General", exact=True)).to_have_count(0)
            expect(page.locator("aside").get_by_role("heading", name=ROOM, exact=True)).to_be_visible()
            search.fill("")
            expect(page.locator("aside").get_by_role("heading", name="General", exact=True)).to_be_visible()

            print("Closing search clears the box...")
            search.fill("report")
            search.press("Enter")
            page.get_by_role("button", name="Close search").click()
            expect(search).to_have_value("", timeout=10000)
            expect(page.get_by_role("textbox", name="Message", exact=True)).to_be_visible()

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
