#!/usr/bin/env python3
"""
Apply generated IDs to Tracked Entity Instances in DHIS2.

This module contains:
- Program definitions (PROGRAMS) shared across Phase 2 scripts
- Functions for applying ID changes via DHIS2 API (async) or direct DB
- CLI entry point for standalone use

Usage:
    # Apply a previously generated mapping CSV (via API)
    python apply_ids.py --csv outputs/phase2/id_mapping_th.csv

    # Apply via direct database update
    python apply_ids.py --csv outputs/phase2/id_mapping_th.csv --use-db

    # Interactive mode (pick CSV → pick method → apply)
    python apply_ids.py --interactive
"""
import sys
import os
import csv
import time
import asyncio
import argparse
import glob
import requests
from requests.adapters import HTTPAdapter
import aiohttp

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


def interactive_select_csv():
    """List available mapping CSVs and let user pick one."""
    output_dir = 'outputs/phase2'
    csvs = sorted(glob.glob(f'{output_dir}/id_mapping_*.csv'))

    if not csvs:
        print(f"\n  ❌ No mapping CSVs found in {output_dir}/")
        print(f"  Run the Phase 2 workflow first to generate a mapping.")
        sys.exit(1)

    print(f"\n  ── Available Mapping CSVs ──")
    for i, path in enumerate(csvs, 1):
        # Count changed rows for context
        try:
            with open(path, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                total = len(rows)
                changed = sum(1 for r in rows if r.get('changed') == 'True')
            print(f"    {i}. {os.path.basename(path)}  ({total} TEIs, {changed} to change)")
        except Exception:
            print(f"    {i}. {os.path.basename(path)}")

    print()
    choice = input(f"  Pick CSV (1-{len(csvs)}): ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(csvs):
            return csvs[idx]
    except ValueError:
        pass

    print(f"  ❌ Invalid choice.")
    sys.exit(1)


def interactive_select_method(csv_file):
    """Let user pick the apply method interactively."""
    # Count changed rows
    try:
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            changed = sum(1 for r in reader if r.get('changed') == 'True')
    except Exception:
        changed = '?'

    print(f"\n  ── Select Update Method ──")
    print(f"  CSV: {csv_file}")
    print(f"  TEIs to update: {changed}")
    print(f"\n    1. API   — DHIS2 REST API (safe, recommended)")
    print(f"    2. DB    — Direct database update (fast, bypasses validation)")
    print(f"    3. Cancel\n")

    method = input("  Pick method (1-3): ").strip()
    if method == '1':
        return False  # use_db=False
    elif method == '2':
        return True   # use_db=True
    else:
        print(f"\n  ❌ Cancelled. No changes made.")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description='Apply generated IDs to DHIS2 via API or direct database update'
    )
    parser.add_argument(
        '--csv',
        required=False,
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
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Interactive mode: pick CSV and update method interactively'
    )

    args = parser.parse_args()

    # ── Interactive mode ──
    if args.interactive:
        csv_file = interactive_select_csv()
        use_db = interactive_select_method(csv_file)
    elif args.csv:
        csv_file = args.csv
        use_db = args.use_db
    else:
        parser.error("Either --csv or --interactive is required")

    if not os.path.exists(csv_file):
        print(f"\n  ❌ Mapping file not found: {csv_file}")
        sys.exit(1)

    # ── Verify mode ──
    if args.verify:
        from cleanup.phase2.db_update import verify_changes
        program_attributes = {
            'household': PROGRAMS['household']['id_attribute'],
            'harmonized': PROGRAMS['harmonized']['id_attribute'],
        }
        verify_changes(csv_file, program_attributes)
        sys.exit(0)

    # ── Apply mode ──
    method = "DATABASE UPDATE" if use_db else "API (ASYNC)"
    print(f"\n{'=' * 80}")
    print(f"  APPLY STANDARDISED IDs TO DHIS2 ({method})")
    print(f"{'=' * 80}")
    print(f"  Server: {DHIS2_URL}")
    print(f"  CSV: {csv_file}")
    print(f"  Method: {method}")

    # Confirmation (skip in interactive mode — user already confirmed by picking)
    if not args.interactive:
        if use_db:
            print(f"\n  ⚠️  WARNING: Direct database update bypasses DHIS2 validation!")
            print(f"  ⚠️  Ensure you have a database backup before proceeding!")
        else:
            print(f"\n  ⚠️  WARNING: This will MODIFY data on the live DHIS2 server!")
        confirm = input(f"  Continue? (yes/no): ")
        if confirm.lower() not in ['yes', 'y']:
            print(f"\n  ❌ Cancelled. No changes made.")
            sys.exit(0)

    success, errors = apply_changes(csv_file, use_db=use_db)

    print(f"\n{'=' * 80}")
    print(f"  ✅ COMPLETE")
    print(f"{'=' * 80}\n")

    sys.exit(1 if errors > 0 else 0)


if __name__ == '__main__':
    main()
