import requests
import csv
import sys
import os
import time
import argparse

# Add parent directory to path to import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.settings import DHIS2_URL, DHIS2_USERNAME, DHIS2_PASSWORD

CSV_FILE = 'outputs/task1/ou_codes_standardized.csv'

# ─── Shared Session (reuses TCP/TLS connections = much faster) ──────────────
SESSION = requests.Session()
SESSION.auth = (DHIS2_USERNAME, DHIS2_PASSWORD)
SESSION.headers.update({'Content-Type': 'application/json'})


# ─── Load & Filter ─────────────────────────────────────────────────────────

def load_ou_rows(csv_file=CSV_FILE):
    """Load all org unit rows from the standardised CSV."""
    if not os.path.exists(csv_file):
        print(f"  ❌ {csv_file} not found. Run Phase 1 generation first.")
        sys.exit(1)
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return rows


def get_districts(rows):
    """Extract level-3 districts from the rows."""
    return [r for r in rows if r.get('ou_level') == '3']


def filter_by_district(rows, district_code):
    """Filter rows belonging to a district (code match or prefix match)."""
    code_upper = district_code.upper()
    filtered = []
    for r in rows:
        rc = r['standardised_code'].upper()
        if rc == code_upper or rc.startswith(code_upper + '_'):
            filtered.append(r)
    return filtered


def filter_by_uid(rows, uid):
    """Filter rows to a single org unit UID."""
    return [r for r in rows if r['dhis2_uid'] == uid]


# ─── Interactive Selection ─────────────────────────────────────────────────

def interactive_select_scope(rows):
    """Let user pick scope interactively."""
    districts = get_districts(rows)

    print("\n  ── Select Scope ──")
    print("    1. Single org unit")
    print("    2. Single district (all org units within)")
    print("    3. Multiple districts")
    print("    4. All org units")

    while True:
        choice = input("\n  Pick scope (1-4): ").strip()
        if choice == '1':
            return interactive_pick_ou(rows)
        elif choice == '2':
            return interactive_pick_district(districts, multi=False)
        elif choice == '3':
            return interactive_pick_district(districts, multi=True)
        elif choice == '4':
            return 'all', []
        print("  ⚠️  Enter 1-4.")


def interactive_pick_ou(rows):
    """Search and pick a single org unit."""
    while True:
        query = input("\n  🔍 Search org unit (name or code): ").strip().lower()
        if not query:
            continue
        matches = [r for r in rows if query in r['ou_name'].lower() or query in r['standardised_code'].lower()]
        if not matches:
            print("  No matches. Try again.")
            continue
        print(f"\n  Found {len(matches)} matches:")
        for i, r in enumerate(matches[:20], 1):
            print(f"    {i:>3}. {r['ou_name']:<40} L{r['ou_level']}  {r['standardised_code']:<12} ({r['dhis2_uid']})")
        if len(matches) > 20:
            print(f"    ... and {len(matches) - 20} more. Refine your search.")
        pick = input(f"\n  Pick a number (1-{min(len(matches), 20)}), or Enter to search again: ").strip()
        if pick.isdigit() and 1 <= int(pick) <= min(len(matches), 20):
            chosen = matches[int(pick) - 1]
            return 'single', [chosen['dhis2_uid']]


def interactive_pick_district(districts, multi=False):
    """Pick district(s) from numbered list."""
    print(f"\n  Available districts ({len(districts)}):")
    for i, d in enumerate(districts, 1):
        print(f"    {i:>3}. {d['ou_name']:<40} {d['standardised_code']:<12}")
    
    if multi:
        prompt = f"\n  Pick districts (comma-separated numbers, e.g., 1,3,5): "
    else:
        prompt = f"\n  Pick a district (1-{len(districts)}): "
    
    while True:
        pick = input(prompt).strip()
        if not pick:
            print("  ❌ Please enter a number.")
            continue
        
        # Parse comma-separated numbers
        try:
            if ',' in pick:
                numbers = [int(n.strip()) for n in pick.split(',')]
            else:
                numbers = [int(pick)]
            
            # Validate all numbers are in range
            if all(1 <= n <= len(districts) for n in numbers):
                selected = [districts[n - 1]['standardised_code'] for n in numbers]
                selected_names = [districts[n - 1]['ou_name'] for n in numbers]
                
                print(f"  ✅ Selected: {', '.join(selected_names)}")
                
                if multi or len(numbers) > 1:
                    return 'districts', selected
                else:
                    return 'district', selected
            else:
                print(f"  ❌ Invalid number(s). Please enter numbers between 1 and {len(districts)}.")
        except ValueError:
            print("  ❌ Invalid input. Please enter number(s) separated by commas.")


