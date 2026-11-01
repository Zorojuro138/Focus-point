from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from focuspilot.system.browser_metadata import PORT, BrowserMetadataServer

ORIGIN = f"chrome-extension://{'a' * 32}"
BASE_URL = f"http://127.0.0.1:{PORT}"


def test_bridge_shares_only_fresh_metadata_during_a_session(qtbot) -> None:
    state = {"active": False}
    server = BrowserMetadataServer(lambda: state["active"])
    server.start()
    try:
        state_request = Request(f"{BASE_URL}/v1/state", headers={"Origin": ORIGIN})
        with urlopen(state_request, timeout=2) as response:
            assert json.loads(response.read()) == {"monitoring": False}

        payload = json.dumps(
            {
                "title": "Lecture",
                "url": "https://youtube.com/watch?v=private#part",
                "browser": "chrome.exe",
            }
        ).encode()
        request = Request(
            f"{BASE_URL}/v1/tab",
            data=payload,
            headers={"Origin": ORIGIN, "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            assert response.status == 200

        state["active"] = True
        with qtbot.waitSignal(server.bridge.metadata_received, timeout=2000) as signal:
            with urlopen(request, timeout=2) as response:
                assert response.status == 200
        title, url, browser, _received_at = signal.args
        assert title == "Lecture"
        assert url == "https://youtube.com/watch"
        assert browser == "chrome.exe"
    finally:
        server.stop()


def test_bridge_rejects_non_extension_origins(qtbot) -> None:
    server = BrowserMetadataServer(lambda: True)
    server.start()
    request = Request(f"{BASE_URL}/v1/state", headers={"Origin": "https://example.com"})
    try:
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=2)
        assert error.value.code == 403
    finally:
        server.stop()
