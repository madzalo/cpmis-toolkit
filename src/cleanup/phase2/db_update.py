"""
Direct database update for TEI attributes.
FAST: Updates all TEIs in seconds instead of minutes via API.
WARNING: Bypasses DHIS2 validation and audit logs. Use with caution.
"""

import csv
import time
import datetime
import psycopg2
from psycopg2.extras import execute_batch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.settings import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD


def get_db_connection():
    """Create PostgreSQL connection to DHIS2 database."""
    if not all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD]):
        raise ValueError(
            "Database credentials not configured. Set DB_HOST, DB_NAME, "
            "DB_USER, DB_PASSWORD in .env file."
        )

    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


def get_tei_id_from_uid(cursor, tei_uid):
    """Convert TEI UID to internal database ID."""
    cursor.execute(
        "SELECT trackedentityinstanceid FROM trackedentityinstance WHERE uid = %s",
        (tei_uid,)
    )
    result = cursor.fetchone()
    return result[0] if result else None


def get_attribute_id_from_uid(cursor, attribute_uid):
    """Convert attribute UID to internal database ID."""
    cursor.execute(
        "SELECT trackedentityattributeid, name FROM trackedentityattribute WHERE uid = %s",
        (attribute_uid,)
    )
    result = cursor.fetchone()
    return (result[0], result[1]) if result else (None, None)