# ─── Push to DHIS2 ────────────────────────────────────────────────────────

def update_single_ou(ou_uid, ou_code, ou_name):
    """Update a single org unit via PATCH. Returns (success, error_msg)."""
    try:
        url = f"{DHIS2_URL}/api/organisationUnits/{ou_uid}"
        payload = {"code": ou_code, "name": ou_name}
        response = SESSION.patch(url, json=payload, timeout=30)
        if response.status_code in [200, 201, 204]:
            return True, None
        else:
            return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, str(e)[:80]


def push_rows(rows, dry_run=False, batch_size=1000):
    """Push org unit codes and names to DHIS2 using bulk metadata import with fallback."""
    # Filter out rows with no code
    valid = [r for r in rows if r.get('standardised_code')]
    skipped = len(rows) - len(valid)

    mode = "DRY RUN" if dry_run else "LIVE"
    print(f"\n  ── Pushing {len(valid)} org units ({mode}) ──")
    print(f"  Server: {DHIS2_URL}")
    if skipped:
        print(f"  Skipped (no code): {skipped}")
    print()

    success = 0
    errors = 0
    error_details = []
    start_time = time.time()

    if dry_run:
        # Dry run: just print what would be updated
        for i, row in enumerate(valid, 1):
            ou_level = row.get('ou_level', '?')
            ou_name = row['ou_name']
            ou_code = row['standardised_code']
            print(f"  [DRY RUN] [{i}/{len(valid)}] L{ou_level} {ou_name:<40} → code: {ou_code}")
            success += 1
    else:
        # Live mode: use bulk metadata import with batching
        processed = 0
        for batch_num, i in enumerate(range(0, len(valid), batch_size), 1):
            batch = valid[i:i + batch_size]
            processed += len(batch)
            
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (len(valid) - processed) / rate if rate > 0 else 0
            
            print(f"\r  [{processed}/{len(valid)}] Batch {batch_num} ({len(batch)} OUs) updating... ({rate:.1f}/s, ETA: {eta:.0f}s)".ljust(110), end='', flush=True)
            
            # Try bulk metadata import first
            bulk_ok = False
            try:
                url = f"{DHIS2_URL}/api/metadata"
                org_units = [
                    {"id": r['dhis2_uid'], "code": r['standardised_code'], "name": r['ou_name']}
                    for r in batch
                ]
                payload = {"organisationUnits": org_units}
                response = SESSION.post(url, json=payload, timeout=60)
                
                if response.status_code in [200, 201]:
                    result = response.json()
                    stats = result.get('stats', {})
                    updated = stats.get('updated', 0)
                    ignored = stats.get('ignored', 0)
                    
                    if updated > 0:
                        success += updated
                        if ignored > 0:
                            errors += ignored
                        bulk_ok = True
                        print(f"\r  [{processed}/{len(valid)}] Batch {batch_num} ✅ ({updated} updated, {ignored} ignored) ({rate:.1f}/s, ETA: {eta:.0f}s)".ljust(110), end='', flush=True)
            except requests.exceptions.Timeout:
                pass  # Fall through to individual PATCH
            except Exception:
                pass  # Fall through to individual PATCH
            
            # If bulk failed, fall back to individual PATCH requests
            if not bulk_ok:
                print(f"\r  [{processed}/{len(valid)}] Batch {batch_num} → individual updates ({len(batch)} OUs)...".ljust(110), end='', flush=True)
                for row in batch:
                    ou_uid = row['dhis2_uid']
                    ou_code = row['standardised_code']
                    ou_name = row['ou_name']
                    
                    ok, err = update_single_ou(ou_uid, ou_code, ou_name)
                    if ok:
                        success += 1
                    else:
                        errors += 1
                        error_details.append(f"{ou_uid} ({ou_name}): {err}")
                    
                    done = success + errors
                    elapsed = time.time() - start_time
                    rate = done / elapsed if elapsed > 0 else 0
                    eta = (len(valid) - done) / rate if rate > 0 else 0
                    print(f"\r  [{done}/{len(valid)}] Updating... ({rate:.1f}/s, ETA: {eta:.0f}s)".ljust(110), end='', flush=True)
        
        print()  # New line after progress

    elapsed = time.time() - start_time
    print(f"\n  {'DRY RUN ' if dry_run else ''}Summary:")
    print(f"  Total:     {len(valid)}")
    print(f"  Success:   {success}")
    print(f"  Errors:    {errors}")
    if skipped:
        print(f"  Skipped:   {skipped}")
    if not dry_run:
        print(f"  Time:      {elapsed:.1f}s")
        print(f"  Rate:      {success/elapsed:.1f} OUs/s")

    if error_details:
        print(f"\n  Errors:")
        for err in error_details[:10]:
            print(f"    ❌ {err}")
        if len(error_details) > 10:
            print(f"    ... and {len(error_details) - 10} more")

    if dry_run:
        print("\n  ℹ️  Dry run — no changes were made to DHIS2.")
    else:
        print(f"\n  ✅ Organisation unit codes updated in DHIS2!")

    return success, errors


