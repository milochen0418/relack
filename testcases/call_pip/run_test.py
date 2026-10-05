"""E2E: a minimized call's pill drags along the bottom, or up into a picture-in-picture window.

Needs the call app (reflex_ddns_livekit_audio_chat) running too, as for call_intent:

    # call app, e.g. on 3200/8200
    DDNS_INTENT_PROVIDER_CALL_JOIN=livekit DDNS_INTENT_URL_LIVEKIT=http://localhost:3200 \\
    poetry run ./run_test_suite.sh call_pip

1. Caller calls, Callee answers. Minimized, the call is a pill at the bottom left.
2. Dragged along the bottom, the pill stays a pill where it is dropped (never
   lower); a click still brings the call back, and minimized again it returns
   to that place.
3. Lifted up, it becomes a small window of the call, which keeps running in it
   (same page, audio flowing). The window takes no clicks: a click on its Hang
   up brings the call back instead of ending it. Minimized again, the call goes
   back to its window.
4. The corner handle resizes the window, keeping its proportions; pushed down to
   the bottom, the window turns back into the pill.
5. A reload keeps the window where it was.
"""

import os
import sys

from dotenv import load_dotenv
from playwright.sync_api import Page, expect, sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(ROOT, ".env"))

BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000").rstrip("/")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
ROOM = "General"
CALLER, CALLEE = "Caller", "Callee"
WIDTH, HEIGHT = 1280, 720
FLOOR = 16  # the tray's gap to the bottom

_INBOUND_AUDIO_BYTES = """async () => {
    const room = window.livekitClient && window.livekitClient.room;
    if (!room) return -1;
    let total = 0;
    for (const p of room.remoteParticipants.values()) {
        for (const pub of p.audioTrackPublications.values()) {
            const track = pub.track;
            if (!track || !track.receiver) continue;
            const stats = await track.receiver.getStats();
            stats.forEach((r) => { if (r.type === 'inbound-rtp') total += r.bytesReceived || 0; });
        }
    }
    return total;
}"""


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


def call_frame(page: Page):
    """The call dialog in front."""
    return page.frame_locator("#ddns-intent-frame")


def call_page(page: Page):
    """The call app's page, in front, minimized or in its window."""
    return page.query_selector('iframe[data-intent-action="call.join"]').content_frame()


def call_dialog(page: Page):
    """The call dialog's element: the whole dialog in front, hidden when minimized, or the window."""
    return page.locator('[data-intent-dialog]:has(iframe[data-intent-action="call.join"])')


def pill(page: Page):
    return page.locator("[data-intent-tray-item]")


def wait_in_call(page: Page, count: int):
    frame = call_frame(page)
    expect(frame.locator("#connection-status")).to_have_text("Connected", timeout=60000)
    expect(frame.locator(".participant-card")).to_have_count(count, timeout=30000)


def assert_audio_flows(page: Page):
    first = call_page(page).evaluate(_INBOUND_AUDIO_BYTES)
    page.wait_for_timeout(3000)
    second = call_page(page).evaluate(_INBOUND_AUDIO_BYTES)
    print(f"  inbound audio bytes: {first} -> {second}")
    assert second > first > 0, "no audio received in the call"


def box(locator) -> dict:
    b = locator.bounding_box()
    assert b is not None, f"{locator} is not shown"
    return b


def center(b: dict) -> tuple[float, float]:
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


def bottom(b: dict) -> float:
    return b["y"] + b["height"]


def drag(page: Page, start: tuple[float, float], end: tuple[float, float]):
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*end, steps=15)
    page.mouse.up()


def near(a: float, b: float, tolerance: float = 3) -> bool:
    return abs(a - b) <= tolerance


