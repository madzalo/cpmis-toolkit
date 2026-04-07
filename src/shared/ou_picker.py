"""
Shared interactive organisation unit picker for CPMIS Toolkit.
Extracted from cleanup Phase 2 for cross-app reuse.
"""
import csv
import os


def load_ou_codes(csv_file='outputs/task1/ou_codes_standardized.csv'):
    """
    Load org unit codes from Phase 1 CSV.

    Returns:
        (ou_list, ou_map) where:
            ou_list: list of dicts with uid, name, code, level
            ou_map: dict of uid -> dict
    """
    ou_list = []
    ou_map = {}

    if not os.path.exists(csv_file):
        print(f"  ❌ CSV file not found: {csv_file}")
        print(f"     Run Phase 1 first: just task1-complete")
        return ou_list, ou_map

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


def search_and_pick_ou(ou_list, prompt_label="Search org unit"):
    """
    Interactive search-and-pick for a single org unit.

    Returns:
        (uid, name) of selected org unit, or ('done', 'done') if user types 'done'.
    """
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
                print(f"  ✅ Selected: {sel['name']} ({sel['uid']})")
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