# ─── Preview ────────────────────────────────────────────────────────────────

def preview_rows(rows):
    """Show a preview of what will be pushed."""
    valid = [r for r in rows if r.get('standardised_code')]
    by_level = {}
    for r in valid:
        lvl = r.get('ou_level', '?')
        by_level.setdefault(lvl, []).append(r)

    print(f"\n  ══════════════════════════════════════════════════════════════════════")
    print(f"  PREVIEW: {len(valid)} org units to update")
    print(f"  ══════════════════════════════════════════════════════════════════════")
    for lvl in sorted(by_level.keys()):
        items = by_level[lvl]
        sample = ', '.join(r['standardised_code'] for r in items[:5])
        suffix = f' ... +{len(items)-5} more' if len(items) > 5 else ''
        print(f"  L{lvl}: {len(items):>4} org units  ({sample}{suffix})")

    print(f"\n  Sample (first 15):")
    print(f"  {'Name':<40} {'Level':<6} {'Code':<15}")
    print(f"  {'─' * 65}")
    for r in valid[:15]:
        print(f"  {r['ou_name']:<40} L{r.get('ou_level', '?'):<5} {r['standardised_code']:<15}")
    if len(valid) > 15:
        print(f"  ... and {len(valid) - 15} more")
    print()


# ─── Validate ──────────────────────────────────────────────────────────────