def apply_changes_via_db(csv_file, program_attribute_map):
    """
    Apply TEI attribute updates directly via PostgreSQL.

    Args:
        csv_file: Path to CSV with columns: tei_uid, program, new_id, changed
        program_attribute_map: Dict mapping program key to attribute UID
                              e.g., {'household': 'SYUXY9pax4w', 'harmonized': 'cxr1eaTGEBO'}

    Returns:
        (success_count, error_count)
    """
    if not os.path.exists(csv_file):
        print(f"  ❌ CSV file not found: {csv_file}")
        return 0, 0

    # ── Read CSV ──────────────────────────────────────────────────────────
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        mappings = [r for r in reader if r.get('changed') == 'True']

    if not mappings:
        print("  ℹ️  No changes to apply.")
        return 0, 0

    total = len(mappings)

    # Count per program
    programs_in_csv = {}
    for row in mappings:
        p = row['program']
        programs_in_csv[p] = programs_in_csv.get(p, 0) + 1

    # ── Connect to database ───────────────────────────────────────────────
    print(f"\n  {'─' * 60}")
    print(f"  DATABASE DIRECT UPDATE")
    print(f"  {'─' * 60}")
    print(f"  Host:     {DB_HOST}:{DB_PORT}")
    print(f"  Database: {DB_NAME}")
    print(f"  User:     {DB_USER}")
    print(f"  CSV:      {csv_file}")
    print(f"  TEIs:     {total}")
    for p, count in programs_in_csv.items():
        print(f"            {p}: {count}")
    print(f"  {'─' * 60}")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        print(f"\n  ✅ Connected to {DB_NAME}@{DB_HOST}")
    except Exception as e:
        print(f"\n  ❌ Connection failed: {e}")
        return 0, 0

    # ── Resolve attribute UIDs to internal IDs ────────────────────────────
    print(f"\n  Resolving attribute UIDs...")
    attribute_id_cache = {}
    for program, attr_uid in program_attribute_map.items():
        if program not in programs_in_csv:
            continue
        attr_id, attr_name = get_attribute_id_from_uid(cursor, attr_uid)
        if not attr_id:
            print(f"  ❌ Attribute not found: {attr_uid} ({program})")
            cursor.close()
            conn.close()
            return 0, 0
        attribute_id_cache[program] = attr_id
        print(f"  ✅ {program}: {attr_name} (UID: {attr_uid} → ID: {attr_id})")

    # ── Batch-resolve TEI UIDs to internal IDs ────────────────────────────
    # Instead of 1 query per TEI, we batch 500 UIDs per query → 100x faster
    unique_uids = list({row['tei_uid'] for row in mappings})
    uid_count = len(unique_uids)
    batch_size = 500
    print(f"\n  Resolving {uid_count} TEI UIDs to database IDs ({batch_size}/batch)...")
    prep_start = time.time()
    tei_id_cache = {}
    not_found_uids = []

    for start in range(0, uid_count, batch_size):
        batch = unique_uids[start:start + batch_size]
        cursor.execute(
            "SELECT uid, trackedentityinstanceid FROM trackedentityinstance WHERE uid IN %s",
            (tuple(batch),)
        )
        for uid, tei_id in cursor.fetchall():
            tei_id_cache[uid] = tei_id

        done = min(start + batch_size, uid_count)
        elapsed = time.time() - prep_start
        rate = done / elapsed if elapsed > 0 else 0
        pct = done * 100 // uid_count
        print(
            f"\r  🔍 [{done}/{uid_count}] {pct}% — {rate:.0f} UIDs/s".ljust(70),
            end='', flush=True
        )

    # Identify not-found UIDs
    for uid in unique_uids:
        if uid not in tei_id_cache:
            not_found_uids.append(uid)

    # Build update list
    updates = []
    update_details = []
    skipped = 0

    for row in mappings:
        tei_uid = row['tei_uid']
        program = row['program']
        new_id = row['new_id']
        old_id = row.get('current_id', '')

        tei_id = tei_id_cache.get(tei_uid)
        if not tei_id:
            skipped += 1
            continue

        attribute_id = attribute_id_cache.get(program)
        if not attribute_id:
            skipped += 1
            continue

        updates.append((tei_id, attribute_id, new_id))
        update_details.append((tei_uid, program, old_id, new_id))

    prep_elapsed = time.time() - prep_start
    print(f"\r  ✅ Resolved {len(tei_id_cache)}/{uid_count} TEIs in {prep_elapsed:.1f}s".ljust(70))

    if skipped:
        print(f"  ⚠️  {skipped} TEIs skipped (not found in database)")
        if not_found_uids:
            for uid in not_found_uids:
                print(f"     - {uid}")
            if skipped > 5:
                print(f"     ... and {skipped - 5} more")

    if not updates:
        print(f"\n  ❌ No valid updates to apply.")
        cursor.close()
        conn.close()
        return 0, skipped

    # ── Preview & Confirm ─────────────────────────────────────────────────
    print(f"\n  {'─' * 60}")
    print(f"  READY TO UPDATE")
    print(f"  {'─' * 60}")
    print(f"  Database:  {DB_NAME}@{DB_HOST}")
    print(f"  Table:     trackedentityattributevalue")
    print(f"  Operation: UPSERT (insert or update)")
    print(f"  Total:     {len(updates)} attribute values")
    print(f"  Skipped:   {skipped}")
    print(f"  {'─' * 60}")
    print(f"\n  ⚠️  This will directly modify {len(updates)} rows in the database.")
    print(f"  ⚠️  This CANNOT be undone without a database backup.\n")

    confirm = input("  Proceed with database update? (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print(f"\n  ❌ Cancelled. No changes made to the database.")
        cursor.close()
        conn.close()
        return 0, 0

    # ── Execute batch update with real-time progress ────────────────────
    total_updates = len(updates)
    batch_size = 500
    print(f"\n  🚀 Executing batch update ({total_updates} rows, batch size {batch_size})...\n")
    exec_start = time.time()

    try:
        sql = """
            INSERT INTO trackedentityattributevalue
                (trackedentityinstanceid, trackedentityattributeid, value, created, lastupdated, storedby)
            VALUES (%s, %s, %s, NOW(), NOW(), 'cpmis-cleanup')
            ON CONFLICT (trackedentityinstanceid, trackedentityattributeid)
            DO UPDATE SET
                value = EXCLUDED.value,
                lastupdated = NOW(),
                storedby = 'cpmis-cleanup'
        """

        done = 0
        for start in range(0, total_updates, batch_size):
            batch = updates[start:start + batch_size]
            execute_batch(cursor, sql, batch, page_size=batch_size)
            done += len(batch)
            elapsed = time.time() - exec_start
            rate = done / elapsed if elapsed > 0 else 0
            pct = done * 100 // total_updates
            remaining = (total_updates - done) / rate if rate > 0 else 0
            eta_str = f"{remaining:.0f}s" if remaining < 60 else f"{remaining / 60:.1f}m"
            print(
                f"\r  🚀 [{done}/{total_updates}] {pct}% — {rate:.0f} rows/s — ETA: {eta_str}".ljust(70),
                end='', flush=True
            )

        conn.commit()
        print(f"\r  ✅ [{done}/{total_updates}] 100% — committed".ljust(70))

        exec_elapsed = time.time() - exec_start
        total_elapsed = time.time() - prep_start
        success = len(updates)
        rate = success / exec_elapsed if exec_elapsed > 0 else 0

        # ── Save update log ─────────────────────────────────────────────
        log_file = _save_update_log(csv_file, update_details)

        # ── Summary ───────────────────────────────────────────────────────
        print(f"\n  {'═' * 60}")
        print(f"  DATABASE UPDATE COMPLETE")
        print(f"  {'═' * 60}")
        print(f"  Database:   {DB_NAME}@{DB_HOST}")
        print(f"  Updated:    {success}")
        print(f"  Skipped:    {skipped}")
        print(f"  Resolve:    {prep_elapsed:.1f}s")
        print(f"  Execute:    {exec_elapsed:.1f}s ({rate:.0f} rows/s)")
        print(f"  Total:      {total_elapsed:.1f}s")
        print(f"  Log:        {log_file}")
        print(f"  {'═' * 60}")
        print(f"\n  To verify: ./venv/bin/python src/phase2/apply_ids.py --csv {csv_file} --verify")

        cursor.close()
        conn.close()

        return success, skipped

    except Exception as e:
        print(f"\n\n  ❌ Database update failed: {e}")
        print(f"  ↩️  Rolling back all changes...")
        conn.rollback()
        cursor.close()
        conn.close()
        print(f"  ✅ Rollback complete. No changes were made.")
        return 0, total


def _save_update_log(csv_file, update_details):
    """Save a log of all updates applied to the database."""
    base = os.path.splitext(csv_file)[0]
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f"{base}_db_log_{timestamp}.csv"

    with open(log_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['tei_uid', 'program', 'old_value', 'new_value', 'timestamp'])
        ts = datetime.datetime.now().isoformat()
        for tei_uid, program, old_id, new_id in update_details:
            writer.writerow([tei_uid, program, old_id, new_id, ts])

    print(f"\n  📄 Update log saved: {log_file} ({len(update_details)} rows)")
    return log_file


def verify_changes(csv_file, program_attribute_map):
    """
    Verify that database values match expected values from the CSV.

    Reads the CSV, queries the database for actual values, and compares.
    """
    if not os.path.exists(csv_file):
        print(f"  ❌ CSV file not found: {csv_file}")
        return

    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        mappings = [r for r in reader if r.get('changed') == 'True']

    if not mappings:
        print("  ℹ️  No changed rows in CSV to verify.")
        return

    total = len(mappings)

    print(f"\n  {'─' * 60}")
    print(f"  DATABASE VERIFICATION")
    print(f"  {'─' * 60}")
    print(f"  Database: {DB_NAME}@{DB_HOST}")
    print(f"  CSV:      {csv_file}")
    print(f"  TEIs:     {total}")
    print(f"  {'─' * 60}")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        print(f"\n  ✅ Connected to {DB_NAME}@{DB_HOST}")
    except Exception as e:
        print(f"\n  ❌ Connection failed: {e}")
        return

    # Resolve attribute UIDs
    attribute_id_cache = {}
    for program, attr_uid in program_attribute_map.items():
        attr_id, attr_name = get_attribute_id_from_uid(cursor, attr_uid)
        if attr_id:
            attribute_id_cache[program] = attr_id

    # Batch-verify: fetch all relevant attribute values in batches
    print(f"\n  Verifying {total} TEIs against database...")
    verify_start = time.time()

    # Group by attribute and collect UIDs
    uid_program_map = {}  # tei_uid -> [(program, expected)]
    for row in mappings:
        tei_uid = row['tei_uid']
        program = row['program']
        expected = row['new_id']
        uid_program_map.setdefault(tei_uid, []).append((program, expected))

    unique_uids = list(uid_program_map.keys())
    uid_count = len(unique_uids)
    batch_size = 500

    # Batch-fetch actual values: {(tei_uid, attr_id): value}
    actual_values = {}
    attr_ids = list(attribute_id_cache.values())

    for start in range(0, uid_count, batch_size):
        batch = unique_uids[start:start + batch_size]
        cursor.execute(
            """
            SELECT tei.uid, teav.trackedentityattributeid, teav.value
            FROM trackedentityattributevalue teav
            JOIN trackedentityinstance tei ON tei.trackedentityinstanceid = teav.trackedentityinstanceid
            WHERE tei.uid IN %s AND teav.trackedentityattributeid IN %s
            """,
            (tuple(batch), tuple(attr_ids))
        )
        for uid, attr_id, value in cursor.fetchall():
            actual_values[(uid, attr_id)] = value

        done = min(start + batch_size, uid_count)
        elapsed = time.time() - verify_start
        rate = done / elapsed if elapsed > 0 else 0
        pct = done * 100 // uid_count
        print(
            f"\r  🔍 [{done}/{uid_count}] {pct}% — {rate:.0f} UIDs/s".ljust(70),
            end='', flush=True
        )

    # Compare
    matched = 0
    mismatched = []
    not_found = 0

    for row in mappings:
        tei_uid = row['tei_uid']
        program = row['program']
        expected = row['new_id']
        attr_id = attribute_id_cache.get(program)

        if not attr_id:
            not_found += 1
            continue

        actual = actual_values.get((tei_uid, attr_id))
        if actual is None:
            not_found += 1
            mismatched.append((tei_uid, program, expected, '<NOT FOUND>'))
        elif actual == expected:
            matched += 1
        else:
            mismatched.append((tei_uid, program, expected, actual))

    elapsed = time.time() - verify_start
    cursor.close()
    conn.close()

    # ── Results ──────────────────────────────────────────────────────────
    print(f"\r  {'═' * 60}".ljust(70))
    print(f"  VERIFICATION RESULTS")
    print(f"  {'═' * 60}")
    print(f"  Total checked: {total}")
    print(f"  ✅ Matched:    {matched}")
    print(f"  ❌ Mismatched: {len(mismatched)}")
    print(f"  ⚠️  Not found:  {not_found}")
    print(f"  Time:          {elapsed:.1f}s")
    print(f"  {'═' * 60}")

    if mismatched:
        print(f"\n  Mismatched rows (first 20):")
        print(f"  {'TEI UID':<14} {'Program':<12} {'Expected':<32} {'Actual'}")
        print(f"  {'─' * 80}")
        for tei_uid, program, expected, actual in mismatched[:20]:
            print(f"  {tei_uid:<14} {program:<12} {expected:<32} {actual}")
        if len(mismatched) > 20:
            print(f"  ... and {len(mismatched) - 20} more")
    else:
        print(f"\n  ✅ All {matched} values match! Database is consistent with CSV.")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Direct database update/verify for TEI attributes')
    parser.add_argument('csv_file', help='Path to the ID mapping CSV')
    parser.add_argument('--verify', action='store_true', help='Verify DB values match CSV')
    args = parser.parse_args()

    PROGRAM_ATTRIBUTES = {
        'household': 'SYUXY9pax4w',
        'harmonized': 'cxr1eaTGEBO',
    }

    if args.verify:
        verify_changes(args.csv_file, PROGRAM_ATTRIBUTES)
    else:
        apply_changes_via_db(args.csv_file, PROGRAM_ATTRIBUTES)
