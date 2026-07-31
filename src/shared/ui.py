"""
CPMIS Toolkit — shared Rich UI helpers.

Single `console` instance used by every module. Import the helpers you need:

    from shared.ui import console, section, ok, warn, err, spinner, ...
"""

import sys
from rich.console import Console
from rich.table import Table
from rich.progress import (
    Progress, SpinnerColumn, TextColumn,
    BarColumn, MofNCompleteColumn, TimeElapsedColumn,
)
from rich import box

# ── Shared console ─────────────────────────────────────────────────────────────
console = Console(highlight=False, soft_wrap=True)

# ── Palette ────────────────────────────────────────────────────────────────────
_PRI  = "cyan"
_DIM  = "dim"
_OK   = "bold green"
_WARN = "bold yellow"
_ERR  = "bold red"


# ── Layout ────────────────────────────────────────────────────────────────────

def header(title: str, subtitle: str = ""):
    """Full-width rule with app title and optional subtitle."""
    console.print()
    console.rule(f"[bold {_PRI}]{title}[/bold {_PRI}]", style=f"{_PRI} dim")
    if subtitle:
        console.print(f"  [{_DIM}]{subtitle}[/{_DIM}]")
    console.print()


def section(title: str):
    """Thin section divider with centred title."""
    console.print()
    console.rule(f"[bold]{title}[/bold]", style=f"{_PRI} dim")
    console.print()


def blank():
    console.print()


# ── Status ────────────────────────────────────────────────────────────────────

def ok(msg: str):
    console.print(f"  [{_OK}]✓[/{_OK}]  {msg}")


def warn(msg: str):
    console.print(f"  [{_WARN}]⚠[/{_WARN}]  {msg}")


def err(msg: str):
    console.print(f"  [{_ERR}]✗[/{_ERR}]  {msg}")


def info(msg: str, indent: int = 2):
    console.print(" " * indent + msg)


def bullet(msg: str, style: str = ""):
    styled = f"[{style}]{msg}[/{style}]" if style else msg
    console.print(f"    [{_PRI}]·[/{_PRI}]  {styled}")


# ── Menu ──────────────────────────────────────────────────────────────────────

def menu_item(key: str, label: str, desc: str = ""):
    row = f"  [bold {_PRI}]{key}[/bold {_PRI}]  [bold]{label}[/bold]"
    if desc:
        row += f"  [{_DIM}]{desc}[/{_DIM}]"
    console.print(row)


# ── Prompts ───────────────────────────────────────────────────────────────────

def ask(prompt_text: str, default: str = "") -> str:
    """Styled prompt — returns stripped input string."""
    hint = f" [{_DIM}][{default}][/{_DIM}]" if default else ""
    console.print(f"\n  [{_PRI}]›[/{_PRI}]  {prompt_text}{hint}  ", end="")
    sys.stdout.flush()
    return input().strip()


# ── Tables ────────────────────────────────────────────────────────────────────

def file_table(files: list) -> None:
    """Table of files: index, basename, size, modified date."""
    import os
    from datetime import datetime as _dt

    t = Table(box=box.SIMPLE_HEAD, show_header=True,
              header_style=f"bold {_PRI}", padding=(0, 1), min_width=60)
    t.add_column("#",        style=_DIM,  width=4,  justify="right")
    t.add_column("File",                  min_width=44)
    t.add_column("Size",     style=_DIM,  width=8,  justify="right")
    t.add_column("Modified", style=_DIM,  width=18)

    for i, f in enumerate(files, 1):
        sz  = f"{os.path.getsize(f) // 1024} KB"
        mdt = _dt.fromtimestamp(os.path.getmtime(f)).strftime("%d %b %Y  %H:%M")
        t.add_row(str(i), os.path.basename(f), sz, mdt)

    console.print(t)


def kv_table(rows: list) -> None:
    """Two-column key / value summary table."""
    t = Table(box=box.SIMPLE_HEAD, show_header=False, padding=(0, 2))
    t.add_column(style=_DIM)
    t.add_column(style="bold")
    for label, value in rows:
        t.add_row(str(label), str(value))
    console.print(t)


# ── Progress ──────────────────────────────────────────────────────────────────

def spinner(msg: str):
    """Context manager — dots spinner while a blocking operation runs."""
    return console.status(f"  [{_DIM}]{msg}[/{_DIM}]",
                          spinner="dots", spinner_style=_PRI)


def make_progress() -> Progress:
    """Rich Progress bar for multi-item loops (non-transient)."""
    return Progress(
        SpinnerColumn(style=_PRI),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(style=f"{_PRI} dim", complete_style=_PRI),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )
