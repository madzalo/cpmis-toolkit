#!/usr/bin/env python3
"""
Generate new standardised IDs for ALL org units across both programs.

Workflow:
1. Loads org unit codes from Phase 1 CSV
2. Fetches all org units assigned to each program
3. For each org unit, fetches TEIs and generates new IDs
4. Saves a complete mapping CSV (old ID → new ID)
5. Does NOT modify any data on the server

The apply_ids.py script can then be used to push changes.

Usage:
    # Generate IDs for all org units (both programs)
    python generate_all_ids.py

    # Generate for a specific program only
    python generate_all_ids.py --program household
    python generate_all_ids.py --program harmonized

    # Limit to specific org unit levels (e.g. only facilities)
    python generate_all_ids.py --levels 5

    # Limit to specific org unit levels (e.g. TAs + facilities)
    python generate_all_ids.py --levels 4,5
"""
import requests
import json
import csv
import sys
import os
import re
import argparse
import time

# Add parent directory to path to import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.settings import DHIS2_URL, DHIS2_USERNAME, DHIS2_PASSWORD


# Program definitions
PROGRAMS = {
    'household': {
        'id': 'lTaqt0loQak',
        'name': 'Household - CPMIS',
        'id_attribute': 'SYUXY9pax4w',
        'id_attribute_name': 'Household ID',
        'type_code': 'HH',
    },
    'harmonized': {
        'id': 'xhzwCCKzFBM',
        'name': 'MW Harmonized OVC Program - CPMIS',
        'id_attribute': 'cxr1eaTGEBO',
        'id_attribute_name': 'Child UIC',
        'type_code': 'OVC',
    }
}

SEQ_LENGTH = 8


def load_ou_codes(csv_file='outputs/task1/ou_codes_standardized.csv'):
    """Load org unit codes from Phase 1 CSV."""
    ou_codes = {}
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            uid = row['dhis2_uid']
            code = row['standardised_code']
            name = row['ou_name']
            level = int(row.get('ou_level', 0))
            ou_codes[uid] = {'code': code, 'name': name, 'level': level}
    return ou_codes


def get_program_org_units(program_id):
    """Fetch all org units assigned to a program."""
    url = f"{DHIS2_URL}/api/programs/{program_id}.json"
    params = {'fields': 'organisationUnits[id,name,level]'}
    
    response = requests.get(
        url, params=params,
        auth=(DHIS2_USERNAME, DHIS2_PASSWORD)
    )
    
    if response.status_code != 200:
        print(f"  ❌ Error fetching program org units: HTTP {response.status_code}")
        sys.exit(1)
    
    return response.json().get('organisationUnits', [])


def fetch_teis_for_ou(program_id, org_unit_id, id_attribute, page_size=50):
    """Fetch all TEIs for a specific program and org unit. Returns list of TEIs."""
    all_teis = []
    page = 1
    
    while True:
        url = f"{DHIS2_URL}/api/trackedEntityInstances.json"
        params = {
            'ou': org_unit_id,
            'program': program_id,
            'fields': f'trackedEntityInstance,orgUnit,attributes[attribute,value]',
            'pageSize': page_size,
            'page': page,
            'totalPages': True
        }
        
        response = requests.get(
            url, params=params,
            auth=(DHIS2_USERNAME, DHIS2_PASSWORD)
        )
        
        if response.status_code != 200:
            return all_teis, -1  # Error
        
        data = response.json()
        teis = data.get('trackedEntityInstances', [])
        pager = data.get('pager', {})
        total = pager.get('total', 0)
        
        all_teis.extend(teis)
        
        if page >= pager.get('pageCount', 1):
            break
        page += 1
    
    return all_teis, total


def extract_current_id(tei, id_attribute):
    """Extract the current ID value from a TEI's attributes."""
    for attr in tei.get('attributes', []):
        if attr.get('attribute') == id_attribute:
            return attr.get('value', '')
    return ''


