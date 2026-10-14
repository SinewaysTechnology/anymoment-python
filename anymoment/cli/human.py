"""Terminal formatting that stays plain when color is turned off."""

import os
import sys

import click


def color_enabled() -> bool:
    """Color only on a terminal, and never when NO_COLOR is set."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("ANYMOMENT_COLOR", "").lower() in {"0", "false", "no"}:
        return False
    return sys.stdout.isatty()


def paint(text: str, **style) -> str:
    if not color_enabled():
        return text
    return click.style(text, **style)


def render_table(rows: list[dict]) -> bool:
    """Draw a table when the terminal can show color. Return False to use plain text."""
    if not color_enabled() or not rows:
        return False
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        return False
    columns = []
    for row in rows:
        for key in row:
            if key not in columns and not isinstance(row[key], (dict, list)):
                columns.append(key)
    columns = columns[:6]
    table = Table(show_header=True, header_style="bold")
    for column in columns:
        table.add_column(column.replace("_", " "))
    for row in rows:
        table.add_row(*["" if row.get(column) is None else str(row.get(column)) for column in columns])
    Console().print(table)
    return True
