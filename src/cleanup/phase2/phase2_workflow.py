#!/usr/bin/env python3
"""
Phase 2: Unified Interactive Workflow for TEI ID Standardisation.

This is the main entry point for Phase 2. It guides you through:
1. Selecting scope (single org unit, district, multiple districts, or all)
2. Generating new standardised IDs
3. Previewing changes (dry-run)
4. Applying changes to the live DHIS2 server

Usage:
    python phase2_workflow.py                    # Interactive mode
    python phase2_workflow.py --district ZA      # Zomba district (by code)
    python phase2_workflow.py --org-unit AI3...  # Single org unit (by UID)
    python phase2_workflow.py --all              # All org units
"""
import requests
from requests.adapters import HTTPAdapter
import json
import csv
import sys
import os
import re
import argparse
import time
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent directory to path to import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.settings import DHIS2_URL as _RAW_URL, DHIS2_USERNAME, DHIS2_PASSWORD

# Strip trailing slash to avoid double-slash in URLs (//api/...)
DHIS2_URL = _RAW_URL.rstrip('/')

# ─── Shared Session (reuses TCP/TLS connections = much faster) ──────────────
SESSION = requests.Session()
SESSION.auth = (DHIS2_USERNAME, DHIS2_PASSWORD)
SESSION.headers.update({'Content-Type': 'application/json'})
# Size connection pool to match max parallel workers
SESSION.mount('https://', HTTPAdapter(pool_connections=8, pool_maxsize=8))
SESSION.mount('http://', HTTPAdapter(pool_connections=8, pool_maxsize=8))


# ─── Program Definitions ─────────────────────────────────────────────────────

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
OUTPUT_DIR = 'outputs/phase2'


# ─── Data Loading ────────────────────────────────────────────────────────────

def load_ou_codes(csv_file='outputs/task1/ou_codes_standardized.csv'):
    """Load org unit codes from Phase 1 CSV."""
    ou_list = []
    ou_map = {}
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


def get_children_of_ou(parent_uid, parent_name=''):
    """Fetch all descendant org units of a parent (district) from DHIS2 API."""
    label = parent_name or parent_uid
    print(f"  📡 Fetching org units under {label}...", end='', flush=True)
    url = f"{DHIS2_URL}/api/organisationUnits.json"
    params = {
        'filter': f'path:like:{parent_uid}',
        'fields': 'id,name,level',
        'paging': 'false',
    }
    response = SESSION.get(url, params=params)
    if response.status_code != 200:
        print(f" ❌ HTTP {response.status_code}")
        return []
    children = response.json().get('organisationUnits', [])
    print(f" ✅ {len(children)} org units")
    if children:
        by_level = {}
        for c in children:
            lvl = c.get('level', '?')
            by_level.setdefault(lvl, []).append(c['name'])
        for lvl in sorted(by_level.keys()):
            names = by_level[lvl]
            sample = ', '.join(names[:5])
            suffix = f' ... +{len(names)-5} more' if len(names) > 5 else ''
            print(f"    L{lvl}: {len(names)} org units ({sample}{suffix})")
    return children


def get_program_org_units(program_id, program_name=''):
    """Fetch all org units assigned to a program."""
    label = program_name or program_id
    print(f"  📡 Fetching org units for {label}...", end='', flush=True)
    url = f"{DHIS2_URL}/api/programs/{program_id}.json"
    params = {'fields': 'organisationUnits[id,name,level]'}
    response = SESSION.get(url, params=params)
    if response.status_code != 200:
        print(f" ❌ HTTP {response.status_code}")
        return []
    ous = response.json().get('organisationUnits', [])
    print(f" ✅ {len(ous)} org units")
    return ous


# ─── Interactive Selection ───────────────────────────────────────────────────

