#!/usr/bin/env python3
"""
OU Transfer Workflow — Interactive CLI for transferring TEIs between org units.

This is the main entry point for the OU Transfer App. It guides you through:
1. Selecting source and destination org units
2. Specifying enrollment year range
3. Fetching TEIs with full enrollments and events
4. Selecting which TEIs to keep at source
5. Generating new IDs for destination
6. Previewing the transfer
7. Executing the transfer
8. Verifying the results

Usage:
    python transfer_workflow.py              # Interactive mode (recommended)
    python transfer_workflow.py --verify     # Re-run verification on last transfer
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.dhis2_client import DHIS2_URL
from shared.ui import console, header, section, ok, warn, err, ask, blank
from rich.table import Table
from shared.ou_picker import load_ou_codes, search_and_pick_ou
from shared.id_utils import PROGRAMS

from transfer.fetcher import (
    fetch_teis_full, build_relationship_graph, resolve_transfer_set
)
from transfer.selector import (
    display_tei_summary, interactive_select_keep, save_transfer_preview
)
from transfer.id_generator import generate_transfer_ids
from transfer.engine import execute_transfer
from transfer.verifier import verify_transfer


OUTPUT_DIR = 'outputs/transfer'


def interactive_year_range():
    """Prompt the user for an enrollment year range."""
    section("Enrollment Year Range")
    console.print("  Filter TEIs by enrollment date.\n")

    while True:
        start = ask("Start year (e.g. 2024)").strip()
        try:
            year_start = int(start)
            if 2000 <= year_start <= 2100:
                break
            warn("Enter a reasonable year (2000-2100).")
        except ValueError:
            warn("Enter a valid year number.")

    while True:
        end = ask(f"End year (e.g. 2026) [{year_start}]").strip() or str(year_start)
        try:
            year_end = int(end)
            if year_end >= year_start:
                break
            warn(f"End year must be >= {year_start}.")
        except ValueError:
            warn("Enter a valid year number.")

    ok(f"Year range: {year_start} – {year_end}")
    return year_start, year_end


def run_interactive():
    """Run the full interactive transfer workflow."""
    header("Transfer TEIs", f"DHIS2 · {DHIS2_URL}")
    warn("Read-only until you confirm the transfer.")
    blank()

    console.print("  📂 Loading org unit codes from Phase 1...", end="", highlight=False)
    ou_list, ou_map = load_ou_codes()
    if not ou_list:
        err("No org unit codes found. Run Phase 1 first: just task1-complete")
        sys.exit(1)
    console.print(f" ✅ {len(ou_list)} org units loaded")

    section("Step 1 — Source Org Unit (where data was incorrectly entered)")
    source_uid, source_name = search_and_pick_ou(ou_list, "Search SOURCE org unit (facility)")
    if source_uid == 'done':
        err("Cancelled.")
        sys.exit(0)
    source_info = ou_map.get(source_uid, {})
    source_code = source_info.get('code', '?')

    section("Step 2 — Destination Org Unit (correct location)")
    dest_uid, dest_name = search_and_pick_ou(ou_list, "Search DESTINATION org unit (TA)")
    if dest_uid == 'done':
        err("Cancelled.")
        sys.exit(0)
    dest_info = ou_map.get(dest_uid, {})
    dest_code = dest_info.get('code', '?')

    if source_uid == dest_uid:
        err("Source and destination are the same. Aborting.")
        sys.exit(1)

    section("Step 3 — Enrollment Year Range")
    year_start, year_end = interactive_year_range()

    section("Transfer Configuration")
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_row("Source",      f"[cyan]{source_name}[/cyan] [dim]({source_uid})[/dim]")
    t.add_row("Source code", f"[green]{source_code}[/green]")
    t.add_row("Destination", f"[cyan]{dest_name}[/cyan] [dim]({dest_uid})[/dim]")
    t.add_row("Dest code",   f"[green]{dest_code}[/green]")
    t.add_row("Year range",  f"[bold]{year_start} – {year_end}[/bold]")
    console.print(t)
    blank()

    confirm = ask("Proceed with fetching TEIs? (yes/no)").strip().lower()
    if confirm not in ('yes', 'y'):
        err("Cancelled.")
        sys.exit(0)

    section("Step 4 — Fetching TEIs")
    household_teis = fetch_teis_full(source_uid, 'household', year_start, year_end)
    child_teis = fetch_teis_full(source_uid, 'harmonized', year_start, year_end)

    if not household_teis and not child_teis:
        warn(f"No TEIs found at {source_name} for {year_start}-{year_end}. Nothing to transfer.")
        sys.exit(0)

    console.print("  🔗 Building relationship graph...", end="", highlight=False)
    hh_to_children, child_to_hh = build_relationship_graph(household_teis, child_teis)
    linked_count = sum(len(v) for v in hh_to_children.values())
    console.print(f" ✅ {linked_count} household-child links found")

    # ── Step 7: Display summary ──
    display_tei_summary(household_teis, child_teis, hh_to_children, child_to_hh)

    section("Step 5 — Select TEIs to Keep at Source")

    all_teis = household_teis + child_teis
    keep_uids = interactive_select_keep(household_teis, child_teis, hh_to_children, child_to_hh)

    if keep_uids is None:
        err("Cancelled.")
        sys.exit(0)

    # Resolve full transfer set with relationship preservation
    keep_set, transfer_set = resolve_transfer_set(
        keep_uids, all_teis, hh_to_children, child_to_hh
    )

    transfer_teis = [t for t in all_teis if t['trackedEntityInstance'] in transfer_set]
    keep_teis = [t for t in all_teis if t['trackedEntityInstance'] in keep_set]

    total_transfer_events = sum(
        len(ev)
        for tei in transfer_teis
        for enr in tei.get('enrollments', [])
        for ev in [enr.get('events', [])]
    )

    section("Transfer Summary")
    ts = Table(show_header=False, box=None, padding=(0, 2))
    ts.add_row("Keeping at source", f"[dim]{len(keep_teis)} TEIs[/dim]")
    ts.add_row("Transferring",      f"[bold]{len(transfer_teis)} TEIs[/bold]")
    ts.add_row("Events to move",    f"[bold]{total_transfer_events}[/bold]")
    console.print(ts)

    if not transfer_teis:
        warn("No TEIs to transfer. All selected to keep.")
        sys.exit(0)

    section("Step 6 — Generating New IDs for Destination")

    id_mappings = generate_transfer_ids(transfer_teis, dest_code, dest_uid)

    id_tbl = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 2))
    id_tbl.add_column("Old ID", style="dim", width=36)
    id_tbl.add_column("→", width=3)
    id_tbl.add_column("New ID", style="green")
    for m in id_mappings[:15]:
        id_tbl.add_row(m['old_id'] or '(empty)', "→", m['new_id'])
    if len(id_mappings) > 15:
        id_tbl.add_row(f"[dim]... and {len(id_mappings) - 15} more[/dim]", "", "")
    console.print(id_tbl)

    # ── Step 10: Save preview ──
    preview_file = save_transfer_preview(transfer_teis, dest_uid, dest_name, OUTPUT_DIR)

    section("Ready to Transfer")
    rt = Table(show_header=False, box=None, padding=(0, 2))
    rt.add_row("TEIs",        f"[bold]{len(transfer_teis)}[/bold]")
    rt.add_row("Events",      f"[bold]{total_transfer_events}[/bold]")
    rt.add_row("From",        f"[cyan]{source_name}[/cyan]")
    rt.add_row("To",          f"[cyan]{dest_name}[/cyan]")
    rt.add_row("Preview CSV", f"[dim]{preview_file}[/dim]")
    console.print(rt)
    blank()
    warn("This will MODIFY data on the live DHIS2 server.")
    warn("TEIs, enrollments, and ALL events will be moved.")

    confirm = ask("Execute transfer? (yes/no)").strip().lower()
    if confirm not in ('yes', 'y'):
        err("Cancelled. No changes made.")
        console.print(f"  Preview saved at: [dim]{preview_file}[/dim]")
        sys.exit(0)

    section("Step 7 — Executing Transfer")

    success, errors_count, log_file = execute_transfer(
        transfer_teis, dest_uid, id_mappings, OUTPUT_DIR, dest_ou_code=dest_code
    )

    if success > 0:
        section("Step 8 — Verifying Transfer")

        verify_transfer(
            transfer_teis, id_mappings, dest_uid, hh_to_children, child_to_hh
        )

    section("Transfer Complete")
    fs = Table(show_header=False, box=None, padding=(0, 2))
    fs.add_row("Source",       f"[cyan]{source_name}[/cyan]")
    fs.add_row("Destination",  f"[cyan]{dest_name}[/cyan]")
    fs.add_row("Transferred",  f"[bold green]{success} TEIs[/bold green]")
    fs.add_row("Errors",       f"[{'red' if errors_count else 'green'}]{errors_count}[/{'red' if errors_count else 'green'}]")
    fs.add_row("Transfer log", f"[dim]{log_file}[/dim]")
    fs.add_row("Preview",      f"[dim]{preview_file}[/dim]")
    console.print(fs)
    blank()


def main():
    parser = argparse.ArgumentParser(
        description='OU Transfer — Move TEIs between organisation units'
    )
    parser.add_argument(
        '--verify', action='store_true',
        help='Re-run verification on the last transfer'
    )

    args = parser.parse_args()

    if args.verify:
        print("  ℹ️  Verification re-run not yet implemented.")
        print("  Run the full workflow instead: just transfer")
        sys.exit(0)

    run_interactive()


if __name__ == '__main__':
    main()
