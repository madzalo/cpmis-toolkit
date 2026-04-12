"""
ID Generator for Transfer — Generates new IDs at the destination org unit.
Queries the destination for existing max sequences to avoid collisions.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.dhis2_client import api_get
from shared.id_utils import (
    PROGRAMS, SEQ_LENGTH, extract_current_id,
    extract_sequence_number, build_id, get_max_sequence_from_teis
)


def get_dest_max_sequences(dest_ou_uid):
    """
    Query the destination org unit to find the current max sequence numbers
    for both Household IDs and Child UICs.

    Returns:
        dict: {'household': int, 'harmonized': int}
    """
    max_seqs = {}

    for program_key, program in PROGRAMS.items():
        print(f"  📡 Querying {program['name']} at destination...", end='', flush=True)

        params = {
            'ou': dest_ou_uid,
            'program': program['id'],
            'fields': f'attributes[attribute,value]',
            'paging': 'false',
        }
        data = api_get('/api/trackedEntityInstances.json', params=params)

        if data is None:
            max_seqs[program_key] = 0
            print(f" ⚠️  Could not query (assuming 0)")
            continue

        existing_teis = data.get('trackedEntityInstances', [])
        max_seq = get_max_sequence_from_teis(existing_teis, program['id_attribute'])
        max_seqs[program_key] = max_seq
        print(f" ✅ {len(existing_teis)} existing TEIs, max seq: {max_seq}")

    return max_seqs


def generate_transfer_ids(transfer_teis, dest_ou_code, dest_ou_uid):
    """
    Generate new IDs for TEIs being transferred to the destination org unit.

    Args:
        transfer_teis: list of TEI dicts to transfer
        dest_ou_code: org unit code for the destination (e.g. 'ZA_CHIK')
        dest_ou_uid: UID of the destination org unit

    Returns:
        list of dicts: [{'tei_uid', 'old_id', 'new_id', 'type_code', 'program_key'}, ...]
    """
    # Get current max sequences at destination
    max_seqs = get_dest_max_sequences(dest_ou_uid)

    id_mappings = []
    hh_seq = max_seqs.get('household', 0)
    ovc_seq = max_seqs.get('harmonized', 0)

    hh_attr = PROGRAMS['household']['id_attribute']
    child_attr = PROGRAMS['harmonized']['id_attribute']

    for tei in transfer_teis:
        uid = tei['trackedEntityInstance']
        hh_id = extract_current_id(tei, hh_attr)
        child_id = extract_current_id(tei, child_attr)

        if hh_id:
            hh_seq += 1
            new_id = build_id(dest_ou_code, 'HH', hh_seq)
            id_mappings.append({
                'tei_uid': uid,
                'old_id': hh_id,
                'new_id': new_id,
                'type_code': 'HH',
                'program_key': 'household',
                'attribute': hh_attr,
            })
        elif child_id:
            ovc_seq += 1
            new_id = build_id(dest_ou_code, 'OVC', ovc_seq)
            id_mappings.append({
                'tei_uid': uid,
                'old_id': child_id,
                'new_id': new_id,
                'type_code': 'OVC',
                'program_key': 'harmonized',
                'attribute': child_attr,
            })
        else:
            # TEI has no ID — generate one based on enrollment
            enrollments = tei.get('enrollments', [])
            for enr in enrollments:
                prog_id = enr.get('program', '')
                if prog_id == PROGRAMS['household']['id']:
                    hh_seq += 1
                    new_id = build_id(dest_ou_code, 'HH', hh_seq)
                    id_mappings.append({
                        'tei_uid': uid,
                        'old_id': '',
                        'new_id': new_id,
                        'type_code': 'HH',
                        'program_key': 'household',
                        'attribute': hh_attr,
                    })
                    break
                elif prog_id == PROGRAMS['harmonized']['id']:
                    ovc_seq += 1
                    new_id = build_id(dest_ou_code, 'OVC', ovc_seq)
                    id_mappings.append({
                        'tei_uid': uid,
                        'old_id': '',
                        'new_id': new_id,
                        'type_code': 'OVC',
                        'program_key': 'harmonized',
                        'attribute': child_attr,
                    })
                    break

    return id_mappings