def extract_sequence_number(current_id):
    """Extract trailing numeric sequence from an existing ID."""
    if not current_id:
        return 0
    match = re.search(r'(\d+)\s*$', current_id)
    if match:
        return int(match.group(1))
    return 0


def generate_ids_for_ou(teis, ou_code, type_code, id_attribute):
    """Generate new IDs for TEIs in a single org unit."""
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
    
    # Sort by existing sequence to preserve ordering
    tei_data.sort(key=lambda x: (x['old_seq'], x['tei_uid']))
    
    # Generate new sequential IDs
    for i, item in enumerate(tei_data, 1):
        new_seq = str(i).zfill(SEQ_LENGTH)
        item['new_id'] = f"{ou_code}-{type_code}-{new_seq}"
        item['changed'] = item['current_id'] != item['new_id']
    
    return tei_data


def process_program(program_key, ou_codes, level_filter=None):
    """Process all org units for a single program."""
    program = PROGRAMS[program_key]
    program_id = program['id']
    program_name = program['name']
    type_code = program['type_code']
    id_attribute = program['id_attribute']
    
    print(f"\n{'=' * 80}")
    print(f"  Program: {program_name}")
    print(f"  Type Code: {type_code}")
    print(f"  ID Attribute: {program['id_attribute_name']} ({id_attribute})")
    print(f"{'=' * 80}")
    
    # Get all org units for this program
    print(f"\n  Fetching org units for program...", flush=True)
    program_ous = get_program_org_units(program_id)
    
    # Filter by level if specified
    if level_filter:
        program_ous = [ou for ou in program_ous if ou.get('level') in level_filter]
    
    print(f"  Found {len(program_ous)} org units to process")
    
    all_results = []
    total_teis = 0
    total_changed = 0
    ous_with_teis = 0
    ous_skipped = 0
    
    start_time = time.time()
    
    for idx, ou in enumerate(program_ous, 1):
        ou_id = ou['id']
        ou_name = ou.get('name', 'Unknown')
        ou_level = ou.get('level', '?')
        
        # Check if we have a code for this org unit
        ou_info = ou_codes.get(ou_id)
        if not ou_info:
            ous_skipped += 1
            continue
        
        ou_code = ou_info['code']
        
        # Progress
        elapsed = time.time() - start_time
        rate = idx / elapsed if elapsed > 0 else 0
        eta = (len(program_ous) - idx) / rate if rate > 0 else 0
        
        print(f"\r  [{idx}/{len(program_ous)}] {ou_name} (L{ou_level}, {ou_code}) - {total_teis} TEIs so far ({rate:.1f} ou/s, ETA: {eta:.0f}s)".ljust(120), end='', flush=True)
        
        # Fetch TEIs for this org unit
        teis, total = fetch_teis_for_ou(program_id, ou_id, id_attribute)
        
        if not teis:
            continue
        
        ous_with_teis += 1
        
        # Generate new IDs
        results = generate_ids_for_ou(teis, ou_code, type_code, id_attribute)
        
        for r in results:
            r['ou_name'] = ou_name
            r['ou_code'] = ou_code
            r['ou_level'] = ou_level
            r['program'] = program_key
            r['type_code'] = type_code
        
        all_results.extend(results)
        total_teis += len(results)
        total_changed += sum(1 for r in results if r['changed'])
    
    elapsed = time.time() - start_time
    print(f"\r  ✅ Processed {len(program_ous)} org units in {elapsed:.1f}s".ljust(120))
    
    print(f"\n  📊 {program_name} Summary:")
    print(f"     Org units processed: {len(program_ous)}")
    print(f"     Org units with TEIs: {ous_with_teis}")
    print(f"     Org units skipped (no code): {ous_skipped}")
    print(f"     Total TEIs: {total_teis}")
    print(f"     IDs to change: {total_changed}")
    print(f"     Already correct: {total_teis - total_changed}")
    
    return all_results