def interactive_select_scope(ou_list):
    """Let the user interactively choose the scope of the operation."""
    print("\n  ── Select Scope ──")
    print("    1. Single org unit")
    print("    2. Single district (all org units within)")
    print("    3. Multiple districts")
    print("    4. All org units")

    while True:
        choice = input("\n  Pick scope (1-4): ").strip()
        if choice in ['1', '2', '3', '4']:
            break
        print("  ⚠️  Enter 1, 2, 3, or 4.")

    if choice == '1':
        uid, name = search_and_pick_ou(ou_list, "Search org unit")
        return 'single', [uid]

    elif choice == '2':
        districts = [ou for ou in ou_list if ou['level'] == 3]
        print(f"\n  Available districts ({len(districts)}):")
        for i, d in enumerate(districts, 1):
            print(f"    {i:>3}. {d['name']:<40} {d['code']:<12}")

        while True:
            pick = input(f"\n  Pick a district (1-{len(districts)}): ").strip()
            if not pick:
                print("  ❌ Please enter a number.")
                continue
            try:
                num = int(pick)
                if 1 <= num <= len(districts):
                    selected = districts[num - 1]
                    print(f"  ✅ Selected: {selected['name']}")
                    return 'district', [selected['uid']]
                else:
                    print(f"  ❌ Invalid number. Please enter a number between 1 and {len(districts)}.")
            except ValueError:
                print("  ❌ Invalid input. Please enter a number.")

    elif choice == '3':
        districts = [ou for ou in ou_list if ou['level'] == 3]
        print(f"\n  Available districts ({len(districts)}):")
        for i, d in enumerate(districts, 1):
            print(f"    {i:>3}. {d['name']:<40} {d['code']:<12}")

        while True:
            pick = input(f"\n  Pick districts (comma-separated numbers, e.g., 1,3,5): ").strip()
            if not pick:
                print("  ❌ Please enter number(s).")
                continue
            try:
                numbers = [int(n.strip()) for n in pick.split(',')]
                if all(1 <= n <= len(districts) for n in numbers):
                    selected = [districts[n - 1]['uid'] for n in numbers]
                    selected_names = [districts[n - 1]['name'] for n in numbers]
                    print(f"  ✅ Selected: {', '.join(selected_names)}")
                    return 'districts', selected
                else:
                    print(f"  ❌ Invalid number(s). Please enter numbers between 1 and {len(districts)}.")
            except ValueError:
                print("  ❌ Invalid input. Please enter number(s) separated by commas.")

    elif choice == '4':
        return 'all', []


def search_and_pick_ou(ou_list, prompt_label="Search"):
    """Search and pick an org unit from a list."""
    while True:
        query = input(f"\n  🔍 {prompt_label} (name or code): ").strip()
        if not query:
            continue
        if query.lower() == 'done':
            return 'done', 'done'

        matches = [
            ou for ou in ou_list
            if query.lower() in ou['name'].lower() or query.lower() in ou['code'].lower()
        ]

        if not matches:
            print(f"  ⚠️  No matches for '{query}'. Try again.")
            continue

        display = matches[:20]
        print(f"\n  Found {len(matches)} matches" + (" (showing first 20):" if len(matches) > 20 else ":"))
        for i, ou in enumerate(display, 1):
            print(f"    {i:3d}. {ou['name']:<35} L{ou['level']}  {ou['code']:<12} ({ou['uid']})")

        if len(matches) > 20:
            print(f"    ... {len(matches) - 20} more. Narrow your search.")

        pick = input(f"\n  Pick a number (1-{len(display)}), or Enter to search again: ").strip()
        if not pick:
            continue

        try:
            idx = int(pick) - 1
            if 0 <= idx < len(display):
                sel = display[idx]
                return sel['uid'], sel['name']
        except ValueError:
            pass
        print("  ⚠️  Invalid choice. Try again.")


def interactive_pick_program():
    """Let the user pick which program to process."""
    print("\n  ── Select Program ──")
    print("    1. Household - CPMIS")
    print("    2. MW Harmonized OVC Program - CPMIS")
    print("    3. Both")

    while True:
        choice = input("\n  Pick a program (1-3) [3]: ").strip() or '3'
        if choice == '1':
            return 'household'
        elif choice == '2':
            return 'harmonized'
        elif choice == '3':
            return 'both'
        print("  ⚠️  Enter 1, 2, or 3.")


# ─── Resolve Target Org Units ───────────────────────────────────────────────

