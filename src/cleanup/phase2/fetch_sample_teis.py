#!/usr/bin/env python3
"""
Fetch sample Tracked Entity Instances (TEIs) from specified DHIS2 programs.
This is a READ-ONLY script - no data is modified.

Supports interactive mode where user can search and pick org units.
"""
import requests
import json
import csv
import sys
import os
import argparse

# Add parent directory to path to import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.settings import DHIS2_URL, DHIS2_USERNAME, DHIS2_PASSWORD


# Program IDs
PROGRAMS = {
    'household': {
        'id': 'lTaqt0loQak',
        'name': 'Household - CPMIS'
    },
    'harmonized': {
        'id': 'xhzwCCKzFBM',
        'name': 'MW Harmonized OVC Program - CPMIS'
    }
}


def load_ou_codes(csv_file='outputs/task1/ou_codes_standardized.csv'):
    """Load org unit codes from Phase 1 CSV for search."""
    ous = []
    try:
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ous.append({
                    'uid': row['dhis2_uid'],
                    'name': row['ou_name'],
                    'code': row['standardised_code'],
                    'level': int(row.get('level', 0))
                })
    except FileNotFoundError:
        pass
    return ous


def interactive_pick_org_unit(ou_list):
    """Let the user search and pick an org unit interactively."""
    while True:
        query = input("\n  🔍 Search org unit (name or code, or 'list' for all): ").strip()
        if not query:
            continue
        
        if query.lower() == 'list':
            matches = ou_list
        else:
            matches = [
                ou for ou in ou_list
                if query.lower() in ou['name'].lower() or query.lower() in ou['code'].lower()
            ]
        
        if not matches:
            print(f"  ⚠️  No org units found matching '{query}'. Try again.")
            continue
        
        # Show matches (limit to 20 if too many)
        display = matches[:20]
        print(f"\n  Found {len(matches)} org units" + (f" (showing first 20):" if len(matches) > 20 else ":"))
        for i, ou in enumerate(display, 1):
            print(f"    {i:3d}. {ou['name']:<35} L{ou['level']}  {ou['code']:<12} ({ou['uid']})")
        
        if len(matches) > 20:
            print(f"    ... {len(matches) - 20} more. Narrow your search.")
        
        choice = input(f"\n  Pick a number (1-{len(display)}), or press Enter to search again: ").strip()
        if not choice:
            continue
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(display):
                selected = display[idx]
                print(f"  ✅ Selected: {selected['name']} ({selected['uid']})")
                return selected['uid'], selected['name']
            else:
                print(f"  ⚠️  Invalid number. Try again.")
        except ValueError:
            print(f"  ⚠️  Enter a number. Try again.")


def interactive_pick_program():
    """Let the user pick which program to fetch from."""
    print(f"\n  Programs:")
    print(f"    1. Household - CPMIS")
    print(f"    2. MW Harmonized OVC Program - CPMIS")
    print(f"    3. Both")
    
    while True:
        choice = input(f"\n  Pick a program (1-3) [3]: ").strip() or '3'
        if choice == '1':
            return 'household'
        elif choice == '2':
            return 'harmonized'
        elif choice == '3':
            return 'both'
        else:
            print(f"  ⚠️  Enter 1, 2, or 3.")


def interactive_pick_sample_size():
    """Let the user pick how many TEIs to fetch."""
    while True:
        choice = input(f"  Sample size [10]: ").strip() or '10'
        try:
            size = int(choice)
            if size < 1:
                print(f"  ⚠️  Must be at least 1.")
                continue
            return size
        except ValueError:
            print(f"  ⚠️  Enter a number.")


