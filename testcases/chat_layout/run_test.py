"""E2E: the layout at every width: nothing opens that can't be closed again.

At phone, tablet, laptop and desktop widths: the room list closes and reopens
from every panel (chat, people, search, browse, saved, no room), the drawer on
narrow screens closes with its button, a tap beside it and Esc, and it gets out
of the way after picking something. Thread and online users panels close too,
nothing scrolls sideways, and the composer and header buttons stay on screen.

    poetry run ./run_test_suite.sh chat_layout
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
SIZES = [(320, 640), (390, 800), (600, 800), (767, 900), (768, 900), (900, 800), (1024, 768), (1099, 800), (1100, 800), (1400, 900)]
NARROW = 768


def open_state(page) -> bool:
    return page.evaluate("!!document.querySelector('aside.relack-sidebar')")


def wait_open(page, want: bool):
    page.wait_for_function(
        """want => {
            const open = !!document.querySelector('aside.relack-sidebar');
            const width = document.querySelector('aside').getBoundingClientRect().width;
            return open === want && (want ? width > 200 : width === 0);
        }""",
        arg=want,
        timeout=8000,
    )


def toggle(page):
    return page.get_by_role("button", name="Toggle sidebar").first


def ensure_open(page):
    if not open_state(page):
        toggle(page).click(timeout=5000)
        wait_open(page, True)


def assert_fits(page, where):
    over = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert over <= 0, f"{where}: {over}px sideways"
    outside = page.evaluate(
        """() => [...document.querySelectorAll('nav button, nav a, main button, h2 ~ div button')]
        .filter(b => { const r = b.getBoundingClientRect(); return r.width && (r.right > innerWidth + 1 || r.left < -1); })
        .map(b => b.getAttribute('aria-label') || b.textContent)"""
    )
    assert not outside, f"{where}: off screen {outside}"


def run():
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    shots: dict[str, bytes] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = None
        try:
            for width, height in SIZES:
                print(f"{width}x{height}...")
                narrow = width < NARROW
                context = browser.new_context(viewport={"width": width, "height": height}, has_touch=narrow)
                page = context.new_page()
                page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
                page.get_by_placeholder("CoolPanda99").fill(f"Size{width}x{STAMP}")
                page.get_by_role("button", name="Continue as Guest").click()
                page.get_by_role("button", name="Browse rooms").wait_for(timeout=30000)
                page.wait_for_timeout(1000)

                # No room yet: the close button works, and the list can come back.
                page.get_by_role("button", name="Close sidebar").click()
                wait_open(page, False)
                toggle(page).click()
                wait_open(page, True)

                # Picking a room: on narrow screens the drawer gets out of the way.
                page.locator("aside").get_by_role("heading", name="General", exact=True).click()
                box = page.get_by_role("textbox", name="Message", exact=True)
                box.wait_for(timeout=15000)
                wait_open(page, not narrow)
                expect(box).to_be_in_viewport()
                assert_fits(page, "chat")

                # Open and close from the chat header, then with the close button.
                ensure_open(page)
                page.get_by_role("button", name="Close sidebar").click()
                wait_open(page, False)
                toggle(page).click()
                wait_open(page, True)
                if narrow:
                    page.mouse.click(width - 5, height / 2)  # beside the drawer
                    wait_open(page, False)
                    toggle(page).click()
                    wait_open(page, True)
                    page.keyboard.press("Escape")
                    wait_open(page, False)
                    shots[f"chat_{width}"] = page.screenshot()
                    toggle(page).click()
                    wait_open(page, True)
                    shots[f"drawer_{width}"] = page.screenshot()

                # Every panel: reachable, and the list can be closed and reopened there.
                for button, marker in (
                    ("People", "Search people..."),
                    ("Browse rooms", None),
                    ("Saved & scheduled", None),
                ):
                    ensure_open(page)
                    page.get_by_role("button", name=button, exact=True).click()
                    wait_open(page, not narrow)
                    if not narrow:
                        page.get_by_role("button", name="Close sidebar").click()
                        wait_open(page, False)
                    toggle(page).click()
                    wait_open(page, True)
                    assert_fits(page, button)

                search = page.get_by_label("Search", exact=True)
                search.fill("general")
                search.press("Enter")
                expect(page.get_by_role("heading", name="Search results")).to_be_in_viewport(timeout=10000)
                wait_open(page, not narrow)
                page.get_by_role("button", name="Close search").click()

                # Thread and online users: open, usable, closable.
                ensure_open(page)
                page.locator("aside").get_by_role("heading", name="General", exact=True).click()
                box.wait_for(timeout=15000)
                wait_open(page, not narrow)
                box.click()
                page.keyboard.type(f"layout {width} {STAMP}")
                page.keyboard.press("Enter")
                msg = page.locator("#relack-messages [id^=msg-]").filter(has_text=f"layout {width} {STAMP}")
                expect(msg).to_have_count(1, timeout=10000)
                msg.hover()
                msg.get_by_role("button", name="Reply in thread").click()
                reply = page.get_by_role("textbox", name="Reply", exact=True)
                expect(reply).to_be_in_viewport(timeout=10000)
                page.get_by_role("button", name="Close thread").click()
                expect(reply).to_have_count(0, timeout=10000)
                page.get_by_role("button", name="Online users", exact=True).click()
                close = page.get_by_role("button", name="Close online users")
                expect(close).to_be_in_viewport(timeout=10000)
                close.click()
                page.wait_for_timeout(500)
                expect(box).to_be_in_viewport()
                assert_fits(page, "after panels")

                # No room selected, list closed: it can still be opened.
                page.locator("button:has(svg.lucide-log-out)").last.click()
                page.get_by_text("No Room Selected").wait_for(timeout=10000)
                if open_state(page):
                    page.get_by_role("button", name="Close sidebar").click()
                    wait_open(page, False)
                toggle(page).click()
                wait_open(page, True)
                context.close()

            print("Resizing across the drawer size...")
            context = browser.new_context(viewport={"width": 1200, "height": 800})
            page = context.new_page()
            page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
            page.get_by_placeholder("CoolPanda99").fill(f"Resize{STAMP}")
            page.get_by_role("button", name="Continue as Guest").click()
            page.get_by_role("button", name="Browse rooms").wait_for(timeout=30000)
            page.wait_for_timeout(800)
            page.locator("aside").get_by_role("heading", name="General", exact=True).click()
            page.get_by_role("textbox", name="Message", exact=True).wait_for(timeout=15000)
            page.set_viewport_size({"width": 500, "height": 800})
            wait_open(page, False)
            page.set_viewport_size({"width": 1200, "height": 800})
            wait_open(page, True)
            print("All tests passed!")
        except Exception as e:
            print(f"TEST FAILED: {e}")
            if page:
                shots["failure"] = page.screenshot()
            sys.exit(1)
        finally:
            browser.close()
            for name, png in shots.items():
                with open(os.path.join(output_dir, f"{name}.png"), "wb") as f:
                    f.write(png)


if __name__ == "__main__":
    run()
