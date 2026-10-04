"""E2E: calls in rooms through the `call.join` DDNS Intent of the call app.

Needs the call app (reflex_ddns_livekit_audio_chat) running too, and both apps
pointed at each other:

    # call app, e.g. on 3200/8200
    DDNS_INTENT_URL_LIVEKIT=http://localhost:3200 poetry run ./run_test_suite.sh call_intent

1. Ring targeting (unit level, since verified members cannot log in from a
   test): private rooms and direct messages ring their members, public rooms
   the people who have the room open; members, people who answered or declined,
   and calls past their ringing time don't ring.
2. Three guests open "General". Caller starts a call: the dialog shows the
   call app joined to the room. Callee and Decliner get the incoming-call popup.
3. Decliner declines (popup gone, header offers "Join call"); Callee accepts and
   both hear each other (inbound audio bytes grow inside the dialogs).
4. Decliner joins from the header (3 in the call), Callee hangs up, Decliner
   closes the dialog (on_cancel), Caller hangs up: the call is gone everywhere.
5. Switching calls: Caller, in a new General call, accepts a Tech Talk call
   from the popup; the General call ends (not the Tech Talk one).
"""

import os
import sys
import time
import types

from dotenv import load_dotenv
from playwright.sync_api import Page, expect, sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000").rstrip("/")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
ROOM = "General"
OTHER_ROOM = "Tech Talk"
CALLER, CALLEE, DECLINER = "Caller", "Callee", "Decliner"

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


def check_ring_targets():
    from relack.models import CallInfo, RoomInfo, UserProfile
    from relack.states.shared_state import GlobalLobbyState

    class Lobby:
        _room_title = GlobalLobbyState._room_title
        _display_name = GlobalLobbyState._display_name

    rooms = {
        "General": RoomInfo(name="General"),
        "Secret": RoomInfo(name="Secret", created_by="owner", is_private=True, allowed_members=["alice"]),
        "dm-1": RoomInfo(name="dm-1", created_by="owner", is_private=True, allowed_members=["bob"], is_direct=True),
    }

    def call(room, **kw):
        return CallInfo(room_name=room, call_id="x", started_by="owner", started_at=time.time(),
                        members={"t-owner": "owner"}, **kw)

    def ringing_for(viewer, location="", calls=None):
        lobby = Lobby()
        lobby._rooms = rooms
        lobby._known_profiles = {"owner": UserProfile(username="owner", nickname="Olivia", is_guest=False)}
        lobby._calls = calls if calls is not None else {name: call(name) for name in rooms}
        lobby._viewer_by_client = {"tok": viewer}
        lobby._user_locations = {"tok": location} if location else {}
        lobby.router = types.SimpleNamespace(session=types.SimpleNamespace(client_token="tok"))
        fget = GlobalLobbyState.computed_vars["incoming_calls"]._fget
        return {(c.room_name, c.title, c.caller) for c in fget(lobby)}

    assert ringing_for("alice", "General") == {("General", "General", "Olivia"), ("Secret", "Secret", "Olivia")}
    assert ringing_for("alice") == {("Secret", "Secret", "Olivia")}, "public room rings only people in it"
    assert ringing_for("bob") == {("dm-1", "Olivia", "Olivia")}, "DM rings the other person, titled with the caller"
    assert ringing_for("carol", "General") == {("General", "General", "Olivia")}, "outsiders: no private rings"
    assert ringing_for("owner", "General") == set(), "members are not rung"
    assert ringing_for("alice", calls={"Secret": call("Secret", responded=["alice"])}) == set()
    assert ringing_for("alice", calls={"Secret": call("Secret", ringing=False)}) == set()


def login_guest(context, name) -> Page:
    page = context.new_page()
    page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
    page.get_by_placeholder("CoolPanda99").fill(name)
    page.get_by_role("button", name="Continue as Guest").click()
    page.wait_for_selector(f"text={name}", timeout=30000)
    page.get_by_role("heading", name=ROOM, level=3).click()
    expect(page.get_by_role("heading", name=ROOM, level=2)).to_be_visible(timeout=15000)
    return page


def call_frame(page: Page):
    return page.frame_locator("#ddns-intent-frame")


def wait_in_call(page: Page, participants: list[str]):
    frame = call_frame(page)
    expect(frame.locator("#connection-status")).to_have_text("Connected", timeout=60000)
    for name in participants:
        expect(frame.locator(".participant-card", has_text=name)).to_be_visible(timeout=30000)
    expect(frame.locator(".participant-card")).to_have_count(len(participants), timeout=30000)


def inbound_audio(page: Page) -> int:
    return page.query_selector("#ddns-intent-frame").content_frame().evaluate(_INBOUND_AUDIO_BYTES)


def popup(page: Page):
    return page.get_by_role("alertdialog", name="Incoming call")