def resolve_target_org_units(scope, scope_ids, ou_map):
    """Resolve the final list of org unit UIDs to process based on scope."""
    if scope == 'single':
        return scope_ids

    elif scope in ('district', 'districts'):
        all_uids = set()
        for i, district_uid in enumerate(scope_ids, 1):
            district_info = ou_map.get(district_uid, {})
            district_name = district_info.get('name', district_uid)
            if len(scope_ids) > 1:
                print(f"  [{i}/{len(scope_ids)}] District: {district_name}")
            children = get_children_of_ou(district_uid, district_name)
            child_uids = [c['id'] for c in children]
            all_uids.update(child_uids)
        return list(all_uids)

    elif scope == 'all':
        return None  # None means "all available in program"


# ─── TEI Fetching & ID Generation ───────────────────────────────────────────

def fetch_teis_for_ou(program_id, org_unit_id, ou_label='', progress_prefix='', page_size=1000):
    """Fetch all TEIs for a program and org unit with page-level progress."""
    all_teis = []
    page = 1
    while True:
        url = f"{DHIS2_URL}/api/trackedEntityInstances.json"
        params = {
            'ou': org_unit_id,
            'program': program_id,
            'fields': 'trackedEntityInstance,orgUnit,trackedEntityType,attributes[attribute,value]',
            'pageSize': page_size,
            'page': page,
            'totalPages': True,
        }
        try:
            response = SESSION.get(url, params=params, timeout=30)
            if response.status_code != 200:
                return all_teis
        except Exception:
            return all_teis
        data = response.json()
        teis = data.get('trackedEntityInstances', [])
        pager = data.get('pager', {})
        total = pager.get('total', len(teis))
        page_count = pager.get('pageCount', 1)
        all_teis.extend(teis)
        if page_count > 1:
            print(f"\r  {progress_prefix}Fetching TEIs from {ou_label}: page {page}/{page_count} ({len(all_teis)}/{total})".ljust(110), end='', flush=True)
        if page >= page_count:
            break
        page += 1
    return all_teis


def fetch_teis_for_ou_silent(program_id, org_unit_id, page_size=1000):
    """Fetch all TEIs for a program and org unit (no output, for parallel use)."""
    all_teis = []
    page = 1
    while True:
        url = f"{DHIS2_URL}/api/trackedEntityInstances.json"
        params = {
            'ou': org_unit_id,
            'program': program_id,
            'fields': 'trackedEntityInstance,orgUnit,trackedEntityType,attributes[attribute,value]',
            'pageSize': page_size,
            'page': page,
            'totalPages': True,
        }
        try:
            response = SESSION.get(url, params=params, timeout=30)
            if response.status_code != 200:
                return org_unit_id, all_teis
        except Exception:
            return org_unit_id, all_teis
        data = response.json()
        teis = data.get('trackedEntityInstances', [])
        pager = data.get('pager', {})
        page_count = pager.get('pageCount', 1)
        all_teis.extend(teis)
        if page >= page_count:
            break
        page += 1
    return org_unit_id, all_teis


def extract_current_id(tei, id_attribute):
    for attr in tei.get('attributes', []):
        if attr.get('attribute') == id_attribute:
            return attr.get('value', '')
    return ''


def extract_sequence_number(current_id):
    if not current_id:
        return 0
    match = re.search(r'(\d+)\s*$', current_id)
    return int(match.group(1)) if match else 0


def generate_ids_for_ou(teis, ou_code, type_code, id_attribute):
    """Generate new IDs for TEIs in a single org unit."""
    tei_data = []
    for tei in teis:
        tei_uid = tei.get('trackedEntityInstance', '')
        current_id = extract_current_id(tei, id_attribute)
        tei_data.append({
            'tei_uid': tei_uid,
            'org_unit': tei.get('orgUnit', ''),
            'tracked_entity_type': tei.get('trackedEntityType', ''),
            'current_id': current_id,
            'old_seq': extract_sequence_number(current_id),
        })

    tei_data.sort(key=lambda x: (x['old_seq'], x['tei_uid']))

    for i, item in enumerate(tei_data, 1):
        item['new_id'] = f"{ou_code}_{type_code}_{str(i).zfill(SEQ_LENGTH)}"
        item['changed'] = item['current_id'] != item['new_id']

    return tei_data


