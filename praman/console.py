"""UTF-8 terminal output.

Praman prints `₹` in nearly every line it produces, and Windows consoles
default to cp1252, which cannot encode it — the process dies with
UnicodeEncodeError partway through a demo. Call `setup()` before printing.

`errors="replace"` rather than strict: on a terminal that genuinely cannot
render the glyph we would rather show a placeholder than lose the run.
"""

from __future__ import annotations

import contextlib
import sys

__all__ = ["setup"]

_done = False


def setup() -> None:
    global _done
    if _done:
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")
    _done = True
