"""The arena's frontend, checked the only way a build-less frontend can be.

There is no bundler, which is the point: a judge clones the repo and the page
runs. The cost is that nothing tells you a template stopped compiling, or that
`format.js` drifted from the Python it mirrors, or that a control quietly
stopped doing anything — you find out by opening the page, if you happen to
open the right pane and click the right thing.

Two checks, because they catch different failures:

`check.mjs`   compiles every template against the vendored Vue and asserts the
              helpers. Fast, needs only Node.

`drive.mjs`   opens the real page in Chrome and clicks it. Every control bug
              this suite exists for was a *wiring* bug — a campaign the rail
              could not reach, a socket left open across a campaign switch —
              and every one of them compiled perfectly.

Both skip rather than fail where their tooling is absent. Python is the
documented prerequisite; a judge running `python -m praman test` should not see
red because they do not have Chrome.
"""

from __future__ import annotations

import contextlib
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

FRONTEND = Path(__file__).parent / "frontend"
ROOT = FRONTEND.parents[1]

NODE = shutil.which("node")
CHROME = next(
    (
        path
        for path in (
            shutil.which("chrome"),
            shutil.which("google-chrome"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/usr/bin/chromium",
        )
        if path and Path(path).exists()
    ),
    None,
)

needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")
needs_chrome = pytest.mark.skipif(CHROME is None, reason="chrome is not installed")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def await_http(url: str, *, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with contextlib.suppress(urllib.error.URLError, OSError):
            urllib.request.urlopen(url, timeout=1).read()
            return
        time.sleep(0.2)
    raise TimeoutError(f"{url} never came up")


@contextlib.contextmanager
def spawned(command: list[str]) -> Iterator[subprocess.Popen]:
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        yield process
    finally:
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=10)


def test_every_asset_the_page_asks_for_is_packaged():
    """Referenced, on disk, and declared as package data — all three.

    The wheel used to contain Python files and nothing else: no arena, no
    corpus.yaml. The container hid it, because it runs from /app with praman/
    copied alongside, so the source tree wins on sys.path and the install only
    ever supplied dependencies. A `pip install praman` 404s every asset, and
    nothing said so.
    """
    import re
    import tomllib
    from fnmatch import fnmatch

    from praman.api.main import STATIC_DIR

    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    referenced = set(re.findall(r'(?:href|src)="/static/([^"]+)"', html))
    assert referenced, "index.html references no assets at all"

    # The vendored fonts.css pulls the woff2 files in turn.
    fonts = (STATIC_DIR / "vendor" / "fonts.css").read_text(encoding="utf-8")
    referenced |= {f"vendor/{u}" for u in re.findall(r"url\(([^)]+)\)", fonts)}

    with (ROOT / "pyproject.toml").open("rb") as fh:
        patterns = tomllib.load(fh)["tool"]["setuptools"]["package-data"]["praman"]

    for asset in sorted(referenced):
        assert (STATIC_DIR / asset).is_file(), f"{asset} is referenced but not on disk"
        declared = f"api/static/{asset}"
        assert any(fnmatch(declared, p) for p in patterns), (
            f"{declared} is served but not in tool.setuptools.package-data"
        )


@needs_node
def test_the_arena_compiles_and_its_helpers_agree_with_the_python():
    result = subprocess.run(
        [NODE, str(FRONTEND / "check.mjs")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    assert result.returncode == 0, f"\n{result.stderr or result.stdout}"


@needs_node
@needs_chrome
def test_the_arenas_controls_do_what_they_say(tmp_path):
    """Click through the page against the committed campaigns.

    Deliberately against `results/` rather than a fixture: the campaigns a
    judge will see are the ones worth proving the rail can reach.
    """
    port, debug_port = free_port(), free_port()

    server = [
        sys.executable, "-m", "uvicorn", "praman.api.main:app",
        "--host", "127.0.0.1", "--port", str(port),
    ]  # fmt: skip
    browser = [
        CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
        f"--remote-debugging-port={debug_port}",
        f"--user-data-dir={tmp_path / 'chrome'}", "about:blank",
    ]  # fmt: skip

    with spawned(server), spawned(browser):
        await_http(f"http://127.0.0.1:{port}/api/health")
        await_http(f"http://127.0.0.1:{debug_port}/json/version")

        with urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json/version") as response:
            import json

            debugger = json.load(response)["webSocketDebuggerUrl"]

        result = subprocess.run(
            [NODE, str(FRONTEND / "drive.mjs"), debugger, f"http://127.0.0.1:{port}/"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=ROOT,
            timeout=180,
        )

    assert result.returncode == 0, f"\n{result.stdout}{result.stderr}"
