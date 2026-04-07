"""
Selection Logic — Interactive TEI selection and transfer preview.
User selects which TEIs to KEEP; everything else is transferred.
"""
import csv
import os

from shared.id_utils import PROGRAMS, extract_current_id, get_tei_display_name


def display_tei_summary(household_teis, child_teis, hh_to_children, child_to_hh):
    """Display a summary of fetched TEIs and their relationships."""
    hh_attr = PROGRAMS['household']['id_attribute']
    child_attr = PROGRAMS['harmonized']['id_attribute']

    print(f"\n  {'═' * 70}")
    print(f"  TEI SUMMARY")
    print(f"  {'═' * 70}")
    print(f"  Households:   {len(household_teis)}")
    print(f"  Children:     {len(child_teis)}")
    print(f"  Total:        {len(household_teis) + len(child_teis)}")

    linked = sum(1 for c in child_teis if c['trackedEntityInstance'] in child_to_hh)
    orphaned = len(child_teis) - linked
    print(f"  Linked children: {linked}")
    if orphaned:
        print(f"  ⚠️  Unlinked children: {orphaned}")

    # Show households with their children
    print(f"\n  {'─' * 70}")
    print(f"  HOUSEHOLDS & CHILDREN")
    print(f"  {'─' * 70}")

    tei_map = {}
    for t in household_teis + child_teis:
        tei_map[t['trackedEntityInstance']] = t

    for i, hh_tei in enumerate(household_teis, 1):
        hh_uid = hh_tei['trackedEntityInstance']
        hh_id = extract_current_id(hh_tei, hh_attr) or '(no ID)'
        hh_name = get_tei_display_name(hh_tei, 'household')
        children = hh_to_children.get(hh_uid, set())
        print(f"\n    {i:3d}. 🏠 {hh_name:<25} {hh_id:<30} ({hh_uid})")
        if children:
            for child_uid in sorted(children):
                child_tei = tei_map.get(child_uid, {})
                child_id = extract_current_id(child_tei, child_attr) or '(no ID)'
                child_name = get_tei_display_name(child_tei, 'harmonized')
                print(f"         └─ 👶 {child_name:<25} {child_id:<30} ({child_uid})")
        else:
            print(f"         └─ (no linked children)")

    # Show orphaned children
    orphaned_children = [
        t for t in child_teis
        if t['trackedEntityInstance'] not in child_to_hh
    ]
    if orphaned_children:
        print(f"\n  {'─' * 70}")
        print(f"  UNLINKED CHILDREN (no household relationship)")
        print(f"  {'─' * 70}")
        for i, child_tei in enumerate(orphaned_children, 1):
            child_uid = child_tei['trackedEntityInstance']
            child_id = extract_current_id(child_tei, PROGRAMS['harmonized']['id_attribute']) or '(no ID)'
            child_name = get_tei_display_name(child_tei, 'harmonized')
            print(f"    {i:3d}. 👶 {child_name:<25} {child_id:<30} ({child_uid})")