def run():
    output_dir = os.environ.get("OUTPUT_DIR") or os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    shots: dict[str, bytes] = {}

    print("Ring targeting...")
    check_ring_targets()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                  "--autoplay-policy=no-user-gesture-required"],
        )
        contexts = [browser.new_context(permissions=["microphone"]) for _ in range(3)]
        try:
            print("Three guests open General...")
            caller, callee, decliner = (login_guest(c, n) for c, n in zip(contexts, (CALLER, CALLEE, DECLINER)))

            print("Caller starts a call...")
            caller.get_by_role("button", name="Start a call").click()
            wait_in_call(caller, [CALLER])
            expect(call_frame(caller).get_by_role("heading", name=ROOM)).to_be_visible()

            print("Callee and Decliner are rung...")
            for page in (callee, decliner):
                expect(popup(page)).to_be_visible(timeout=15000)
                expect(popup(page)).to_contain_text(f"# {ROOM}")
                expect(popup(page)).to_contain_text(f"{CALLER} is calling")
            expect(popup(caller)).to_have_count(0)
            shots["incoming_call"] = callee.screenshot()

            print("Decliner declines...")
            popup(decliner).get_by_role("button", name="Decline").click()
            expect(popup(decliner)).to_have_count(0, timeout=10000)
            expect(decliner.get_by_role("button", name="Join call · 1")).to_be_visible(timeout=10000)

            print("Callee accepts; both hear each other...")
            popup(callee).get_by_role("button", name="Accept").click()
            expect(popup(callee)).to_have_count(0, timeout=10000)
            wait_in_call(callee, [CALLER, CALLEE])
            wait_in_call(caller, [CALLER, CALLEE])
            for page in (caller, callee):
                first = inbound_audio(page)
                page.wait_for_timeout(3000)
                second = inbound_audio(page)
                print(f"  inbound audio bytes: {first} -> {second}")
                assert second > first > 0, "no audio received inside the call dialog"
            shots["in_call"] = caller.screenshot()

            print("Decliner joins from the header...")
            decliner.get_by_role("button", name="Join call · 2").click()
            wait_in_call(decliner, [CALLER, CALLEE, DECLINER])
            wait_in_call(caller, [CALLER, CALLEE, DECLINER])

            print("Callee hangs up...")
            call_frame(callee).get_by_role("button", name="Hang up").click()
            expect(callee.locator("#ddns-intent-frame")).to_have_count(0, timeout=15000)
            wait_in_call(caller, [CALLER, DECLINER])
            expect(callee.get_by_role("button", name="Join call · 2")).to_be_visible(timeout=10000)
            callee.wait_for_timeout(4000)  # a heartbeat or two: answered once, never rung again
            expect(popup(callee)).to_have_count(0)
            shots["after_hang_up"] = callee.screenshot()

            print("Decliner closes the dialog (on_cancel)...")
            decliner.get_by_role("button", name="Close").click()
            expect(decliner.locator("#ddns-intent-frame")).to_have_count(0, timeout=10000)
            wait_in_call(caller, [CALLER])
            expect(callee.get_by_role("button", name="Join call · 1")).to_be_visible(timeout=10000)

            print("Caller hangs up: the call is over...")
            call_frame(caller).get_by_role("button", name="Hang up").click()
            expect(caller.locator("#ddns-intent-frame")).to_have_count(0, timeout=15000)
            for page in (caller, callee, decliner):
                expect(page.get_by_role("button", name="Start a call")).to_be_visible(timeout=10000)
                expect(page.get_by_title("Call in progress")).to_have_count(0)

            print("Switching calls: accept a second call from inside one...")
            caller.get_by_role("button", name="Start a call").click()
            wait_in_call(caller, [CALLER])
            # Open Tech Talk underneath the dialog, so its call rings Caller.
            caller.get_by_role("heading", name=OTHER_ROOM, level=3).dispatch_event("click")
            callee.get_by_role("heading", name=OTHER_ROOM, level=3).click()
            expect(callee.get_by_role("heading", name=OTHER_ROOM, level=2)).to_be_visible(timeout=15000)
            callee.get_by_role("button", name="Start a call").click()
            wait_in_call(callee, [CALLEE])
            expect(popup(caller)).to_contain_text(f"# {OTHER_ROOM}", timeout=15000)
            shots["call_waiting"] = caller.screenshot()
            popup(caller).get_by_role("button", name="Accept").click()
            wait_in_call(caller, [CALLER, CALLEE])
            expect(call_frame(caller).get_by_role("heading", name=OTHER_ROOM)).to_be_visible()
            wait_in_call(callee, [CALLER, CALLEE])
            badges = decliner.get_by_title("Call in progress")
            expect(badges).to_have_count(1, timeout=10000)  # General's call ended
            expect(badges).to_have_text("2")
            call_frame(caller).get_by_role("button", name="Hang up").click()
            call_frame(callee).get_by_role("button", name="Hang up").click()
            expect(decliner.get_by_title("Call in progress")).to_have_count(0, timeout=10000)

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