# ─── Process Programs ────────────────────────────────────────────────────────

def process_program(program_key, target_ou_uids, ou_map):
    """
    Generate IDs for a program across target org units.

    Args:
        program_key: 'household' or 'harmonized'
        target_ou_uids: list of org unit UIDs, or None for all
        ou_map: dict of uid -> ou info

    Returns:
        list of result dicts
    """
    program = PROGRAMS[program_key]
    program_id = program['id']
    type_code = program['type_code']
    id_attribute = program['id_attribute']

    print(f"\n  {'─' * 70}")
    print(f"  Program: {program['name']}")
    print(f"  ID Format: <OU_CODE>_{type_code}_{'0' * SEQ_LENGTH}")

    # If target_ou_uids is None, fetch all from program
    if target_ou_uids is None:
        program_ous = get_program_org_units(program_id, program['name'])
        ou_uids_to_process = [ou['id'] for ou in program_ous]
    else:
        ou_uids_to_process = target_ou_uids

    # Filter to only org units we have codes for
    valid_ous = [(uid, ou_map[uid]) for uid in ou_uids_to_process if uid in ou_map]
    print(f"  Org units to process: {len(valid_ous)}")

    all_results = []
    total_teis = 0
    ous_with_teis = 0
    start_time = time.time()

    # ── Parallel fetch TEIs for all org units ──
    max_workers = min(6, len(valid_ous))
    tei_by_ou = {}
    fetched = 0

    if len(valid_ous) > 1 and max_workers > 1:
        print(f"  ⚡ Fetching TEIs from {len(valid_ous)} org units ({max_workers} parallel)...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(fetch_teis_for_ou_silent, program_id, uid): uid
                for uid, _ in valid_ous
            }
            for future in as_completed(futures):
                ou_uid_result, teis = future.result()
                tei_by_ou[ou_uid_result] = teis
                fetched += 1
                total_fetched_teis = sum(len(t) for t in tei_by_ou.values())
                elapsed = time.time() - start_time
                print(f"\r  ⚡ Fetched {fetched}/{len(valid_ous)} org units ({total_fetched_teis} TEIs, {elapsed:.1f}s)".ljust(110), end='', flush=True)
        print()
    else:
        # Single org unit — use the verbose version
        for uid, info in valid_ous:
            teis = fetch_teis_for_ou(program_id, uid, ou_label=info['name'])
            tei_by_ou[uid] = teis
        print()

    # ── Generate IDs (sequential, fast) ──
    for idx, (ou_uid, ou_info) in enumerate(valid_ous, 1):
        ou_name = ou_info['name']
        ou_code = ou_info['code']
        ou_level = ou_info['level']

        teis = tei_by_ou.get(ou_uid, [])
        if not teis:
            continue

        ous_with_teis += 1
        prefix = f"[{idx}/{len(valid_ous)}] "
        print(f"\r  {prefix}{ou_name:<30} ({ou_code}) - {len(teis)} TEIs, generating IDs...".ljust(110), end='', flush=True)
        results = generate_ids_for_ou(teis, ou_code, type_code, id_attribute)

        for r in results:
            r['ou_name'] = ou_name
            r['ou_code'] = ou_code
            r['ou_level'] = ou_level
            r['program'] = program_key
            r['type_code'] = type_code

        all_results.extend(results)
        total_teis += len(results)
        changed_here = sum(1 for r in results if r['changed'])
        print(f"\r  {prefix}{ou_name:<30} ({ou_code}) ✅ {len(teis)} TEIs, {changed_here} to change".ljust(110))

    elapsed = time.time() - start_time
    print(f"  ✅ {program['name']}: {total_teis} TEIs across {ous_with_teis} org units ({elapsed:.1f}s)")

    return all_results


# ─── Saving & Previewing ────────────────────────────────────────────────────

