#!/usr/bin/env python3
"""
Generate new standardised IDs for Household and Child TEIs.

This script:
1. Fetches all TEIs from specified org units
2. Loads org unit codes from Phase 1 CSV
3. Generates new IDs in the format: {OU_CODE}_HH_{SEQ} or {OU_CODE}_OVC_{SEQ}
4. Outputs a mapping CSV showing old ID → new ID
5. Does NOT modify any data on the server

Usage:
    python generate_ids.py --org-unit AI3mavjiuUD --dry-run
    python generate_ids.py --org-unit AI3mavjiuUD --program household
    python generate_ids.py --org-unit AI3mavjiuUD --program harmonized
"""
import requests
import json
import csv
import sys
import os
import re
import argparse
from collections import defaultdict

# Add parent directory to path to import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.settings import DHIS2_URL, DHIS2_USERNAME, DHIS2_PASSWORD


# Program definitions
PROGRAMS = {
    'household': {
        'id': 'lTaqt0loQak',
        'name': 'Household - CPMIS',
        'id_attribute': 'SYUXY9pax4w',      # Household ID
        'id_attribute_name': 'Household ID',
        'type_code': 'HH',
    },
    'harmonized': {
        'id': 'xhzwCCKzFBM',
        'name': 'MW Harmonized OVC Program - CPMIS',
        'id_attribute': 'cxr1eaTGEBO',      # Child UIC
        'id_attribute_name': 'Child UIC',
        'type_code': 'OVC',
    }
}

# Sequence length (zero-padded)
SEQ_LENGTH = 8


def load_ou_codes(csv_file='outputs/task1/ou_codes_standardized.csv'):
    """Load org unit codes from Phase 1 CSV."""
    ou_codes = {}
    try:
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                uid = row['dhis2_uid']
                code = row['standardised_code']
                name = row['ou_name']
                ou_codes[uid] = {'code': code, 'name': name}
    except FileNotFoundError:
        print(f"❌ CSV file not found: {csv_file}")
        print("   Run Phase 1 first: just task1-complete")
        sys.exit(1)
    
    return ou_codes


def fetch_all_teis(program_key, org_unit_id, page_size=200):
    """
    Fetch ALL tracked entity instances for a program and org unit.
    Paginates through all pages. READ-ONLY.
    """
    program = PROGRAMS[program_key]
    program_id = program['id']
    
    all_teis = []
    page = 1
    total = None
    
    while True:
        url = f"{DHIS2_URL}/api/trackedEntityInstances.json"
        params = {
            'ou': org_unit_id,
            'program': program_id,
            'fields': 'trackedEntityInstance,orgUnit,attributes[attribute,displayName,value]',
            'pageSize': page_size,
            'page': page,
            'totalPages': True
        }
        
        response = requests.get(
            url,
            params=params,
            auth=(DHIS2_USERNAME, DHIS2_PASSWORD)
        )
        
        if response.status_code != 200:
            print(f"  ❌ Error fetching page {page}: HTTP {response.status_code}")
            print(f"     {response.text}")
            sys.exit(1)
        
        data = response.json()
        teis = data.get('trackedEntityInstances', [])
        pager = data.get('pager', {})
        
        if total is None:
            total = pager.get('total', 0)
            print(f"  Total TEIs to process: {total}", flush=True)
        
        all_teis.extend(teis)
        
        fetched = len(all_teis)
        print(f"\r  Fetching: [{fetched}/{total}] ({(fetched/total*100):.0f}%)" if total > 0 else f"\r  Fetching: {fetched}...", end='', flush=True)
        
        page_count = pager.get('pageCount', 1)
        if page >= page_count:
            break
        
        page += 1
    
    print(f"\r  ✅ Fetched {len(all_teis)}/{total} TEIs".ljust(60))
    return all_teis


def extract_current_id(tei, id_attribute):
    """Extract the current ID value from a TEI's attributes."""
    for attr in tei.get('attributes', []):
        if attr.get('attribute') == id_attribute:
            return attr.get('value', '')
    return ''


def extract_sequence_number(current_id):
    """
    Try to extract the numeric sequence from an existing ID.
    Handles formats like:
      HH_0034588 → 34588
      ZALAMB15909 → 15909
      ZA_LAMBF_00014 → 14
      ZA_LAMB_HH_00000001 → 1 (already in new format)
    """
    if not current_id:
        return 0
    
    # Try to find trailing digits
    match = re.search(r'(\d+)\s*$', current_id)
    if match:
        return int(match.group(1))
    return 0


def generate_new_ids(teis, ou_code, type_code, id_attribute):
    """
    Generate new standardised IDs for all TEIs.
    
    New format: {OU_CODE}_{TYPE_CODE}_{SEQ}
    Example: ZA_LAMB_HH_00000001
    
    Preserves relative ordering of existing IDs where possible.
    """
    # Extract existing IDs and their sequence numbers
    tei_data = []
    for tei in teis:
        tei_uid = tei.get('trackedEntityInstance', '')
        current_id = extract_current_id(tei, id_attribute)
        seq_num = extract_sequence_number(current_id)
        tei_data.append({
            'tei_uid': tei_uid,
            'org_unit': tei.get('orgUnit', ''),
            'current_id': current_id,
            'old_seq': seq_num,
        })
    
    # Sort by existing sequence number to preserve ordering
    tei_data.sort(key=lambda x: (x['old_seq'], x['tei_uid']))
    
    # Generate new sequential IDs
    for i, item in enumerate(tei_data, 1):
        new_seq = str(i).zfill(SEQ_LENGTH)
        item['new_id'] = f"{ou_code}_{type_code}_{new_seq}"
        item['changed'] = item['current_id'] != item['new_id']
    
    return tei_data


