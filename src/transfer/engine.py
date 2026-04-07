"""
Transfer Engine — Executes the OU transfer for TEIs, enrollments, and events.
Uses POST to preserve createdBy metadata.
"""
import csv
import os
import sys
import time
import json
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.dhis2_client import api_post, api_get, DHIS2_URL, SESSION


def build_transfer_payload(tei, dest_ou_uid, id_mapping=None):
    """
    Build a full TEI payload for import with updated orgUnit on the TEI,
    all enrollments, and all events. Optionally update the ID attribute.

    Args:
        tei: full TEI dict (with enrollments/events)
        dest_ou_uid: destination org unit UID
        id_mapping: dict with 'attribute' and 'new_id' keys, or None

    Returns:
        dict: TEI payload ready for POST
    """
    payload = {
        'trackedEntityInstance': tei['trackedEntityInstance'],
        'trackedEntityType': tei.get('trackedEntityType', ''),
        'orgUnit': dest_ou_uid,
        'attributes': [],
        'enrollments': [],
    }

    # Copy attributes, updating the ID if needed
    for attr in tei.get('attributes', []):
        attr_copy = {
            'attribute': attr['attribute'],
            'value': attr.get('value', ''),
        }
        if id_mapping and attr['attribute'] == id_mapping['attribute']:
            attr_copy['value'] = id_mapping['new_id']
        payload['attributes'].append(attr_copy)

    # Copy enrollments and their events, updating orgUnit on each
    for enrollment in tei.get('enrollments', []):
        enr_copy = {
            'enrollment': enrollment['enrollment'],
            'program': enrollment['program'],
            'orgUnit': dest_ou_uid,
            'enrollmentDate': enrollment.get('enrollmentDate', ''),
            'incidentDate': enrollment.get('incidentDate', ''),
            'status': enrollment.get('status', 'ACTIVE'),
            'events': [],
        }

        for event in enrollment.get('events', []):
            evt_copy = {
                'event': event['event'],
                'program': event.get('program', enrollment['program']),
                'programStage': event.get('programStage', ''),
                'orgUnit': dest_ou_uid,
                'eventDate': event.get('eventDate', ''),
                'status': event.get('status', 'ACTIVE'),
                'dataValues': event.get('dataValues', []),
            }
            if event.get('dueDate'):
                evt_copy['dueDate'] = event['dueDate']
            enr_copy['events'].append(evt_copy)

        payload['enrollments'].append(enr_copy)

    return payload


def execute_transfer(transfer_teis, dest_ou_uid, id_mappings, output_dir='outputs/transfer'):
    """
    Execute the transfer of TEIs to the destination org unit.

    Uses POST /api/trackedEntityInstances with strategy=CREATE_AND_UPDATE
    to update existing TEIs while preserving createdBy.

    Args:
        transfer_teis: list of full TEI dicts
        dest_ou_uid: destination org unit UID
        id_mappings: list of id mapping dicts from id_generator
        output_dir: directory for saving transfer log

    Returns:
        (success_count, error_count, log_file)
    """
    os.makedirs(output_dir, exist_ok=True)

    # Build lookup for id_mappings
    id_map = {m['tei_uid']: m for m in id_mappings}

    total = len(transfer_teis)
    success_count = 0
    error_count = 0
    errors = []
    results = []

    total_events = sum(
        len(ev)
        for tei in transfer_teis
        for enr in tei.get('enrollments', [])
        for ev in [enr.get('events', [])]
    )

    print(f"\n  {'═' * 70}")
    print(f"  EXECUTING TRANSFER")
    print(f"  {'═' * 70}")
    print(f"  TEIs to transfer:  {total}")
    print(f"  Events to move:    {total_events}")
    print(f"  Destination:       {dest_ou_uid}")
    print(f"  Method:            POST (preserves createdBy)")
    print(f"  {'═' * 70}\n")

    start_time = time.time()

    for i, tei in enumerate(transfer_teis, 1):
        tei_uid = tei['trackedEntityInstance']
        mapping = id_map.get(tei_uid)

        payload = build_transfer_payload(tei, dest_ou_uid, mapping)

        # Count events in this TEI
        tei_events = sum(len(e.get('events', [])) for e in tei.get('enrollments', []))

        # POST with CREATE_AND_UPDATE strategy
        import_payload = {
            'trackedEntityInstances': [payload]
        }

        ok, resp = api_post(
            '/api/trackedEntityInstances',
            import_payload,
            params={
                'strategy': 'CREATE_AND_UPDATE',
                'mergeMode': 'MERGE',
            }
        )

        old_id = mapping['old_id'] if mapping else ''
        new_id = mapping['new_id'] if mapping else ''

        if ok:
            # Check response for import summaries
            response_data = resp.get('response', resp)
            imported = response_data.get('imported', 0)
            updated = response_data.get('updated', 0)
            ignored = response_data.get('ignored', 0)

            if ignored and not imported and not updated:
                error_count += 1
                import_summaries = response_data.get('importSummaries', [])
                err_desc = ''
                if import_summaries:
                    err_desc = import_summaries[0].get('description', 'Unknown error')
                errors.append(f"{tei_uid}: IGNORED - {err_desc}")
                results.append({
                    'tei_uid': tei_uid,
                    'status': 'ERROR',
                    'old_id': old_id,
                    'new_id': new_id,
                    'events': tei_events,
                    'error': err_desc[:200],
                })
            else:
                success_count += 1
                results.append({
                    'tei_uid': tei_uid,
                    'status': 'OK',
                    'old_id': old_id,
                    'new_id': new_id,
                    'events': tei_events,
                    'error': '',
                })
        else:
            error_count += 1
            err = resp.get('error', 'Unknown error')
            errors.append(f"{tei_uid}: {err}")
            results.append({
                'tei_uid': tei_uid,
                'status': 'ERROR',
                'old_id': old_id,
                'new_id': new_id,
                'events': tei_events,
                'error': str(err)[:200],
            })

        # Progress
        elapsed = time.time() - start_time
        rate = i / elapsed if elapsed > 0 else 0
        remaining = (total - i) / rate if rate > 0 else 0
        eta_str = f"{int(remaining // 60)}m{int(remaining % 60)}s"
        pct = i * 100 // total
        print(
            f"\r  🚀 [{i}/{total}] {pct}% — ✅ {success_count} ok  ❌ {error_count} err  "
            f"({rate:.1f} TEIs/s, ETA: {eta_str})".ljust(110),
            end='', flush=True
        )

    print()  # Newline after progress

    # Save transfer log
    log_file = _save_transfer_log(results, output_dir)

    # Summary
    elapsed = time.time() - start_time
    print(f"\n  {'═' * 70}")
    print(f"  TRANSFER COMPLETE")
    print(f"  {'═' * 70}")
    print(f"  Total:     {total}")
    print(f"  Success:   {success_count}")
    print(f"  Errors:    {error_count}")
    print(f"  Time:      {elapsed:.1f}s")
    print(f"  Log:       {log_file}")

    if errors:
        print(f"\n  Errors (first 10):")
        for err in errors[:10]:
            print(f"    ❌ {err}")
        if len(errors) > 10:
            print(f"    ... and {len(errors) - 10} more")

    return success_count, error_count, log_file


def _save_transfer_log(results, output_dir):
    """Save transfer results to a CSV log."""
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(output_dir, f'transfer_log_{timestamp}.csv')

    with open(log_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['tei_uid', 'status', 'old_id', 'new_id', 'events', 'error'])
        for r in results:
            writer.writerow([
                r['tei_uid'], r['status'], r['old_id'], r['new_id'],
                r['events'], r['error']
            ])

    return log_file