def validate_codes_in_dhis2():
    """Validate that codes in DHIS2 match our CSV."""
    print("\n  📡 Validating codes in DHIS2...", end='', flush=True)

    rows = load_ou_rows()
    expected = {r['dhis2_uid']: r['standardised_code'] for r in rows}

    url = f"{DHIS2_URL}/api/organisationUnits.json"
    params = {'fields': 'id,code,name,level', 'paging': 'false'}
    response = SESSION.get(url, params=params)

    if response.status_code != 200:
        print(f" ❌ HTTP {response.status_code}")
        sys.exit(1)

    org_units = response.json().get('organisationUnits', [])
    print(f" ✅ {len(org_units)} org units fetched")

    matches = 0
    mismatches = 0
    missing = 0

    for ou in org_units:
        ou_uid = ou['id']
        dhis2_code = ou.get('code', '')
        expected_code = expected.get(ou_uid, '')
        if not expected_code:
            continue
        if dhis2_code == expected_code:
            matches += 1
        elif not dhis2_code:
            missing += 1
            print(f"  Missing: {ou['name']} (expected: {expected_code})")
        else:
            mismatches += 1
            print(f"  Mismatch: {ou['name']} — DHIS2: {dhis2_code}, Expected: {expected_code}")

    print(f"\n  Validation Summary:")
    print(f"  Matches:    {matches}")
    print(f"  Missing:    {missing}")
    print(f"  Mismatches: {mismatches}")

    if missing == 0 and mismatches == 0:
        print("\n  ✅ All codes match!")
    else:
        print("\n  ⚠️  Some codes need attention.")


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Push organisation unit codes to DHIS2')
    parser.add_argument('--dry-run', action='store_true', help='Simulate without making changes')
    parser.add_argument('--validate', action='store_true', help='Validate codes in DHIS2 against CSV')
    parser.add_argument('--csv', default=CSV_FILE, help='Path to CSV file with codes')
    parser.add_argument('--org-unit', type=str, help='Single org unit UID')
    parser.add_argument('--district', type=str, help='District code(s), comma-separated (e.g. "ZA" or "ZA,BL")')
    parser.add_argument('--all', action='store_true', help='Process all org units')

    args = parser.parse_args()

    if args.validate:
        validate_codes_in_dhis2()
        return

    print("\n" + "=" * 80)
    print("  PHASE 1: PUSH ORGANISATION UNIT CODES")
    print("=" * 80)
    print(f"  Server: {DHIS2_URL}")
    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"  Mode:   {mode}")

    # Load CSV
    print(f"\n  📂 Loading org unit codes...", end='', flush=True)
    all_rows = load_ou_rows(args.csv)
    districts = get_districts(all_rows)
    print(f" ✅ {len(all_rows)} org units ({len(districts)} districts)")

    # ── Determine scope ──
    if args.org_unit:
        scope = 'single'
        target_rows = filter_by_uid(all_rows, args.org_unit)
        if not target_rows:
            print(f"  ❌ Org unit '{args.org_unit}' not found in CSV.")
            sys.exit(1)
        scope_label = f"Single org unit: {target_rows[0]['ou_name']}"
    elif args.district:
        codes = [c.strip().upper() for c in args.district.split(',')]
        target_rows = []
        labels = []
        for code in codes:
            matched = [d for d in districts if d['standardised_code'].upper() == code]
            if not matched:
                print(f"  ❌ District code '{code}' not found. Available: {', '.join(d['standardised_code'] for d in sorted(districts, key=lambda x: x['ou_name']))}")
                sys.exit(1)
            filtered = filter_by_district(all_rows, code)
            target_rows.extend(filtered)
            labels.append(f"{matched[0]['ou_name']} ({code})")
        scope = 'district' if len(codes) == 1 else 'districts'
        scope_label = ', '.join(labels)
    elif args.all:
        scope = 'all'
        target_rows = all_rows
        scope_label = "All org units"
    else:
        # Interactive
        scope, scope_ids = interactive_select_scope(all_rows)
        if scope == 'single':
            target_rows = filter_by_uid(all_rows, scope_ids[0])
            scope_label = f"Single org unit: {target_rows[0]['ou_name']}" if target_rows else 'Unknown'
        elif scope in ('district', 'districts'):
            target_rows = []
            labels = []
            for code in scope_ids:
                filtered = filter_by_district(all_rows, code)
                target_rows.extend(filtered)
                matched = [d for d in districts if d['standardised_code'].upper() == code.upper()]
                name = matched[0]['ou_name'] if matched else code
                labels.append(f"{name} ({code})")
            scope_label = ', '.join(labels)
        else:
            target_rows = all_rows
            scope_label = "All org units"

    print(f"\n  ── Configuration ──")
    print(f"  Scope:     {scope_label}")
    print(f"  Org units: {len(target_rows)}")
    print(f"  Mode:      {mode}")

    # Preview
    preview_rows(target_rows)

    # Confirm if live
    if not args.dry_run:
        print(f"  ⚠️  This will update {len(target_rows)} org units on the live DHIS2 server.")
        confirm = input("  Proceed? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("\n  ❌ Cancelled. No changes made.")
            return

    # Push
    push_rows(target_rows, dry_run=args.dry_run)
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
