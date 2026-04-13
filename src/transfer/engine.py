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
from shared.id_utils import PROGRAMS


def build_transfer_payload(tei, dest_ou_uid):
    """
    Build a full TEI payload for import with updated orgUnit on the TEI,
    all enrollments, and all events. Attributes are kept as-is (the ID
    attribute is updated in a separate PUT step to avoid unique-constraint
    conflicts).

    Args:
        tei: full TEI dict (with enrollments/events)
        dest_ou_uid: destination org unit UID

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

    # Copy attributes AS-IS (keep original values including old ID).
    # The ID attribute will be updated in a separate PUT step after the
    # POST succeeds. This avoids DHIS2 unique-constraint rejections when
    # the new ID happens to already exist during the orgUnit move.
    for attr in tei.get('attributes', []):
        payload['attributes'].append({
            'attribute': attr['attribute'],
            'value': attr.get('value', ''),
        })

    # Copy enrollments and their events, updating orgUnit to match TEI
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


def update_enrollment_ou(enrollment_uid, dest_ou_uid):
    """
    Update an enrollment's orgUnit using the enrollments API.
    This is necessary because POST /api/trackedEntityInstances doesn't 
    reliably update enrollment orgUnits.
    
    Args:
        enrollment_uid: Enrollment UID to update
        dest_ou_uid: Destination org unit UID
        
    Returns:
        (success: bool, error_msg: str)
    """
    # Fetch the enrollment
    data = api_get(f'/api/enrollments/{enrollment_uid}.json', params={
        'fields': '*'
    })
    if data is None:
        return False, f"Could not fetch enrollment {enrollment_uid}"
    
    # Update orgUnit
    data['orgUnit'] = dest_ou_uid
    
    # PUT the updated enrollment
    ok, resp = api_post(
        '/api/enrollments',
        {'enrollments': [data]},
        params={'strategy': 'UPDATE'}
    )
    if ok:
        return True, ''
    return False, resp.get('error', 'Unknown enrollment update error')


def transfer_program_ownership(tei_uid, program_id, dest_ou_uid):
    """
    Transfer program ownership to the destination OU.
    This is CRITICAL for the TEI to appear in web UI queries at the destination.
    
    DHIS2 uses program ownership to determine which OUs can see a TEI in queries.
    Without transferring ownership, the TEI won't show up in Tracker Capture.
    
    Args:
        tei_uid: TEI UID
        program_id: Program UID
        dest_ou_uid: Destination org unit UID
        
    Returns:
        (success: bool, error_msg: str)
    """
    from shared.dhis2_client import SESSION, DHIS2_URL
    
    resp = SESSION.put(
        f'{DHIS2_URL}/api/tracker/ownership/transfer',
        params={
            'trackedEntityInstance': tei_uid,
            'program': program_id,
            'ou': dest_ou_uid
        }
    )
    
    if resp.status_code in [200, 204]:
        return True, ''
    return False, f"Ownership transfer failed: {resp.status_code} - {resp.text[:200]}"


def update_tei_attribute(tei_uid, attribute_uid, new_value, program_id=None, dest_ou_code=None):
    """
    Update a single attribute on a TEI using POST with strategy=UPDATE.
    This is needed because the bulk POST import doesn't reliably update attributes.
    
    If the new_value already exists, will auto-increment the sequence number and retry
    up to 10 times to find an available ID.

    Args:
        tei_uid: TEI UID to update
        attribute_uid: attribute UID to set
        new_value: new attribute value
        program_id: DHIS2 program ID (required to fetch program-scoped attributes)
        dest_ou_code: destination OU code (e.g. 'DE_KAPH') for auto-incrementing IDs

    Returns:
        (success: bool, error_msg: str, final_value: str)
    """
    from shared.id_utils import extract_sequence_number, build_id
    
    attempted_value = new_value
    max_retries = 10
    
    for attempt in range(max_retries):
        # Check if attempted_value already exists on another TEI (unique constraint)
        check_params = {
            'filter': f'{attribute_uid}:EQ:{attempted_value}',
            'fields': 'trackedEntityInstance',
            'ouMode': 'ALL',
            'pageSize': 1
        }
        if program_id:
            check_params['program'] = program_id
        
        existing = api_get('/api/trackedEntityInstances.json', params=check_params)
        conflict_found = False
        if existing:
            existing_teis = existing.get('trackedEntityInstances', [])
            for t in existing_teis:
                if t.get('trackedEntityInstance') != tei_uid:
                    conflict_found = True
                    break
        
        if not conflict_found:
            # No conflict - proceed with this value
            break
        
        # Conflict found - increment sequence and retry
        if dest_ou_code and attempt < max_retries - 1:
            seq = extract_sequence_number(attempted_value)
            if seq is not None:
                # Extract type code from ID (e.g., 'OVC' from 'DE_KAPH_OVC_00000001')
                parts = attempted_value.split('_')
                if len(parts) >= 3:
                    type_code = parts[2]
                    new_seq = seq + 1
                    attempted_value = build_id(dest_ou_code, type_code, new_seq)
                    continue
        
        # Can't increment or max retries reached
        return False, f"ID '{attempted_value}' already exists on TEI {existing_teis[0].get('trackedEntityInstance')}", attempted_value
    
    if attempt >= max_retries - 1 and conflict_found:
        return False, f"Could not find available ID after {max_retries} attempts", attempted_value
    
    # Fetch TEI with program to ensure program-scoped attributes are included
    fetch_params = {
        'fields': 'trackedEntityInstance,trackedEntityType,orgUnit,'
                  'attributes[attribute,value]'
    }
    if program_id:
        fetch_params['program'] = program_id

    data = api_get(f'/api/trackedEntityInstances/{tei_uid}.json', params=fetch_params)
    if data is None:
        return False, f"Could not fetch TEI {tei_uid} for attribute update", attempted_value

    # POST with strategy=UPDATE to update just the attribute
    # This is more reliable than PUT and matches DHIS2 best practices
    update_payload = {
        'trackedEntityInstances': [{
            'trackedEntityInstance': data['trackedEntityInstance'],
            'trackedEntityType': data.get('trackedEntityType', ''),
            'orgUnit': data.get('orgUnit', ''),
            'attributes': [{'attribute': attribute_uid, 'value': attempted_value}]
        }]
    }

    ok, resp = api_post(
        '/api/trackedEntityInstances',
        update_payload,
        params={
            'strategy': 'UPDATE',
            'mergeMode': 'MERGE'
        }
    )
    if ok:
        return True, '', attempted_value
    return False, resp.get('error', 'Unknown update error'), attempted_value


def execute_transfer(transfer_teis, dest_ou_uid, id_mappings, output_dir='outputs/transfer', dest_ou_code=None):
    """
    Execute the transfer of TEIs to the destination org unit.

    3-step process:
    1. POST TEI with updated orgUnits (TEI + events)
    2. POST enrollments separately (DHIS2 doesn't update enrollment orgUnits in step 1)
    3. Transfer program ownership (CRITICAL for web UI visibility)

    Step 3 is essential - without it, TEIs won't appear in Tracker Capture queries
    even though the data is correctly moved in the database.

    Args:
        transfer_teis: list of full TEI dicts
        dest_ou_uid: destination org unit UID
        id_mappings: list of id mapping dicts from id_generator
        output_dir: directory for saving transfer log
        dest_ou_code: destination OU code (e.g. 'DE_KAPH') for auto-incrementing IDs

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
    print(f"  Method:            3-step: POST (TEI+events) → POST (enrollments) → Transfer ownership")
    print(f"  {'═' * 70}\n")

    start_time = time.time()

    for i, tei in enumerate(transfer_teis, 1):
        tei_uid = tei['trackedEntityInstance']
        mapping = id_map.get(tei_uid)

        payload = build_transfer_payload(tei, dest_ou_uid)

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
                # Step 2: Update enrollment orgUnits separately (POST doesn't update them reliably)
                enr_err = ''
                for enrollment in tei.get('enrollments', []):
                    enr_uid = enrollment.get('enrollment')
                    if enr_uid:
                        enr_ok, enr_msg = update_enrollment_ou(enr_uid, dest_ou_uid)
                        if not enr_ok:
                            enr_err = f"Enrollment {enr_uid} update failed: {enr_msg}"
                            errors.append(f"{tei_uid}: {enr_err}")
                            break
                
                # Step 3: Transfer program ownership (CRITICAL for web UI visibility)
                ownership_err = ''
                for enrollment in tei.get('enrollments', []):
                    program_id = enrollment.get('program')
                    if program_id:
                        own_ok, own_msg = transfer_program_ownership(tei_uid, program_id, dest_ou_uid)
                        if not own_ok:
                            ownership_err = f"Ownership transfer failed: {own_msg}"
                            errors.append(f"{tei_uid}: {ownership_err}")
                            break
                
                combined_err = enr_err or ownership_err
                success_count += 1
                results.append({
                    'tei_uid': tei_uid,
                    'status': 'OK' if not combined_err else 'PARTIAL',
                    'old_id': old_id,
                    'new_id': old_id,  # Keep original ID (no ID update)
                    'events': tei_events,
                    'error': combined_err,
                })
        else:
            error_count += 1
            err = resp.get('error', 'Unknown error')
            
            # Extract conflict details from DHIS2 response
            import_summaries = resp.get('response', {}).get('importSummaries', [])
            if import_summaries:
                summary = import_summaries[0]
                description = summary.get('description', '')
                conflicts = summary.get('conflicts', [])
                if conflicts:
                    conflict_details = '; '.join([c.get('value', '') for c in conflicts])
                    err = f"{err} | {conflict_details}"
                elif description:
                    err = f"{err} | {description}"
            
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
