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
from shared.dhis2_client import api_post, api_put, api_get, DHIS2_URL, SESSION
from shared.id_utils import PROGRAMS


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
    id_attr_updated = False
    for attr in tei.get('attributes', []):
        attr_copy = {
            'attribute': attr['attribute'],
            'value': attr.get('value', ''),
        }
        if id_mapping and attr['attribute'] == id_mapping['attribute']:
            attr_copy['value'] = id_mapping['new_id']
            id_attr_updated = True
        payload['attributes'].append(attr_copy)

    # If ID attribute wasn't in original attributes, add it now
    if id_mapping and not id_attr_updated:
        payload['attributes'].append({
            'attribute': id_mapping['attribute'],
            'value': id_mapping['new_id'],
        })

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


def update_tei_attribute(tei_uid, attribute_uid, new_value, program_id=None):
    """
    Update a single attribute on a TEI using PUT.
    This is needed because the bulk POST import doesn't reliably update attributes.

    Args:
        tei_uid: TEI UID to update
        attribute_uid: attribute UID to set
        new_value: new attribute value
        program_id: DHIS2 program ID (required to fetch program-scoped attributes)

    Returns:
        (success: bool, error_msg: str)
    """
    # Fetch TEI with program to ensure program-scoped attributes are included
    fetch_params = {
        'fields': 'trackedEntityInstance,trackedEntityType,orgUnit,'
                  'attributes[attribute,value]'
    }
    if program_id:
        fetch_params['program'] = program_id

    data = api_get(f'/api/trackedEntityInstances/{tei_uid}.json', params=fetch_params)
    if data is None:
        return False, f"Could not fetch TEI {tei_uid} for attribute update"

    # Update the target attribute or add it
    attr_updated = False
    for attr in data.get('attributes', []):
        if attr.get('attribute') == attribute_uid:
            attr['value'] = new_value
            attr_updated = True
            break
    if not attr_updated:
        data.setdefault('attributes', []).append({
            'attribute': attribute_uid,
            'value': new_value,
        })

    # PUT the updated TEI
    put_payload = {
        'trackedEntityInstance': data['trackedEntityInstance'],
        'trackedEntityType': data.get('trackedEntityType', ''),
        'orgUnit': data.get('orgUnit', ''),
        'attributes': data.get('attributes', []),
    }

    ok, resp = api_put(
        f'/api/trackedEntityInstances/{tei_uid}',
        put_payload,
        params={'mergeMode': 'MERGE'}
    )
    if ok:
        return True, ''
    return False, resp.get('error', 'Unknown PUT error')


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
    print(f"  Method:            POST strategy=CREATE_AND_UPDATE, mergeMode=REPLACE")
    print(f"  {'═' * 70}\n")

    start_time = time.time()

    for i, tei in enumerate(transfer_teis, 1):
        tei_uid = tei['trackedEntityInstance']
        mapping = id_map.get(tei_uid)

        payload = build_transfer_payload(tei, dest_ou_uid, mapping)

        # Debug: Log attribute values being sent (first TEI only)
        if i == 1:
            print(f"\n  🔍 DEBUG - Sample payload for {tei_uid}:")
            print(f"     OrgUnit: {tei.get('orgUnit')} → {dest_ou_uid}")
            if mapping:
                print(f"     ID: {mapping['old_id']} → {mapping['new_id']}")
                print(f"     Attribute UID: {mapping['attribute']}")
                # Check if ID attribute exists in original TEI
                id_in_original = False
                for attr in tei.get('attributes', []):
                    if attr.get('attribute') == mapping['attribute']:
                        id_in_original = True
                        print(f"     ✓ ID attribute found in original TEI: '{attr.get('value', '')}'")
                        break
                if not id_in_original:
                    print(f"     ⚠️  ID attribute NOT in original TEI - will be added")
            print(f"     Attributes in original TEI: {len(tei.get('attributes', []))}")
            print(f"     Attributes in payload: {len(payload.get('attributes', []))}")
            for attr in payload.get('attributes', []):
                if mapping and attr.get('attribute') == mapping['attribute']:
                    print(f"       → ID Attribute in payload: {attr['attribute']} = '{attr['value']}'")
            print()

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
                'mergeMode': 'REPLACE',
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

            # Log import summary details for debugging
            import_summaries = response_data.get('importSummaries', [])
            if import_summaries:
                summary = import_summaries[0]
                status = summary.get('status', 'UNKNOWN')
                description = summary.get('description', '')
                if status != 'SUCCESS' or description:
                    print(f"\n    ⚠️  {tei_uid}: {status} - {description}")

            if ignored and not imported and not updated:
                error_count += 1
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
                # Step 2: Update ID attribute via PUT (POST doesn't update attributes reliably)
                id_err = ''
                if mapping:
                    prog_id = PROGRAMS.get(mapping.get('program_key', ''), {}).get('id', '')
                    attr_ok, attr_err = update_tei_attribute(
                        tei_uid, mapping['attribute'], mapping['new_id'], program_id=prog_id
                    )
                    if not attr_ok:
                        id_err = f"OU moved OK, but ID update failed: {attr_err}"
                        errors.append(f"{tei_uid}: {id_err}")

                success_count += 1
                results.append({
                    'tei_uid': tei_uid,
                    'status': 'OK' if not id_err else 'PARTIAL',
                    'old_id': old_id,
                    'new_id': new_id,
                    'events': tei_events,
                    'error': id_err,
                })
        else:
            error_count += 1
            err = resp.get('error', 'Unknown error')
            
            # For HTTP 409, try to extract more details
            if '409' in str(err):
                import_summaries = resp.get('response', {}).get('importSummaries', [])
                if import_summaries:
                    summary = import_summaries[0]
                    conflicts = summary.get('conflicts', [])
                    if conflicts:
                        conflict_details = '; '.join([c.get('value', '') for c in conflicts])
                        err = f"{err} | Conflicts: {conflict_details}"
                        print(f"\n    ❌ {tei_uid}: {conflict_details}")
            
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
