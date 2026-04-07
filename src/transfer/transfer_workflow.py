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
    print("\n  ── Enrollment Year Range ──")
    print("  Enter the year range to filter TEIs by enrollment date.")
    print("  Only TEIs enrolled within this range will be considered.\n")

    while True:
        start = input("  Start year (e.g. 2024): ").strip()
        try:
            year_start = int(start)
            if 2000 <= year_start <= 2100:
                break
            print("  ⚠️  Enter a reasonable year (2000-2100).")
        except ValueError:
            print("  ⚠️  Enter a valid year number.")

    while True:
        end = input(f"  End year (e.g. 2026) [{year_start}]: ").strip() or str(year_start)
        try:
            year_end = int(end)
            if year_end >= year_start:
                break
            print(f"  ⚠️  End year must be >= {year_start}.")
        except ValueError:
            print("  ⚠️  Enter a valid year number.")

    print(f"  ✅ Year range: {year_start} to {year_end}")
    return year_start, year_end


def run_interactive():
    """Run the full interactive transfer workflow."""
    print("\n" + "=" * 80)
    print("  OU TRANSFER — Move TEIs Between Organisation Units")
    print("=" * 80)
    print(f"  Server: {DHIS2_URL}")
    print(f"  ⚠️  Read-only until you confirm the transfer.\n")

    # ── Step 1: Load org unit codes ──
    print("  📂 Loading org unit codes from Phase 1...", end='', flush=True)
    ou_list, ou_map = load_ou_codes()
    if not ou_list:
        print("\n  ❌ No org unit codes found. Run Phase 1 first: just task1-complete")
        sys.exit(1)
    print(f" ✅ {len(ou_list)} org units loaded")

    # ── Step 2: Select source org unit ──
    print(f"\n  {'─' * 70}")
    print(f"  STEP 1: SELECT SOURCE ORG UNIT (where data was incorrectly entered)")
    print(f"  {'─' * 70}")
    source_uid, source_name = search_and_pick_ou(ou_list, "Search SOURCE org unit (facility)")
    if source_uid == 'done':
        print("  ❌ Cancelled.")
        sys.exit(0)
    source_info = ou_map.get(source_uid, {})
    source_code = source_info.get('code', '?')

    # ── Step 3: Select destination org unit ──
    print(f"\n  {'─' * 70}")
    print(f"  STEP 2: SELECT DESTINATION ORG UNIT (correct location)")
    print(f"  {'─' * 70}")
    dest_uid, dest_name = search_and_pick_ou(ou_list, "Search DESTINATION org unit (TA)")
    if dest_uid == 'done':
        print("  ❌ Cancelled.")
        sys.exit(0)
    dest_info = ou_map.get(dest_uid, {})
    dest_code = dest_info.get('code', '?')

    if source_uid == dest_uid:
        print("  ❌ Source and destination are the same. Aborting.")
        sys.exit(1)

    # ── Step 4: Year range ──
    print(f"\n  {'─' * 70}")
    print(f"  STEP 3: ENROLLMENT YEAR RANGE")
    print(f"  {'─' * 70}")
    year_start, year_end = interactive_year_range()

    # ── Show configuration ──
    print(f"\n  {'═' * 70}")
    print(f"  TRANSFER CONFIGURATION")
    print(f"  {'═' * 70}")
    print(f"  Source:       {source_name} ({source_uid})")
    print(f"  Source code:  {source_code}")
    print(f"  Destination:  {dest_name} ({dest_uid})")
    print(f"  Dest code:    {dest_code}")
    print(f"  Year range:   {year_start}-{year_end}")
    print(f"  {'═' * 70}")

    confirm = input("\n  Proceed with fetching TEIs? (yes/no): ").strip().lower()
    if confirm not in ('yes', 'y'):
        print("  ❌ Cancelled.")
        sys.exit(0)

    # ── Step 5: Fetch TEIs ──
    print(f"\n  {'─' * 70}")
    print(f"  STEP 4: FETCHING TEIs")
    print(f"  {'─' * 70}")

    household_teis = fetch_teis_full(source_uid, 'household', year_start, year_end)
    child_teis = fetch_teis_full(source_uid, 'harmonized', year_start, year_end)

    if not household_teis and not child_teis:
        print(f"\n  ⚠️  No TEIs found at {source_name} for {year_start}-{year_end}.")
        print("  Nothing to transfer.")
        sys.exit(0)

    # ── Step 6: Build relationship graph ──
    print(f"\n  🔗 Building relationship graph...")
    hh_to_children, child_to_hh = build_relationship_graph(household_teis, child_teis)
    linked_count = sum(len(v) for v in hh_to_children.values())
    print(f"  ✅ {linked_count} household-child links found")

    # ── Step 7: Display summary ──
    display_tei_summary(household_teis, child_teis, hh_to_children, child_to_hh)

    # ── Step 8: Select TEIs to keep ──
    print(f"\n  {'─' * 70}")
    print(f"  STEP 5: SELECT TEIs TO KEEP AT SOURCE")
    print(f"  {'─' * 70}")

    all_teis = household_teis + child_teis
    keep_uids = interactive_select_keep(household_teis, child_teis, hh_to_children, child_to_hh)

    if keep_uids is None:
        print("  ❌ Cancelled.")
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

    print(f"\n  📊 Transfer Summary:")
    print(f"     Keeping at source:   {len(keep_teis)} TEIs")
    print(f"     Transferring:        {len(transfer_teis)} TEIs")
    print(f"     Events to move:      {total_transfer_events}")

    if not transfer_teis:
        print("  ℹ️  No TEIs to transfer. All selected to keep.")
        sys.exit(0)

    # ── Step 9: Generate new IDs ──
    print(f"\n  {'─' * 70}")
    print(f"  STEP 6: GENERATING NEW IDs FOR DESTINATION")
    print(f"  {'─' * 70}")

    id_mappings = generate_transfer_ids(transfer_teis, dest_code, dest_uid)

    print(f"\n  📋 ID Mapping Preview:")
    print(f"  {'Old ID':<35} → {'New ID':<35}")
    print(f"  {'─' * 75}")
    for m in id_mappings[:15]:
        old = m['old_id'] or '(empty)'
        print(f"  {old:<35} → {m['new_id']:<35}")
    if len(id_mappings) > 15:
        print(f"  ... and {len(id_mappings) - 15} more")

    # ── Step 10: Save preview ──
    preview_file = save_transfer_preview(transfer_teis, dest_uid, dest_name, OUTPUT_DIR)

    # ── Step 11: Confirm and execute ──
    print(f"\n  {'═' * 70}")
    print(f"  READY TO TRANSFER")
    print(f"  {'═' * 70}")
    print(f"  TEIs:          {len(transfer_teis)}")
    print(f"  Events:        {total_transfer_events}")
    print(f"  From:          {source_name}")
    print(f"  To:            {dest_name}")
    print(f"  Preview CSV:   {preview_file}")
    print(f"  {'═' * 70}")
    print(f"\n  ⚠️  This will MODIFY data on the live DHIS2 server.")
    print(f"  ⚠️  TEIs, enrollments, and ALL events will be moved.")

    confirm = input("\n  Execute transfer? (yes/no): ").strip().lower()
    if confirm not in ('yes', 'y'):
        print(f"\n  ❌ Cancelled. No changes made.")
        print(f"  Preview saved at: {preview_file}")
        sys.exit(0)

    # ── Step 12: Execute transfer ──
    print(f"\n  {'─' * 70}")
    print(f"  STEP 7: EXECUTING TRANSFER")
    print(f"  {'─' * 70}")

    success, errors_count, log_file = execute_transfer(
        transfer_teis, dest_uid, id_mappings, OUTPUT_DIR
    )

    # ── Step 13: Verify ──
    if success > 0:
        print(f"\n  {'─' * 70}")
        print(f"  STEP 8: VERIFYING TRANSFER")
        print(f"  {'─' * 70}")

        verify_transfer(
            transfer_teis, id_mappings, dest_uid, hh_to_children, child_to_hh
        )

    # ── Final summary ──
    print(f"\n{'=' * 80}")
    print(f"  ✅ OU TRANSFER WORKFLOW COMPLETE")
    print(f"{'=' * 80}")
    print(f"  Source:        {source_name}")
    print(f"  Destination:   {dest_name}")
    print(f"  Transferred:   {success} TEIs")
    print(f"  Errors:        {errors_count}")
    print(f"  Transfer log:  {log_file}")
    print(f"  Preview:       {preview_file}")
    print(f"{'=' * 80}\n")


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
