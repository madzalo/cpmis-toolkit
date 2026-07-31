"""
Shared interactive organisation unit picker for CPMIS Toolkit.
Extracted from cleanup Phase 2 for cross-app reuse.
"""
import csv
import os

from shared.ui import console, section, ok, warn, err, ask, blank
from rich.table import Table


def load_ou_codes(csv_file='outputs/task1/ou_codes_standardized.csv'):
    """
    Load org unit codes from Phase 1 CSV.

    Returns:
        (ou_list, ou_map) where:
            ou_list: list of dicts with uid, name, code, level
            ou_map: dict of uid -> dict
    """
    ou_list = []
    ou_map = {}

    if not os.path.exists(csv_file):
        err(f"CSV file not found: {csv_file}")
        console.print("     Run Phase 1 first: just task1-complete")
        return ou_list, ou_map

    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            entry = {
                'uid': row['dhis2_uid'],
                'name': row['ou_name'],
                'code': row['standardised_code'],
                'level': int(row.get('ou_level', 0)),
            }
            ou_list.append(entry)
            ou_map[entry['uid']] = entry

    return ou_list, ou_map


# ─── Helpers ────────────────────────────────────────────────────────────────

def _level_label(level):
    return {3: "District", 4: "TA", 5: "Facility"}.get(level, f"L{level}")


def _ou_table(items):
    """Build a Rich table for a list of OUs."""
    t = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 2))
    t.add_column("#", style="dim", width=4, no_wrap=True)
    t.add_column("Name", width=42)
    t.add_column("Type", style="dim", width=10)
    t.add_column("Code", style="green")
    for i, ou in enumerate(items, 1):
        t.add_row(str(i), ou['name'], _level_label(ou['level']), ou['code'])
    return t


def _pick_from_list(items, prompt):
    """Show table and let user pick one item. Returns OU dict or None (go back)."""
    console.print(_ou_table(items))
    while True:
        raw = ask(f"{prompt} (1–{len(items)})  or  [dim]Enter[/dim] to go back").strip()
        if not raw:
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return items[int(raw) - 1]
        warn("Enter a valid number, or press Enter to go back.")


# ─── Search mode ────────────────────────────────────────────────────────────

def _search_mode(ou_list):
    """Search by name or code across all levels."""
    while True:
        query = ask("🔍 Name or code").strip().lower()
        if not query:
            return None  # back to main menu

        matches = [o for o in ou_list
                   if query in o['name'].lower() or query in o['code'].lower()]

        if not matches:
            warn(f"No matches for '{query}'. Try again or press Enter to go back.")
            continue

        display = matches[:25]
        console.print(f"\n  Found [bold]{len(matches)}[/bold] match(es)"
                      + (f" [dim](showing first 25)[/dim]" if len(matches) > 25 else "") + ":")
        sel = _pick_from_list(display, "Pick")
        if sel:
            ok(f"Selected: {sel['name']}  ({_level_label(sel['level'])})  —  {sel['code']}")
            return sel['uid'], sel['name']
        # else: loop — search again


# ─── Browse mode: District → TA → optional Facility ─────────────────────────

def _browse_mode(ou_list, districts):
    """Browse District → TA → (optionally) Facility."""

    # Step 1 — District
    section("Browse — Select District")
    dist_items = sorted(districts, key=lambda x: x['name'])
    dist = _pick_from_list(dist_items, "District")
    if not dist:
        return None  # back

    # Step 2 — TA within district
    tas = sorted(
        [o for o in ou_list
         if o['level'] == 4 and o['code'].upper().startswith(dist['code'].upper() + '_')],
        key=lambda x: x['name']
    )
    if not tas:
        warn(f"No TAs found under {dist['name']}.")
        return None

    section(f"Select TA — {dist['name']}")
    ta = _pick_from_list(tas, "TA")
    if not ta:
        return None  # back to district

    # Step 3 — Use TA or drill into its facilities
    facilities = sorted(
        [o for o in ou_list
         if o['level'] == 5 and o['code'].upper().startswith(ta['code'].upper() + '_')],
        key=lambda x: x['name']
    )

    if facilities:
        console.print(f"\n  [dim]{len(facilities)} facilities under {ta['name']}[/dim]")
        choice = ask("[bold]t[/bold]=use this TA  /  [bold]f[/bold]=browse facilities").strip().lower()
        if choice == 'f':
            section(f"Select Facility — {ta['name']}")
            fac = _pick_from_list(facilities, "Facility")
            if fac:
                ok(f"Selected: {fac['name']}  (Facility)  —  {fac['code']}")
                return fac['uid'], fac['name']
            # fell back — use TA instead

    ok(f"Selected: {ta['name']}  (TA)  —  {ta['code']}")
    return ta['uid'], ta['name']


# ─── Public API ─────────────────────────────────────────────────────────────

def search_and_pick_ou(ou_list, prompt_label="Select org unit"):
    """
    Enhanced interactive org unit picker.

    Supports:
      1. Search by name or code (any level)
      2. Browse  District → TA → Facility

    Works for selecting TAs, facilities, or districts as source/destination.
    Returns (uid, name) or ('done', 'done') to cancel.
    """
    districts = [o for o in ou_list if o['level'] == 3]

    while True:
        console.print(f"\n  [bold]{prompt_label}[/bold]")
        console.print("    [dim]1[/dim]  Search by name or code")
        console.print("    [dim]2[/dim]  Browse  District → TA → Facility")
        console.print("    [dim]q[/dim]  Cancel")
        blank()

        mode = ask("Choose").strip().lower()
        if mode in ('q', 'done', 'cancel'):
            return 'done', 'done'
        elif mode == '1':
            result = _search_mode(ou_list)
        elif mode == '2':
            result = _browse_mode(ou_list, districts)
        else:
            warn("Enter 1, 2, or q.")
            continue

        if result:
            return result
        # None → user went back, show menu again


def interactive_pick_program():
    """Let the user pick which program to process."""
    section("Select Program")
    console.print("    [dim]1[/dim]  Household — CPMIS")
    console.print("    [dim]2[/dim]  MW Harmonized OVC Program — CPMIS")
    console.print("    [dim]3[/dim]  Both")

    while True:
        choice = ask("Pick a program (1–3) [3]").strip() or '3'
        if choice == '1':
            return 'household'
        elif choice == '2':
            return 'harmonized'
        elif choice == '3':
            return 'both'
        warn("Enter 1, 2, or 3.")