def save_mapping_csv(all_results, output_file):
    """Save the complete ID mapping to CSV."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'tei_uid', 'org_unit', 'ou_name', 'ou_code', 'ou_level',
            'program', 'type_code', 'current_id', 'new_id', 'changed'
        ])
        
        for r in all_results:
            writer.writerow([
                r['tei_uid'],
                r['org_unit'],
                r.get('ou_name', ''),
                r.get('ou_code', ''),
                r.get('ou_level', ''),
                r['program'],
                r['type_code'],
                r['current_id'],
                r['new_id'],
                r['changed']
            ])
    
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description='Generate standardised IDs for ALL org units (READ-ONLY)'
    )
    parser.add_argument(
        '--program',
        choices=['household', 'harmonized', 'both'],
        default='both',
        help='Which program to process (default: both)'
    )
    parser.add_argument(
        '--levels',
        type=str,
        default=None,
        help='Comma-separated org unit levels to include (e.g. "4,5"). Default: all levels'
    )
    parser.add_argument(
        '--csv',
        default='outputs/task1/ou_codes_standardized.csv',
        help='Path to Phase 1 OU codes CSV'
    )
    parser.add_argument(
        '--output',
        default='outputs/phase2/id_mapping_all.csv',
        help='Output mapping CSV path'
    )
    
    args = parser.parse_args()
    
    level_filter = None
    if args.levels:
        level_filter = [int(l.strip()) for l in args.levels.split(',')]
    
    print("\n" + "=" * 80)
    print("  GENERATE STANDARDISED IDs - ALL ORG UNITS (READ-ONLY)")
    print("=" * 80)
    print(f"\n  ⚠️  This script only generates IDs locally.")
    print(f"  ⚠️  No data will be modified on the DHIS2 server.")
    print(f"  Server: {DHIS2_URL}")
    if level_filter:
        print(f"  Filtering to org unit levels: {level_filter}")
    print()
    
    # Load org unit codes
    print(f"  Loading org unit codes from Phase 1...", flush=True)
    ou_codes = load_ou_codes(args.csv)
    print(f"  ✅ Loaded {len(ou_codes)} org unit codes")
    
    # Process programs
    all_results = []
    
    if args.program in ['household', 'both']:
        results = process_program('household', ou_codes, level_filter)
        all_results.extend(results)
    
    if args.program in ['harmonized', 'both']:
        results = process_program('harmonized', ou_codes, level_filter)
        all_results.extend(results)
    
    # Save mapping
    output_file = save_mapping_csv(all_results, args.output)
    
    # Final summary
    total_teis = len(all_results)
    total_changed = sum(1 for r in all_results if r['changed'])
    hh_count = sum(1 for r in all_results if r['program'] == 'household')
    ovc_count = sum(1 for r in all_results if r['program'] == 'harmonized')
    unique_ous = len(set(r['org_unit'] for r in all_results))
    
    print(f"\n{'=' * 80}")
    print(f"  ✅ ID GENERATION COMPLETE")
    print(f"{'=' * 80}")
    print(f"  Total TEIs processed:      {total_teis}")
    print(f"    Household IDs:           {hh_count}")
    print(f"    Child UICs:              {ovc_count}")
    print(f"  Org units with TEIs:       {unique_ous}")
    print(f"  IDs that would change:     {total_changed}")
    print(f"  Already correct:           {total_teis - total_changed}")
    print(f"\n  Mapping CSV: {output_file}")
    print(f"\n  Next steps:")
    print(f"  1. Review the mapping CSV")
    print(f"  2. Dry run:  ./venv/bin/python src/phase2/apply_ids.py --csv {output_file} --dry-run")
    print(f"  3. Apply:    ./venv/bin/python src/phase2/apply_ids.py --csv {output_file}")
    print(f"{'=' * 80}\n")


if __name__ == '__main__':
    main()
