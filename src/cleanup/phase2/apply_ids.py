#!/usr/bin/env python3
"""
Apply generated IDs to Tracked Entity Instances in DHIS2.

This script reads the ID mapping CSV and applies changes using bulk POST
(strategy=UPDATE) for maximum performance.

Usage:
    # Apply with default batch size (200)
    python apply_ids.py --csv outputs/phase2/id_mapping_th.csv

    # Apply with custom batch size
    python apply_ids.py --csv outputs/phase2/id_mapping_th.csv --batch-size 100
"""
import sys
import os
import argparse

# Add parent directory to path to import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.settings import DHIS2_URL

# Import the bulk apply function from phase2_workflow
from cleanup.phase2.phase2_workflow import apply_changes




def main():
    parser = argparse.ArgumentParser(
        description='Apply generated IDs to DHIS2 via API or direct database update'
    )
    parser.add_argument(
        '--csv',
        required=True,
        help='Path to the ID mapping CSV'
    )
    parser.add_argument(
        '--use-db',
        action='store_true',
        help='Use direct database update (FAST but bypasses DHIS2 validation)'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify database values match expected CSV values (requires --use-db credentials)'
    )
    
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"\n  ❌ Mapping file not found: {args.csv}")
        sys.exit(1)

    # ── Verify mode ──
    if args.verify:
        from cleanup.phase2.db_update import verify_changes
        from cleanup.phase2.phase2_workflow import PROGRAMS
        program_attributes = {
            'household': PROGRAMS['household']['id_attribute'],
            'harmonized': PROGRAMS['harmonized']['id_attribute'],
        }
        verify_changes(args.csv, program_attributes)
        sys.exit(0)

    # ── Apply mode ──
    method = "DATABASE UPDATE" if args.use_db else "API (ASYNC)"
    print(f"\n{'=' * 80}")
    print(f"  APPLY STANDARDISED IDs TO DHIS2 ({method})")
    print(f"{'=' * 80}")
    print(f"  Server: {DHIS2_URL}")
    print(f"  CSV: {args.csv}")
    print(f"  Method: {method}")
    
    # Confirmation
    if args.use_db:
        print(f"\n  ⚠️  WARNING: Direct database update bypasses DHIS2 validation!")
        print(f"  ⚠️  Ensure you have a database backup before proceeding!")
    else:
        print(f"\n  ⚠️  WARNING: This will MODIFY data on the live DHIS2 server!")
    confirm = input(f"  Continue? (yes/no): ")
    if confirm.lower() not in ['yes', 'y']:
        print(f"\n  ❌ Cancelled. No changes made.")
        sys.exit(0)
    
    # Call the apply function from phase2_workflow
    success, errors = apply_changes(args.csv, use_db=args.use_db)
    
    print(f"\n{'=' * 80}")
    print(f"  ✅ COMPLETE")
    print(f"{'=' * 80}\n")
    
    sys.exit(1 if errors > 0 else 0)


if __name__ == '__main__':
    main()