def save_mapping_csv(all_results, output_file):
    """Save the ID mapping to CSV."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'tei_uid', 'org_unit', 'tracked_entity_type', 'ou_name', 'ou_code', 'ou_level',
            'program', 'type_code', 'current_id', 'new_id', 'changed'
        ])
        for r in all_results:
            writer.writerow([
                r['tei_uid'], r['org_unit'], r.get('tracked_entity_type', ''),
                r.get('ou_name', ''), r.get('ou_code', ''), r.get('ou_level', ''),
                r['program'], r['type_code'],
                r['current_id'], r['new_id'], r['changed']
            ])
    return output_file


def preview_changes(all_results):
    """Show a preview of the changes to be made."""
    changed = [r for r in all_results if r['changed']]
    unchanged = len(all_results) - len(changed)
    no_id = sum(1 for r in all_results if not r['current_id'])

    hh_count = sum(1 for r in changed if r['program'] == 'household')
    ovc_count = sum(1 for r in changed if r['program'] == 'harmonized')
    unique_ous = len(set(r['org_unit'] for r in all_results))

    print(f"\n  {'═' * 70}")
    print(f"  PREVIEW SUMMARY")
    print(f"  {'═' * 70}")
    print(f"  Total TEIs:          {len(all_results)}")
    print(f"  Org units:           {unique_ous}")
    print(f"  IDs to change:       {len(changed)}")
    print(f"    Household IDs:     {hh_count}")
    print(f"    Child UICs:        {ovc_count}")
    print(f"  Already correct:     {unchanged}")
    print(f"  Currently empty:     {no_id}")

    # Show sample
    print(f"\n  Sample changes (first 15):")
    print(f"  {'Org Unit':<20} {'Current ID':<35} → {'New ID':<30}")
    print(f"  {'─' * 90}")
    for r in changed[:15]:
        current = r['current_id'] or '(empty)'
        print(f"  {r.get('ou_name', '')[:20]:<20} {current:<35} → {r['new_id']:<30}")
    if len(changed) > 15:
        print(f"  ... and {len(changed) - 15} more")
    print()


# ─── Apply Changes (Bulk) ───────────────────────────────────────────────────

def update_single_tei(tei_payload, retries=3, timeout=90):
    """Update a single TEI via PUT with retry. Returns (tei_uid, True/False, error_msg).
    Used only as a fallback for TEIs that failed in bulk."""
    tei_uid = tei_payload['trackedEntityInstance']
    for attempt in range(1, retries + 1):
        try:
            url = f"{DHIS2_URL}/api/trackedEntityInstances/{tei_uid}?mergeMode=MERGE"
            resp = SESSION.put(url, json=tei_payload, timeout=timeout)
            if resp.status_code in [200, 201, 204]:
                return tei_uid, True, None
            else:
                try:
                    body = resp.json()
                    msg = body.get('message', '') or body.get('response', {}).get('description', '')
                    err = f"HTTP {resp.status_code}: {msg[:120]}" if msg else f"HTTP {resp.status_code}"
                except Exception:
                    err = f"HTTP {resp.status_code}: {resp.text[:120]}"
        except Exception as e:
            err = str(e)[:120]
        if attempt < retries:
            time.sleep(2 * attempt)
    return tei_uid, False, err


async def _async_update_tei(session, semaphore, tei_payload, retries=3, timeout=90):
    """Async PUT for a single TEI. Returns (tei_uid, True/False, error_msg)."""
    tei_uid = tei_payload['trackedEntityInstance']
    url = f"{DHIS2_URL}/api/trackedEntityInstances/{tei_uid}?mergeMode=MERGE"
    err = 'unknown'
    for attempt in range(1, retries + 1):
        try:
            async with semaphore:
                async with session.put(url, json=tei_payload,
                                       timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status in [200, 201, 204]:
                        return tei_uid, True, None
                    try:
                        body = await resp.json(content_type=None)
                        msg = body.get('message', '') or body.get('response', {}).get('description', '')
                        err = f"HTTP {resp.status}: {msg[:120]}" if msg else f"HTTP {resp.status}"
                    except Exception:
                        text = await resp.text()
                        err = f"HTTP {resp.status}: {text[:120]}"
        except Exception as e:
            err = str(e)[:120]
        if attempt < retries:
            await asyncio.sleep(2 * attempt)
    return tei_uid, False, err


async def _run_async_updates(updates, concurrency=10):
    """Run all TEI PUTs concurrently with aiohttp. Returns (success, failed_list)."""
    semaphore = asyncio.Semaphore(concurrency)
    auth = aiohttp.BasicAuth(DHIS2_USERNAME, DHIS2_PASSWORD)
    connector = aiohttp.TCPConnector(limit=concurrency, limit_per_host=concurrency)
    headers = {'Content-Type': 'application/json'}

    success = 0
    failed_list = []
    done = 0
    total_updates = len(updates)
    start_time = time.time()

    async with aiohttp.ClientSession(auth=auth, connector=connector, headers=headers) as session:
        tasks = [
            asyncio.ensure_future(_async_update_tei(session, semaphore, payload, 3, 90))
            for payload in updates
        ]
        for coro in asyncio.as_completed(tasks):
            tei_uid, ok, err = await coro
            done += 1
            if ok:
                success += 1
            else:
                failed_list.append(f"{tei_uid}: {err}")
                print(f"\n  ❌ {tei_uid}: {err}")

            elapsed = time.time() - start_time
            rate = done / elapsed if elapsed > 0 else 0
            remaining = total_updates - done
            eta = remaining / rate if rate > 0 else 0
            eta_str = f"{int(eta//3600)}h{int((eta%3600)//60)}m{int(eta%60)}s" if eta >= 3600 else f"{int(eta//60)}m{int(eta%60)}s"
            pct = done * 100 // total_updates
            print(
                f"\r  🚀 [{done}/{total_updates}] {pct}% — ✅ {success} updated  ❌ {len(failed_list)} failed  "
                f"({rate:.1f} TEIs/s, ETA: {eta_str})".ljust(110),
                end='', flush=True
            )

    return success, failed_list


def apply_changes(csv_file, use_db=False):
    """
    Apply ID changes from CSV to DHIS2.

    Args:
        csv_file: Path to CSV mapping file
        use_db: If True, update directly via PostgreSQL (FAST but bypasses DHIS2 validation).
                If False, use DHIS2 API with async aiohttp PUT requests (SAFE but slower).

    Each API PUT sends only the single ID attribute with mergeMode=MERGE,
    so all other TEI attributes remain untouched. Uses 4 concurrent async
    requests for high throughput without overwhelming the server.
    """
    if use_db:
        from cleanup.phase2.db_update import apply_changes_via_db
        program_attributes = {
            'household': PROGRAMS['household']['id_attribute'],
            'harmonized': PROGRAMS['harmonized']['id_attribute'],
        }
        return apply_changes_via_db(csv_file, program_attributes)
    if not os.path.exists(csv_file):
        print(f"  ❌ CSV file not found: {csv_file}")
        return 0, 0

    # Read only the rows that actually need changing
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        mappings = [r for r in reader if r.get('changed') == 'True']

    if not mappings:
        print("  ℹ️  No changes to apply.")
        return 0, 0

    total = len(mappings)
    print(f"\n  Applying {total} ID changes...\n")

    # ── Build minimal payloads directly from CSV ─────────────────────────
    # The CSV already contains org_unit and tracked_entity_type from the
    # first fetch (during ID generation). No second fetch needed.
    # Each payload sends ONLY the single ID attribute; mergeMode=MERGE
    # ensures all other attributes remain untouched.
    updates = []
    skipped = 0
    for row in mappings:
        tei_uid = row['tei_uid']
        org_unit = row.get('org_unit', '')
        tracked_entity_type = row.get('tracked_entity_type', '')
        program = row['program']
        new_id = row['new_id']
        attribute_id = PROGRAMS[program]['id_attribute']

        if not org_unit or not tracked_entity_type:
            skipped += 1
            continue

        updates.append({
            'trackedEntityInstance': tei_uid,
            'orgUnit': org_unit,
            'trackedEntityType': tracked_entity_type,
            'attributes': [{'attribute': attribute_id, 'value': new_id}],
        })

    if skipped:
        print(f"  ⚠️  {skipped} TEIs skipped (missing org_unit or tracked_entity_type in CSV)")
    print(f"  📝 {len(updates)} TEIs ready to update")

    # ── STEP C: Async PUT with aiohttp (4 concurrent requests) ─────────────
    # Uses aiohttp with asyncio for non-blocking I/O — much higher throughput
    # than threads. Semaphore limits concurrency to avoid overwhelming the
    # DHIS2 server. Each PUT sends only the single ID attribute;
    # mergeMode=MERGE ensures all other attributes remain untouched.
    CONCURRENCY = 4
    total_updates = len(updates)

    print(f"\n  🚀 Updating {total_updates} TEIs with {CONCURRENCY} async connections...\n")

    start_time = time.time()
    success, failed_list = asyncio.run(_run_async_updates(updates, concurrency=CONCURRENCY))

    # ── Final summary ────────────────────────────────────────────────────────
    total_elapsed = time.time() - start_time
    error_count = len(failed_list)
    rate = success / total_elapsed if total_elapsed > 0 else 0

    print(f"\n\n  Summary:")
    print(f"  Total:     {total_updates}")
    print(f"  Success:   {success}")
    print(f"  Errors:    {error_count}")
    if skipped:
        print(f"  Skipped:   {skipped}")
    print(f"  Time:      {total_elapsed:.1f}s")
    print(f"  Rate:      {rate:.1f} TEIs/s")

    if failed_list:
        print(f"\n  Errors (first 10):")
        for err in failed_list[:10]:
            print(f"    ❌ {err}")
        if len(failed_list) > 10:
            print(f"    ... and {len(failed_list) - 10} more")

    return success, error_count


# ─── Main Workflow ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Phase 2: TEI ID Standardisation Workflow'
    )
    parser.add_argument('--org-unit', type=str, help='Single org unit UID')
    parser.add_argument('--district', type=str, help='District code(s), comma-separated (e.g. "ZA" or "ZA,BL")')
    parser.add_argument('--all', action='store_true', help='Process all org units')
    parser.add_argument('--program', choices=['household', 'harmonized', 'both'], default=None)
    parser.add_argument('--apply', action='store_true', help='Apply changes after generation (will ask for confirmation)')
    parser.add_argument('--use-db', action='store_true', help='Use direct database update (FAST but bypasses DHIS2 validation)')
    parser.add_argument('--output', type=str, default=None, help='Output CSV path')

    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("  PHASE 2: TEI ID STANDARDISATION WORKFLOW")
    print("=" * 80)
    print(f"  Server: {DHIS2_URL}")
    print(f"  ⚠️  Read-only until you confirm to apply changes.\n")

    # Load org unit codes
    print("  📂 Loading org unit codes from Phase 1...", end='', flush=True)
    ou_list, ou_map = load_ou_codes()
    districts = [ou for ou in ou_list if ou['level'] == 3]
    print(f" ✅ {len(ou_list)} org units ({len(districts)} districts)")

    # ── Determine scope ──
    if args.org_unit:
        scope, scope_ids = 'single', [args.org_unit]
    elif args.district:
        codes = [c.strip().upper() for c in args.district.split(',')]
        scope_ids = []
        for code in codes:
            found = [ou['uid'] for ou in districts if ou['code'].upper() == code]
            if found:
                scope_ids.extend(found)
            else:
                print(f"  ❌ District code '{code}' not found. Available: {', '.join(d['code'] for d in sorted(districts, key=lambda x: x['name']))}")
                sys.exit(1)
        scope = 'district' if len(scope_ids) == 1 else 'districts'
    elif args.all:
        scope, scope_ids = 'all', []
    else:
        scope, scope_ids = interactive_select_scope(ou_list)

    # ── Determine program ──
    program_choice = args.program or interactive_pick_program()

    # ── Show configuration ──
    scope_label = {
        'single':    f"Single org unit: {ou_map.get(scope_ids[0], {}).get('name', scope_ids[0]) if scope_ids else 'N/A'}",
        'district':  f"District: {ou_map.get(scope_ids[0], {}).get('name', scope_ids[0]) if scope_ids else 'N/A'}",
        'districts': f"{len(scope_ids)} districts",
        'all':       "All org units",
    }

    print(f"\n  ── Configuration ──")
    print(f"  Scope:      {scope_label.get(scope, scope)}")
    print(f"  Program:    {program_choice}")
    print(f"  Update:     4 async connections (mergeMode=MERGE)")

    # ── Resolve target org units ──
    print(f"\n  Resolving target org units...", flush=True)
    target_uids = resolve_target_org_units(scope, scope_ids, ou_map)

    if target_uids is not None:
        print(f"  Target org units: {len(target_uids)}")

    # ── Determine output file ──
    if args.output:
        output_file = args.output
    elif scope == 'single':
        ou_info = ou_map.get(scope_ids[0], {})
        ou_code = ou_info.get('code', scope_ids[0])
        output_file = f"{OUTPUT_DIR}/id_mapping_{ou_code.lower()}.csv"
    elif scope in ('district', 'districts'):
        district_codes = [ou_map.get(uid, {}).get('code', uid).lower() for uid in scope_ids]
        output_file = f"{OUTPUT_DIR}/id_mapping_{'_'.join(district_codes)}.csv"
    else:
        output_file = f"{OUTPUT_DIR}/id_mapping_all.csv"

    print(f"  Output CSV: {output_file}")

    # ── STEP 1: Generate IDs ──────────────────────────────────────────────────
    print(f"\n  {'=' * 70}")
    print(f"  STEP 1: GENERATING IDs")
    print(f"  {'=' * 70}")

    all_results = []

    if program_choice in ['household', 'both']:
        results = process_program('household', target_uids, ou_map)
        all_results.extend(results)

    if program_choice in ['harmonized', 'both']:
        results = process_program('harmonized', target_uids, ou_map)
        all_results.extend(results)

    if not all_results:
        print("\n  ⚠️  No TEIs found for the selected scope. Nothing to do.")
        sys.exit(0)

    # ── Save mapping CSV ──
    save_mapping_csv(all_results, output_file)
    print(f"\n  💾 Mapping saved: {output_file}")

    # ── STEP 2: Preview ───────────────────────────────────────────────────────
    print(f"\n  {'=' * 70}")
    print(f"  STEP 2: PREVIEW")
    print(f"  {'=' * 70}")
    preview_changes(all_results)

    # ── STEP 3: Apply? ────────────────────────────────────────────────────────
    changed_count = sum(1 for r in all_results if r['changed'])
    if changed_count == 0:
        print("  ✅ All IDs are already correct. Nothing to apply.")
        sys.exit(0)

    if args.apply:
        do_apply = True
        use_db = args.use_db
    else:
        print(f"  {'=' * 70}")
        print(f"  STEP 3: APPLY CHANGES")
        print(f"  {'=' * 70}")
        print(f"\n  ⚠️  This will update {changed_count} TEIs.")
        print(f"\n  ── Select Update Method ──")
        print(f"    1. API   — DHIS2 REST API (safe, ~{changed_count // 8} min)")
        print(f"    2. DB    — Direct database update (fast, ~5s)")
        print(f"    3. Cancel\n")
        method = input("  Pick method (1-3): ").strip()

        if method == '1':
            do_apply = True
            use_db = False
        elif method == '2':
            do_apply = True
            use_db = True
        else:
            do_apply = False
            use_db = False

    if do_apply:
        success, errors = apply_changes(output_file, use_db=use_db)
        print(f"\n  {'=' * 70}")
        print(f"  ✅ WORKFLOW COMPLETE")
        print(f"  {'=' * 70}")
        print(f"  Applied: {success} success, {errors} errors")
        print(f"  Mapping: {output_file}")

        # Auto-verify after DB update
        if use_db and success > 0:
            print(f"\n  {'=' * 70}")
            print(f"  STEP 4: VERIFY DATABASE CHANGES")
            print(f"  {'=' * 70}")
            from cleanup.phase2.db_update import verify_changes
            program_attributes = {
                'household': PROGRAMS['household']['id_attribute'],
                'harmonized': PROGRAMS['harmonized']['id_attribute'],
            }
            verify_changes(output_file, program_attributes)
    else:
        print(f"\n  ❌ Cancelled. No changes made.")
        print(f"\n  To apply later:")
        print(f"  ./venv/bin/python src/phase2/apply_ids.py --csv {output_file}")
        print(f"  ./venv/bin/python src/phase2/apply_ids.py --csv {output_file} --use-db")

    print(f"{'=' * 80}\n")


if __name__ == '__main__':
    main()