def fetch_sample_teis(program_key, sample_size=10, ou_id='AI3mavjiuUD', ou_name='Lambulira'):
    """
    Fetch a sample of tracked entity instances from a program.
    
    Args:
        program_key: Key from PROGRAMS dict ('household' or 'harmonized')
        sample_size: Number of TEIs to fetch (default: 10)
        ou_id: Org unit UID to fetch from
        ou_name: Org unit name for display
    
    Returns:
        List of TEI data
    """
    if program_key not in PROGRAMS:
        print(f"❌ Invalid program key: {program_key}")
        print(f"Valid options: {', '.join(PROGRAMS.keys())}")
        sys.exit(1)
    
    program = PROGRAMS[program_key]
    program_id = program['id']
    program_name = program['name']
    
    print(f"Fetching {sample_size} sample TEIs from: {program_name}")
    print(f"Program ID: {program_id}")
    print(f"DHIS2 URL: {DHIS2_URL}")
    print("=" * 80)
    
    print(f"\n✓ Using org unit: {ou_name} ({ou_id})")
    
    # API endpoint for tracked entity instances
    url = f"{DHIS2_URL}/api/trackedEntityInstances.json"
    
    params = {
        'ou': ou_id,
        'program': program_id,
        'fields': '*',
        'pageSize': sample_size,
        'page': 1,
        'totalPages': True
    }
    
    print(f"  Requesting {sample_size} TEIs from DHIS2...", flush=True)
    
    try:
        response = requests.get(
            url,
            params=params,
            auth=(DHIS2_USERNAME, DHIS2_PASSWORD)
        )
        
        if response.status_code == 200:
            data = response.json()
            teis = data.get('trackedEntityInstances', [])
            total = data.get('pager', {}).get('total', 'Unknown')
            
            print(f"  ✅ Fetched {len(teis)} TEIs (total in org unit: {total})")
            
            # Display each TEI as it's processed
            if teis:
                print(f"\n{'─' * 80}")
                for idx, tei in enumerate(teis, 1):
                    tei_uid = tei.get('trackedEntityInstance', 'N/A')
                    tei_created = tei.get('created', 'N/A')[:10] if tei.get('created') else 'N/A'
                    attributes = tei.get('attributes', [])
                    enrollments = tei.get('enrollments', [])
                    
                    print(f"\n  📋 TEI {idx}/{len(teis)}: {tei_uid}")
                    print(f"     Created: {tei_created} | Org Unit: {tei.get('orgUnit', 'N/A')}")
                    print(f"     Attributes ({len(attributes)}):")
                    for attr in attributes:
                        display_name = attr.get('displayName', 'N/A')
                        attr_value = attr.get('value', 'N/A')
                        attr_id = attr.get('attribute', 'N/A')
                        print(f"       • {display_name}: {attr_value}  [{attr_id}]")
                    
                    print(f"     Enrollments ({len(enrollments)}):")
                    for enr in enrollments:
                        enr_id = enr.get('enrollment', 'N/A')
                        enr_date = enr.get('enrollmentDate', 'N/A')[:10] if enr.get('enrollmentDate') else 'N/A'
                        enr_status = enr.get('status', 'N/A')
                        enr_program = enr.get('program', 'N/A')
                        events = enr.get('events', [])
                        print(f"       • {enr_id}: {enr_status} (enrolled: {enr_date}, events: {len(events)})")
            else:
                print(f"\n  ⚠️  No TEIs found in {ou_name} for this program")
            
            # Save to file
            output_dir = 'outputs/phase2'
            os.makedirs(output_dir, exist_ok=True)
            output_file = f'{output_dir}/sample_teis_{program_key}.json'
            
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"\n{'─' * 80}")
            print(f"  💾 Full data saved to: {output_file}")
            
            return teis
            
        else:
            print(f"  ❌ Error fetching TEIs: HTTP {response.status_code}")
            print(f"  Response: {response.text}")
            sys.exit(1)
            
    except Exception as e:
        print(f"  ❌ Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Fetch sample Tracked Entity Instances from DHIS2 programs (READ-ONLY)'
    )
    parser.add_argument(
        '--program',
        choices=['household', 'harmonized', 'both'],
        default=None,
        help='Which program to fetch TEIs from (skips interactive prompt if set)'
    )
    parser.add_argument(
        '--sample-size',
        type=int,
        default=None,
        help='Number of TEIs to fetch per program (skips interactive prompt if set)'
    )
    parser.add_argument(
        '--org-unit',
        type=str,
        default=None,
        help='Org unit UID (skips interactive prompt if set)'
    )
    parser.add_argument(
        '--no-interactive',
        action='store_true',
        help='Disable interactive mode, use defaults (Lambulira, both, 10)'
    )
    
    args = parser.parse_args()
    
    print("\n" + "=" * 80)
    print("FETCH SAMPLE TRACKED ENTITY INSTANCES (READ-ONLY)")
    print("=" * 80)
    print("\n⚠️  This is a READ-ONLY operation - no data will be modified\n")
    
    # Determine mode: interactive or CLI args
    interactive = not args.no_interactive and (args.program is None or args.org_unit is None)
    
    if interactive:
        # Load org units for search
        ou_list = load_ou_codes()
        if not ou_list:
            print("  ⚠️  Could not load org unit list. Run Phase 1 first.")
            print("  Falling back to Lambulira.\n")
            ou_id, ou_name = 'AI3mavjiuUD', 'Lambulira'
        else:
            print(f"  Loaded {len(ou_list)} org units.")
            ou_id, ou_name = interactive_pick_org_unit(ou_list)
        
        program = args.program or interactive_pick_program()
        sample_size = args.sample_size or interactive_pick_sample_size()
    else:
        ou_id = args.org_unit or 'AI3mavjiuUD'
        ou_name = ou_id  # Will show UID if name not provided
        # Try to resolve name from CSV
        ou_list = load_ou_codes()
        for ou in ou_list:
            if ou['uid'] == ou_id:
                ou_name = ou['name']
                break
        program = args.program or 'both'
        sample_size = args.sample_size or 10
    
    print(f"\n  ── Configuration ──")
    print(f"  Org Unit:    {ou_name} ({ou_id})")
    print(f"  Program:     {program}")
    print(f"  Sample Size: {sample_size}")
    print()
    
    if program == 'both':
        print("Fetching from BOTH programs:\n")
        fetch_sample_teis('household', sample_size, ou_id, ou_name)
        print("\n" + "=" * 80 + "\n")
        fetch_sample_teis('harmonized', sample_size, ou_id, ou_name)
    else:
        fetch_sample_teis(program, sample_size, ou_id, ou_name)
    
    print("\n" + "=" * 80)
    print("✅ Sample fetch complete!")
    print("\nNext steps:")
    print("1. Review the JSON files in outputs/phase2/")
    print("2. Examine the TEI structure and attributes")
    print("3. Identify which attributes need ID generation")
    print("=" * 80 + "\n")


if __name__ == '__main__':
    main()