def run():
    output_dir = os.environ.get("OUTPUT_DIR") or os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    shots: dict[str, bytes] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                  "--autoplay-policy=no-user-gesture-required"],
        )
        contexts = [
            browser.new_context(viewport={"width": WIDTH, "height": HEIGHT}, permissions=["microphone"])
            for _ in range(2)
        ]
        try:
            print("Caller calls, Callee answers...")
            caller, callee = (login_guest(c, n) for c, n in zip(contexts, (CALLER, CALLEE)))
            caller.get_by_role("button", name="Start a call").click()
            wait_in_call(caller, 1)
            expect(popup(callee)).to_be_visible(timeout=15000)
            popup(callee).get_by_role("button", name="Accept").click()
            wait_in_call(callee, 2)
            wait_in_call(caller, 2)
            call_page(caller).evaluate("window.__e2eMarker = 7")  # gone if the call page reloads

            print("Minimized, the call is a pill at the bottom left...")
            caller.get_by_role("button", name="Minimize").click()
            expect(pill(caller)).to_be_visible(timeout=10000)
            expect(call_dialog(caller)).to_be_hidden()
            start = box(pill(caller))
            assert near(bottom(start), HEIGHT - FLOOR), start

            print("Dragged along the bottom, it stays a pill where it is dropped...")
            x, y = center(start)
            drag(caller, (x, y), (x + 300, y - 25))
            expect(call_dialog(caller)).to_be_hidden()
            moved = box(pill(caller))
            assert near(moved["x"], start["x"] + 300) and near(bottom(moved), bottom(start)), moved
            drag(caller, center(moved), (center(moved)[0], HEIGHT - 2))  # never below the tray
            assert near(bottom(box(pill(caller))), bottom(start))

            print("A click still brings the call back; minimized again, the pill is where it was...")
            caller.get_by_role("button", name=f"Show Call · {ROOM}").click()
            wait_in_call(caller, 2)
            caller.get_by_role("button", name="Minimize").click()
            expect(pill(caller)).to_be_visible(timeout=10000)
            assert near(box(pill(caller))["x"], moved["x"]), box(pill(caller))

            print("Lifted up, the pill becomes a small window of the call...")
            x, y = center(box(pill(caller)))
            drag(caller, (x, y), (x, y - 250))
            expect(call_dialog(caller)).to_be_visible(timeout=10000)
            expect(pill(caller)).to_be_hidden()
            window = box(call_dialog(caller))
            print(f"  window: {window}")
            assert 200 <= window["width"] <= 280 and window["height"] > 60, window
            assert bottom(window) < HEIGHT - FLOOR - 100, window
            shots["window"] = caller.screenshot()

            print("The call keeps running in it, never reloaded...")
            assert call_page(caller).evaluate("window.__e2eMarker") == 7, "the call page reloaded"
            expect(call_frame(callee).locator(".participant-card")).to_have_count(2)
            assert_audio_flows(caller)

            print("The window takes no clicks: Hang up there brings the call back instead...")
            hang_up = call_page(caller).get_by_role("button", name="Hang up")
            hx, hy = hang_up.evaluate("el => { const r = el.getBoundingClientRect(); "
                                      "return [r.x + r.width / 2, r.y + r.height / 2]; }")
            dialog_box = call_dialog(caller).locator("[data-intent-box]")
            scale = window["width"] / dialog_box.evaluate("el => el.offsetWidth")
            caller.mouse.click(window["x"] + hx * scale, window["y"] + hy * scale)
            expect(caller.locator("#ddns-intent-frame")).to_be_visible(timeout=10000)
            wait_in_call(caller, 2)
            expect(call_frame(callee).locator(".participant-card")).to_have_count(2)

            print("Minimized again, the call goes back to its window...")
            caller.get_by_role("button", name="Minimize").click()
            expect(caller.locator("#ddns-intent-frame")).to_have_count(0, timeout=10000)  # left the front
            expect(call_dialog(caller)).to_be_visible(timeout=10000)
            again = box(call_dialog(caller))
            assert all(near(again[k], window[k]) for k in ("x", "y", "width", "height")), again

            print("The corner handle resizes it, keeping its proportions...")
            handle = box(call_dialog(caller).locator("[data-intent-resize]"))
            x, y = center(handle)
            drag(caller, (x, y), (x + 120, y + 20))
            bigger = box(call_dialog(caller))
            print(f"  resized: {bigger}")
            assert near(bigger["width"], again["width"] + 120, 4), bigger
            assert near(bigger["height"] / bigger["width"], again["height"] / again["width"], 0.02), bigger
            assert near(bigger["x"], again["x"]) and near(bigger["y"], again["y"]), bigger
            shots["window_resized"] = caller.screenshot()

            print("Pushed down to the bottom, it turns back into the pill...")
            x, y = center(bigger)
            drag(caller, (x, y), (x, HEIGHT - 5))
            expect(pill(caller)).to_be_visible(timeout=10000)
            expect(call_dialog(caller)).to_be_hidden()
            assert near(bottom(box(pill(caller))), HEIGHT - FLOOR), box(pill(caller))
            assert call_page(caller).evaluate("window.__e2eMarker") == 7, "the call page reloaded"

            print("A reload keeps the window where it was...")
            x, y = center(box(pill(caller)))
            drag(caller, (x, y), (x - 100, y - 300))
            expect(call_dialog(caller)).to_be_visible(timeout=10000)
            before = box(call_dialog(caller))
            caller.reload(wait_until="domcontentloaded")
            expect(call_dialog(caller)).to_be_visible(timeout=30000)
            expect(pill(caller)).to_be_hidden()
            caller.wait_for_timeout(2000)  # the window settles on the dialog's real size
            after = box(call_dialog(caller))
            assert near(after["x"], before["x"]) and near(after["width"], before["width"]), (before, after)
            expect(call_frame(callee).locator(".participant-card")).to_have_count(2, timeout=30000)

            print("Bring it back and hang up...")
            caller.mouse.click(*center(after))
            wait_in_call(caller, 2)
            call_frame(caller).get_by_role("button", name="Hang up").click()
            expect(caller.locator('iframe[data-intent-action="call.join"]')).to_have_count(0, timeout=15000)
            expect(pill(caller)).to_have_count(0)
            call_frame(callee).get_by_role("button", name="Hang up").click()
            expect(callee.get_by_title("Call in progress")).to_have_count(0, timeout=10000)

            print("All tests passed!")
        except Exception as e:
            print(f"TEST FAILED: {e}")
            for i, ctx in enumerate(contexts):
                for j, pg in enumerate(ctx.pages):
                    shots[f"failure_{i}_{j}"] = pg.screenshot()
            sys.exit(1)
        finally:
            browser.close()
            for name, png in shots.items():
                with open(os.path.join(output_dir, f"{name}.png"), "wb") as f:
                    f.write(png)


if __name__ == "__main__":
    run()
