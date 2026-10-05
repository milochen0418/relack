"""E2E: the caller chooses the call app; whoever answers or joins goes straight into it.

Needs two `call.join` providers. The call app (reflex_ddns_livekit_audio_chat)
can stand in for both: `livekit` at localhost and `livekit-alt` at 127.0.0.1 are
two origins of the same server, so a dialog's URL tells which app it opened:

    # call app, e.g. on 3200/8200
    DDNS_INTENT_PROVIDER_CALL_JOIN=livekit,livekit-alt DDNS_INTENT_URL_LIVEKIT=http://localhost:3200 \\
    DDNS_INTENT_URL_LIVEKIT_ALT=http://127.0.0.1:3200 poetry run ./run_test_suite.sh call_app_choice

1. Caller starts a call: the chooser lists both apps, and nobody is rung while
   the caller chooses. Closing the chooser starts no call.
2. Caller starts again and picks the second app. Callee accepts from the popup
   and Joiner joins from the header: neither is asked, both open the caller's
   app, and all three are in the same call.
3. Once everyone hung up, the next call is chosen afresh: Caller picks the
   first app, and Callee joins it there.
"""

import os
import re
import sys

from dotenv import load_dotenv
from playwright.sync_api import Page, expect, sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(ROOT, ".env"))

from reflex_ddns_auth.intent.protocol import app_url  # noqa: E402  (after .env)

BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000").rstrip("/")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
ROOM = "General"
CALLER, CALLEE, JOINER = "Caller", "Callee", "Joiner"
PROVIDERS = [a.strip() for a in os.environ.get("DDNS_INTENT_PROVIDER_CALL_JOIN", "").split(",") if a.strip()]


def login_guest(context, name) -> Page:
    page = context.new_page()
    page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
    page.get_by_placeholder("CoolPanda99").fill(name)
    page.get_by_role("button", name="Continue as Guest").click()
    page.wait_for_selector(f"text={name}", timeout=30000)
    page.get_by_role("heading", name=ROOM, level=3).click()
    expect(page.get_by_role("heading", name=ROOM, level=2)).to_be_visible(timeout=15000)
    return page


def popup(page: Page):
    return page.get_by_role("alertdialog", name="Incoming call")


def chooser(page: Page):
    return page.get_by_text("Open with", exact=True)


def choose(page: Page, app: str):
    expect(chooser(page)).to_be_visible(timeout=15000)
    page.get_by_role("button").filter(has_text=app_url(app)).click()


def wait_in_call(page: Page, app: str, participants: list[str]):
    """In the call, through ``app``, with exactly ``participants``."""
    frame = page.locator("#ddns-intent-frame")
    expect(frame).to_have_attribute("src", re.compile("^" + re.escape(app_url(app)) + "/intent/call-join\\?"),
                                    timeout=15000)
    expect(chooser(page)).to_have_count(0)
    call = page.frame_locator("#ddns-intent-frame")
    expect(call.locator("#connection-status")).to_have_text("Connected", timeout=60000)
    for name in participants:
        expect(call.locator(".participant-card", has_text=name)).to_be_visible(timeout=30000)
    expect(call.locator(".participant-card")).to_have_count(len(participants), timeout=30000)


def hang_up(page: Page):
    page.frame_locator("#ddns-intent-frame").get_by_role("button", name="Hang up").click()
    expect(page.locator("#ddns-intent-frame")).to_have_count(0, timeout=15000)


def run():
    output_dir = os.environ.get("OUTPUT_DIR") or os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    if len(PROVIDERS) < 2:
        print("TEST FAILED: needs two call apps in DDNS_INTENT_PROVIDER_CALL_JOIN (see the docstring)")
        sys.exit(1)
    first, second = PROVIDERS[:2]
    shots: dict[str, bytes] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                  "--autoplay-policy=no-user-gesture-required"],
        )
        contexts = [browser.new_context(permissions=["microphone"]) for _ in range(3)]
        try:
            print("Three guests open General...")
            caller, callee, joiner = (login_guest(c, n) for c, n in zip(contexts, (CALLER, CALLEE, JOINER)))

            print("Caller starts a call: the chooser lists both apps, nobody is rung yet...")
            caller.get_by_role("button", name="Start a call").click()
            expect(chooser(caller)).to_be_visible(timeout=15000)
            for app in (first, second):
                expect(caller.get_by_role("button").filter(has_text=app_url(app))).to_be_visible()
            shots["chooser"] = caller.screenshot()
            callee.wait_for_timeout(4000)  # a heartbeat or more
            expect(popup(callee)).to_have_count(0)
            expect(callee.get_by_title("Call in progress")).to_have_count(0)

            print("Closing the chooser starts no call...")
            caller.locator("[data-intent-dialog]").get_by_role("button", name="Close", exact=True).click()
            expect(chooser(caller)).to_have_count(0, timeout=10000)
            expect(caller.locator("#ddns-intent-frame")).to_have_count(0)
            callee.wait_for_timeout(4000)
            for page in (caller, callee, joiner):
                expect(page.get_by_role("button", name="Start a call")).to_be_visible()
                expect(popup(page)).to_have_count(0)

            print(f"Caller starts again and picks {second}...")
            caller.get_by_role("button", name="Start a call").click()
            choose(caller, second)
            wait_in_call(caller, second, [CALLER])

            print(f"Callee accepts: straight into {second}, not asked...")
            expect(popup(callee)).to_be_visible(timeout=15000)
            popup(callee).get_by_role("button", name="Accept").click()
            wait_in_call(callee, second, [CALLER, CALLEE])
            wait_in_call(caller, second, [CALLER, CALLEE])
            shots["callee_in_call"] = callee.screenshot()

            print(f"Joiner joins from the header: {second} too...")
            popup(joiner).get_by_role("button", name="Decline").click()
            joiner.get_by_role("button", name="Join call · 2").click()
            wait_in_call(joiner, second, [CALLER, CALLEE, JOINER])
            wait_in_call(caller, second, [CALLER, CALLEE, JOINER])

            print("Everyone hangs up...")
            for page in (joiner, callee, caller):
                hang_up(page)
            for page in (caller, callee, joiner):
                expect(page.get_by_role("button", name="Start a call")).to_be_visible(timeout=10000)

            print(f"The next call is chosen afresh: Caller picks {first}, Callee follows...")
            caller.get_by_role("button", name="Start a call").click()
            choose(caller, first)
            wait_in_call(caller, first, [CALLER])
            expect(popup(callee)).to_be_visible(timeout=15000)
            popup(callee).get_by_role("button", name="Accept").click()
            wait_in_call(callee, first, [CALLER, CALLEE])
            wait_in_call(caller, first, [CALLER, CALLEE])
            hang_up(callee)
            hang_up(caller)
            expect(joiner.get_by_title("Call in progress")).to_have_count(0, timeout=10000)

            print("All tests passed!")
        except Exception as e:
            print(f"TEST FAILED: {e}")
            for i, ctx in enumerate(contexts):
                for j, pg in enumerate(ctx.pages):
                    pg.screenshot(path=os.path.join(output_dir, f"failure_{i}_{j}.png"))
            sys.exit(1)
        finally:
            browser.close()
            for name, png in shots.items():
                with open(os.path.join(output_dir, f"{name}.png"), "wb") as f:
                    f.write(png)


if __name__ == "__main__":
    run()