def interactive_select_keep(household_teis, child_teis, hh_to_children, child_to_hh):
    """
    Interactive selection: user picks TEIs to KEEP or TRANSFER.
    Supports two modes:
      1. Select TEIs to KEEP (everything else transfers)
      2. Select TEIs to TRANSFER (everything else stays)

    Returns:
        set of TEI UIDs to keep at source (None = cancel)
    """
    hh_attr = PROGRAMS['household']['id_attribute']
    child_attr = PROGRAMS['harmonized']['id_attribute']

    all_teis = household_teis + child_teis
    total = len(all_teis)

    # ── Choose selection mode ──
    print(f"\n  {'═' * 70}")
    print(f"  SELECTION MODE")
    print(f"  {'═' * 70}")
    print(f"    1. Select TEIs to KEEP at source (default)")
    print(f"       → Everything NOT selected will be TRANSFERRED")
    print(f"    2. Select TEIs to TRANSFER")
    print(f"       → Everything NOT selected will be KEPT")
    print(f"  {'═' * 70}")

    while True:
        mode = input("  Choose mode (1 or 2) [1]: ").strip() or '1'
        if mode in ('1', '2'):
            break
        print("  ⚠️  Enter 1 or 2.")

    select_to_transfer = (mode == '2')
    mode_label = "TRANSFER" if select_to_transfer else "KEEP"

    print(f"\n  {'═' * 70}")
    print(f"  SELECT TEIs TO {mode_label}")
    print(f"  {'═' * 70}")
    print(f"  Total TEIs: {total}")
    print(f"  Enter numbers of TEIs to {mode_label} (separated by commas).")
    if select_to_transfer:
        print(f"  Everything NOT selected will STAY at source.")
    else:
        print(f"  Everything NOT selected will be TRANSFERRED.")
    print(f"  Linked households/children are automatically handled.")
    print(f"  Enter 'none' to {mode_label} nothing, or 'cancel' to abort.\n")

    # Build numbered list
    hh_uid_set = {t['trackedEntityInstance'] for t in household_teis}
    numbered = []
    for i, tei in enumerate(all_teis, 1):
        uid = tei['trackedEntityInstance']
        if uid in hh_uid_set:
            tei_type = 'HH'
            tei_id = extract_current_id(tei, hh_attr)
            tei_name = get_tei_display_name(tei, 'household')
        else:
            tei_type = 'OVC'
            tei_id = extract_current_id(tei, child_attr)
            tei_name = get_tei_display_name(tei, 'harmonized')
        numbered.append((i, uid, tei_type, tei_id or '(no ID)', tei_name))
        print(f"    {i:3d}. [{tei_type}] {tei_name:<25} {tei_id or '(no ID)':<30} ({uid})")

    while True:
        choice = input(f"\n  TEIs to {mode_label} (e.g., 1,3,5 or 'none' or 'cancel'): ").strip()

        if choice.lower() == 'cancel':
            return None

        if choice.lower() == 'none':
            if select_to_transfer:
                print(f"  ℹ️  No TEIs selected to transfer — ALL {total} will STAY at source.")
            else:
                print(f"  ℹ️  No TEIs selected to keep — ALL {total} will be TRANSFERRED.")
            confirm = input("  Confirm? (yes/no): ").strip().lower()
            if confirm in ('yes', 'y'):
                if select_to_transfer:
                    return set(t['trackedEntityInstance'] for t in all_teis)  # Keep all
                else:
                    return set()  # Transfer all
            continue

        try:
            indices = [int(n.strip()) for n in choice.split(',')]
            if all(1 <= n <= total for n in indices):
                selected_uids = {numbered[n - 1][1] for n in indices}
                selected_labels = [f"{numbered[n-1][2]}:{numbered[n-1][4]} ({numbered[n-1][3]})" for n in indices]

                if select_to_transfer:
                    # In transfer mode: selected = transfer, so keep = all - selected
                    keep_uids = {t['trackedEntityInstance'] for t in all_teis} - selected_uids
                    print(f"  ✅ Transferring: {', '.join(selected_labels)}")
                    print(f"  ✅ Keeping {len(keep_uids)} others at source")
                    return keep_uids
                else:
                    # In keep mode: selected = keep, transfer = all - selected
                    keep_uids = selected_uids
                    print(f"  ✅ Keeping: {', '.join(selected_labels)}")
                    return keep_uids
            else:
                print(f"  ⚠️  Numbers must be between 1 and {total}.")
        except ValueError:
            print(f"  ⚠️  Enter comma-separated numbers.")


def save_transfer_preview(transfer_teis, dest_ou_uid, dest_ou_name, output_dir='outputs/transfer'):
    """Save a CSV preview of what will be transferred."""
    os.makedirs(output_dir, exist_ok=True)
    preview_file = os.path.join(output_dir, 'transfer_preview.csv')

    hh_attr = PROGRAMS['household']['id_attribute']
    child_attr = PROGRAMS['harmonized']['id_attribute']

    with open(preview_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'tei_uid', 'tei_type', 'name', 'current_id', 'current_ou',
            'dest_ou_uid', 'dest_ou_name', 'enrollments', 'events'
        ])
        for tei in transfer_teis:
            uid = tei['trackedEntityInstance']
            current_ou = tei.get('orgUnit', '')

            # Determine type, name, and current ID
            hh_id = extract_current_id(tei, hh_attr)
            child_id = extract_current_id(tei, child_attr)
            if hh_id:
                tei_type = 'HH'
                current_id = hh_id
                name = get_tei_display_name(tei, 'household')
            elif child_id:
                tei_type = 'OVC'
                current_id = child_id
                name = get_tei_display_name(tei, 'harmonized')
            else:
                tei_type = '?'
                current_id = ''
                name = ''

            enrollments = len(tei.get('enrollments', []))
            events = sum(len(e.get('events', [])) for e in tei.get('enrollments', []))

            writer.writerow([
                uid, tei_type, name, current_id, current_ou,
                dest_ou_uid, dest_ou_name, enrollments, events
            ])

    print(f"  💾 Transfer preview saved: {preview_file}")
    return preview_file
