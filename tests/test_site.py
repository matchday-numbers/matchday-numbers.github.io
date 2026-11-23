"""Opens the real site in a headless browser and fails on script errors or error pages.
Skipped when Playwright isn't installed (the tests workflow installs it)."""
import functools
import http.server
import json
import os
import threading

import pytest

pw = pytest.importorskip("playwright.sync_api")

SITE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site")


@pytest.fixture(scope="module")
def server():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=SITE)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/"
    httpd.shutdown()


def routes():
    data = os.path.join(SITE, "data")
    out = ["#/", "#/teams", "#/accuracy", "#/calls", "#/about", "#/search/madrid"]
    meta = json.load(open(os.path.join(data, "meta.json")))
    for lg in meta["leagues"]:
        out.append(f"#/league/{lg['key']}")
        L = json.load(open(os.path.join(data, f"league-{lg['key']}.json")))
        if L["upcoming"]:
            out.append(f"#/match/{L['upcoming'][0]['id']}")
        if L["recent"]:
            out.append(f"#/match/{L['recent'][0]['id']}")
        if L["table"]:
            out.append(f"#/team/{L['table'][0]['team']['slug']}")
    return out


def test_every_page_renders(server):
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch(timeout=60000)  # Playwright's own Chromium
        except Exception:
            browser = p.chromium.launch(executable_path="/usr/bin/google-chrome", timeout=60000)
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        bad = []
        for r in routes():
            page.goto(server + r)
            page.wait_for_function("!document.querySelector('#app .loading')", timeout=15000)
            text = page.inner_text("#app")
            if "Page not found" in text or len(text) < 200:
                bad.append(f"{r}: {text[:120]!r}")
        browser.close()
    assert not errors, errors[:5]
    assert not bad, bad[:5]