def run_generation(program_key, org_unit_id, ou_codes):
    """Run ID generation for a single program and org unit."""
    program = PROGRAMS[program_key]
    program_name = program['name']
    type_code = program['type_code']
    id_attribute = program['id_attribute']
    id_attr_name = program['id_attribute_name']
    
    # Get org unit code
    ou_info = ou_codes.get(org_unit_id)
    if not ou_info:
        print(f"  ❌ Org unit {org_unit_id} not found in Phase 1 codes")
        return None
    
    ou_code = ou_info['code']
    ou_name = ou_info['name']
    
    print(f"\n{'─' * 80}")
    print(f"  Program: {program_name}")
    print(f"  Org Unit: {ou_name} ({org_unit_id})")
    print(f"  OU Code: {ou_code}")
    print(f"  ID Format: {ou_code}-{type_code}-{'0' * SEQ_LENGTH}")
    print(f"  ID Attribute: {id_attr_name} ({id_attribute})")
    print(f"{'─' * 80}")
    
    # Fetch all TEIs
    print(f"\n  Fetching TEIs from DHIS2...", flush=True)
    teis = fetch_all_teis(program_key, org_unit_id)
    
    if not teis:
        print(f"  ⚠️  No TEIs found")
        return None
    
    # Generate new IDs
    print(f"  Generating new IDs...", flush=True)
    results = generate_new_ids(teis, ou_code, type_code, id_attribute)
    
    # Display results
    changed_count = sum(1 for r in results if r['changed'])
    unchanged_count = sum(1 for r in results if not r['changed'])
    no_id_count = sum(1 for r in results if not r['current_id'])
    
    print(f"\n  📊 Results:")
    print(f"     Total TEIs:  {len(results)}")
    print(f"     Will change: {changed_count}")
    print(f"     Unchanged:   {unchanged_count}")
    print(f"     No current ID: {no_id_count}")
    
    # Show sample of changes
    print(f"\n  📋 Sample changes (first 10):")
    print(f"     {'Current ID':<25} → {'New ID':<30} {'Status'}")
    print(f"     {'─' * 70}")
    for r in results[:10]:
        current = r['current_id'] or '(empty)'
        status = "CHANGE" if r['changed'] else "same"
        print(f"     {current:<25} → {r['new_id']:<30} {status}")
    
    if len(results) > 10:
        print(f"     ... and {len(results) - 10} more")
    
    return results


def save_mapping_csv(all_results, output_file):
    """Save the ID mapping to a CSV file for review."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'tei_uid', 'org_unit', 'program', 'type_code',
            'current_id', 'new_id', 'changed'
        ])
        
        for program_key, results in all_results.items():
            if results is None:
                continue
            type_code = PROGRAMS[program_key]['type_code']
            for r in results:
                writer.writerow([
                    r['tei_uid'],
                    r['org_unit'],
                    program_key,
                    type_code,
                    r['current_id'],
                    r['new_id'],
                    r['changed']
                ])
    
    print(f"\n  💾 Mapping saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate new standardised IDs for Household and Child TEIs (READ-ONLY)'
    )
    parser.add_argument(
        '--org-unit',
        default='AI3mavjiuUD',  # Lambulira
        help='Org unit UID to process (default: Lambulira)'
    )
    parser.add_argument(
        '--program',
        choices=['household', 'harmonized', 'both'],
        default='both',
        help='Which program to generate IDs for (default: both)'
    )
    parser.add_argument(
        '--csv',
        default='outputs/task1/ou_codes_standardized.csv',
        help='Path to Phase 1 OU codes CSV'
    )
    
    args = parser.parse_args()
    
    print("\n" + "=" * 80)
    print("  GENERATE STANDARDISED IDs (READ-ONLY - NO SERVER CHANGES)")
    print("=" * 80)
    print("\n  ⚠️  This script only generates IDs locally.")
    print("  ⚠️  No data will be modified on the DHIS2 server.\n")
    
    # Load org unit codes from Phase 1
    print("  Loading org unit codes from Phase 1...", flush=True)
    ou_codes = load_ou_codes(args.csv)
    print(f"  ✅ Loaded {len(ou_codes)} org unit codes\n")
    
    # Run generation
    all_results = {}
    
    if args.program in ['household', 'both']:
        all_results['household'] = run_generation('household', args.org_unit, ou_codes)
    
    if args.program in ['harmonized', 'both']:
        all_results['harmonized'] = run_generation('harmonized', args.org_unit, ou_codes)
    
    # Save mapping CSV
    output_file = 'outputs/phase2/id_mapping.csv'
    save_mapping_csv(all_results, output_file)
    
    # Final summary
    total_teis = sum(len(r) for r in all_results.values() if r)
    total_changes = sum(sum(1 for x in r if x['changed']) for r in all_results.values() if r)
    
    print(f"\n{'=' * 80}")
    print(f"  ✅ ID GENERATION COMPLETE (DRY RUN)")
    print(f"{'=' * 80}")
    print(f"  Total TEIs processed: {total_teis}")
    print(f"  Total IDs that would change: {total_changes}")
    print(f"  Mapping CSV: {output_file}")
    print(f"\n  To apply these changes to DHIS2, run:")
    print(f"  ./venv/bin/python src/phase2/apply_ids.py --csv {output_file}")
    print(f"{'=' * 80}\n")


if __name__ == '__main__':
    main()
