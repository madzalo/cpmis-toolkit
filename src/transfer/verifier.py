"""
Verifier — Confirms TEIs were transferred correctly to the destination OU.
Checks TEI existence, org unit, IDs, events, and relationships.
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.dhis2_client import api_get
from shared.id_utils import PROGRAMS, extract_current_id


def verify_transfer(transfer_teis, id_mappings, dest_ou_uid, hh_to_children, child_to_hh):
    """
    Verify that all transferred TEIs exist at the destination with correct
    org unit, IDs, events, and intact relationships.

    Args:
        transfer_teis: list of TEI dicts that were transferred
        id_mappings: list of id mapping dicts from id_generator
        dest_ou_uid: destination org unit UID
        hh_to_children: dict hh_uid -> set(child_uids)
        child_to_hh: dict child_uid -> hh_uid

    Returns:
        dict with verification results
    """
    id_map = {m['tei_uid']: m for m in id_mappings}
    transfer_uids = {t['trackedEntityInstance'] for t in transfer_teis}

    total = len(transfer_teis)
    verified = 0
    ou_ok = 0
    ou_fail = 0
    id_ok = 0
    id_fail = 0
    events_ok = 0
    events_fail = 0
    not_found = 0
    relationship_ok = 0
    relationship_fail = 0
    errors = []

    # Count expected events
    expected_events_total = sum(
        len(ev)
        for tei in transfer_teis
        for enr in tei.get('enrollments', [])
        for ev in [enr.get('events', [])]
    )

    print(f"\n  [dim]{'─' * 70}[/dim]")
    print(f"  [bold]Verifying {total} TEIs[/bold] ({expected_events_total} events)")
    print(f"  [dim]{'─' * 70}[/dim]\n")

    start_time = time.time()

    for i, tei in enumerate(transfer_teis, 1):
        tei_uid = tei['trackedEntityInstance']
        mapping = id_map.get(tei_uid)

        # Determine program ID for fetching program-scoped attributes
        prog_id = ''
        if mapping:
            prog_id = PROGRAMS.get(mapping.get('program_key', ''), {}).get('id', '')

        # Fetch TEI from server (with program to get program-scoped attributes)
        fetch_params = {
            'fields': (
                'trackedEntityInstance,orgUnit,'
                'attributes[attribute,value],'
                'enrollments[enrollment,orgUnit,'
                'events[event,orgUnit,status]],'
                'relationships[relationship,from[trackedEntityInstance[trackedEntityInstance]],'
                'to[trackedEntityInstance[trackedEntityInstance]]]'
            )
        }
        if prog_id:
            fetch_params['program'] = prog_id

        data = api_get(f'/api/trackedEntityInstances/{tei_uid}.json', params=fetch_params)

        if data is None:
            not_found += 1
            errors.append(f"{tei_uid}: NOT FOUND on server")
            _print_progress(i, total, verified, not_found, len(errors), start_time)
            continue

        verified += 1
        tei_ok = True

        # Check org unit
        actual_ou = data.get('orgUnit', '')
        if actual_ou == dest_ou_uid:
            ou_ok += 1
        else:
            ou_fail += 1
            tei_ok = False
            errors.append(f"{tei_uid}: OU mismatch (expected {dest_ou_uid}, got {actual_ou})")

        # Check ID
        if mapping:
            expected_attr = mapping['attribute']
            expected_id = mapping['new_id']
            actual_id = extract_current_id(data, expected_attr)
            if actual_id == expected_id:
                id_ok += 1
            else:
                id_fail += 1
                tei_ok = False
                errors.append(f"{tei_uid}: ID mismatch (expected {expected_id}, got {actual_id})")

        # Check events org unit
        expected_event_count = sum(
            len(enr.get('events', []))
            for enr in tei.get('enrollments', [])
        )
        actual_events = []
        for enr in data.get('enrollments', []):
            # Check enrollment org unit
            enr_ou = enr.get('orgUnit', '')
            if enr_ou != dest_ou_uid:
                errors.append(
                    f"{tei_uid}: Enrollment {enr.get('enrollment','')} "
                    f"OU mismatch (expected {dest_ou_uid}, got {enr_ou})"
                )
                tei_ok = False

            for evt in enr.get('events', []):
                actual_events.append(evt)
                evt_ou = evt.get('orgUnit', '')
                if evt_ou != dest_ou_uid:
                    errors.append(
                        f"{tei_uid}: Event {evt.get('event','')} "
                        f"OU mismatch (expected {dest_ou_uid}, got {evt_ou})"
                    )
                    tei_ok = False

        if len(actual_events) >= expected_event_count:
            events_ok += 1
        else:
            events_fail += 1
            errors.append(
                f"{tei_uid}: Event count mismatch "
                f"(expected >={expected_event_count}, got {len(actual_events)})"
            )

        # Check relationships (informational only - not a critical error)
        if tei_uid in hh_to_children or tei_uid in child_to_hh:
            rel_found = False
            for rel in data.get('relationships', []):
                from_uid = (rel.get('from', {})
                            .get('trackedEntityInstance', {})
                            .get('trackedEntityInstance', ''))
                to_uid = (rel.get('to', {})
                          .get('trackedEntityInstance', {})
                          .get('trackedEntityInstance', ''))
                # Check relationship involves the expected partner
                if tei_uid in child_to_hh:
                    expected_hh = child_to_hh[tei_uid]
                    if from_uid == expected_hh or to_uid == expected_hh:
                        rel_found = True
                        break
                elif tei_uid in hh_to_children:
                    expected_children = hh_to_children[tei_uid]
                    if from_uid in expected_children or to_uid in expected_children:
                        rel_found = True
                        break

            if rel_found:
                relationship_ok += 1
            else:
                relationship_fail += 1
                # Don't add to errors - relationships are optional

        _print_progress(i, total, verified, not_found, len(errors), start_time)

    print()  # Newline after progress

    elapsed = time.time() - start_time

    # Summary
    print(f"\n  [dim]{'─' * 70}[/dim]")
    print(f"  [bold green]✓ Verification complete[/bold green]")
    print(f"  [dim]{'─' * 70}[/dim]")
    print(f"  ✅ {verified} found  ❌ {not_found} missing  ⏱️  {elapsed:.1f}s")
    if id_fail > 0 or ou_fail > 0:
        print(f"  ⚠️  ID issues: {id_fail}  OU issues: {ou_fail}")
    print(f"  [dim]{'─' * 70}[/dim]\n")

    if errors:
        print(f"  Critical Issues (first 10):")
        for err in errors[:10]:
            print(f"    ⚠️  {err}")
        if len(errors) > 10:
            print(f"    ... and {len(errors) - 10} more")
        print()
    elif not_found == 0:
        print(f"  [bold green]All {total} TEIs verified successfully![/bold green]\n")

    if relationship_fail > 0:
        print(f"  ℹ️  {relationship_fail} TEIs have missing relationships (not critical)\n")

    return {
        'total': total,
        'verified': verified,
        'not_found': not_found,
        'ou_ok': ou_ok,
        'ou_fail': ou_fail,
        'id_ok': id_ok,
        'id_fail': id_fail,
        'events_ok': events_ok,
        'events_fail': events_fail,
        'relationship_ok': relationship_ok,
        'relationship_fail': relationship_fail,
        'errors': errors,
    }


def _print_progress(current, total, verified, not_found, error_count, start_time):
    """Print inline progress."""
    elapsed = time.time() - start_time
    rate = current / elapsed if elapsed > 0 else 0
    remaining = (total - current) / rate if rate > 0 else 0
    eta_str = f"{int(remaining // 60)}m{int(remaining % 60)}s"
    pct = current * 100 // total
    print(
        f"\r  🔍 [{current}/{total}] {pct}% — ✅ {verified} verified  "
        f"❌ {not_found} missing  ⚠️  {error_count} issues  "
        f"(ETA: {eta_str})".ljust(110),
        end='', flush=True
    )
