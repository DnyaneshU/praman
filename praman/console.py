"""UTF-8 terminal output, and the report furniture every command shares.

Praman prints `₹` in nearly every line it produces, and Windows consoles
default to cp1252, which cannot encode it — the process dies with
UnicodeEncodeError partway through a demo. Call `setup()` before printing.

`errors="replace"` rather than strict: on a terminal that genuinely cannot
render the glyph we would rather show a placeholder than lose the run.

The rest of this module is the layout that eleven commands were each
reimplementing. Every one of them opened with a rule, a `PRAMAN · TITLE` line
and another rule; drew tables; and closed with a labelled block of figures. The
table was the part worth fixing:

    print(f"  {'attack':<7} {'name':<32} {'ASR':>6}")
    print(f"  {'-' * 7} {'-' * 32} {'-' * 6}")

Those widths are the same three numbers typed twice, and nothing keeps them in
step — widen a column and the rule beneath it silently stops matching, which is
how `tiers_study` came to print a 13-wide heading over a 12-wide column. Here a
`Table` owns its columns and derives its own rule, so that cannot happen.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterable

__all__ = ["setup", "rule", "banner", "Table", "Column", "field", "summary", "divider", "WIDTH"]

#: `(heading, width)` or `(heading, width, alignment)`, alignment being a
#: format-spec character — `<` by default, `>` for anything numeric.
Column = tuple[str, int] | tuple[str, int, str]

BRAND = "PRAMAN"

#: Report width. Reports were 68, 76 and 78 columns wide depending on which
#: file you opened; one number means consecutive commands in a terminal line up.
WIDTH = 78

#: Every report indents its body by this much under the full-width banner.
INDENT = 2

#: Label column in a summary block, wide enough for "benign pass rate".
LABEL = 21

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


def rule(width: int = WIDTH) -> str:
    return "─" * width


def banner(title: str, *facts: str, note: str | None = None, width: int = WIDTH) -> None:
    """The three-line heading every command opens with.

    `facts` are the run's coordinates — profile, seed, control — which belong on
    the title line because they qualify every number underneath it. A report
    that does not say which seed produced it cannot be checked against a re-run.
    """
    bar = rule(width)
    print(bar)
    print("  ·  ".join((BRAND, title, *facts)))
    if note:
        print(f"{' ' * (len(BRAND) + 5)}{note}")
    print(bar)


def divider(width: int = WIDTH - INDENT, *, indent: int = INDENT) -> None:
    """The light rule that separates a table from the figures that summarise it."""
    print(f"\n{' ' * indent}{'-' * width}")


def field(label: str, value: object, *, width: int = LABEL, indent: int = INDENT) -> None:
    """One `label   value` line. A blank label continues the line above it."""
    print(f"{' ' * indent}{label:<{width}}{value}")


def summary(
    rows: Iterable[tuple[str, object]], *, width: int = LABEL, indent: int = INDENT
) -> None:
    """A divider and the closing figures of a report.

    Pass `("", "…")` for a continuation line: it aligns under the value above
    without repeating the label, which is how the latency note explains itself.
    """
    divider(indent=indent)
    for label, value in rows:
        field(label, value, width=width, indent=indent)


class Table:
    """A fixed-width table that derives its own rule from its columns.

    The heading row, the rule and every data row are laid out from one
    declaration, so a column cannot be widened in one place and not the other.
    Rows are zipped strictly: a row with the wrong number of cells raises
    rather than silently truncating.
    """

    __slots__ = ("_columns", "_indent", "_gap")

    def __init__(self, *columns: Column, indent: int = INDENT, gap: int = 1) -> None:
        self._columns = [(c[0], c[1], c[2] if len(c) > 2 else "<") for c in columns]
        self._indent = " " * indent
        self._gap = " " * gap

    def head(self) -> None:
        print(self._line([name for name, _, _ in self._columns]))
        print(self._line(["-" * width for _, width, _ in self._columns]))

    def row(self, *cells: object) -> None:
        print(self._line(cells))

    def _line(self, cells: Iterable[object]) -> str:
        return self._indent + self._gap.join(
            f"{cell!s:{align}{width}}"
            for cell, (_, width, align) in zip(cells, self._columns, strict=True)
        )
