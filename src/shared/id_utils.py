"""
Shared ID generation utilities for CPMIS Toolkit.
Handles Household ID and Child UIC generation based on org unit codes.
Extracted from cleanup Phase 2 for cross-app reuse.
"""
import re

SEQ_LENGTH = 8

# Program definitions shared across apps
PROGRAMS = {
    'household': {
        'id': 'lTaqt0loQak',
        'name': 'Household - CPMIS',
        'id_attribute': 'SYUXY9pax4w',
        'id_attribute_name': 'Household ID',
        'type_code': 'HH',
        'firstname_attribute': 'BEW0LacDZlt',
        'surname_attribute': 'J6IRtvVe7qL',
    },
    'harmonized': {
        'id': 'xhzwCCKzFBM',
        'name': 'MW Harmonized OVC Program - CPMIS',
        'id_attribute': 'cxr1eaTGEBO',
        'id_attribute_name': 'Child UIC',
        'type_code': 'OVC',
        'firstname_attribute': 'UADoN3P2lNa',
        'surname_attribute': 'AJBnw1hCqte',
    }
}


def extract_attribute(tei, attribute_uid):
    """Extract a single attribute value from a TEI."""
    for attr in tei.get('attributes', []):
        if attr.get('attribute') == attribute_uid:
            return attr.get('value', '')
    return ''


def extract_current_id(tei, id_attribute):
    """Extract the current ID value from a TEI's attributes."""
    return extract_attribute(tei, id_attribute)


def get_tei_display_name(tei, program_key):
    """
    Get a human-readable display name for a TEI.
    For households: 'Firstname Surname'
    For children: 'Firstname Surname'
    """
    program = PROGRAMS.get(program_key, {})
    first = extract_attribute(tei, program.get('firstname_attribute', ''))
    surname = extract_attribute(tei, program.get('surname_attribute', ''))
    name = f"{first} {surname}".strip()
    return name or '(no name)'


def extract_sequence_number(current_id):
    """
    Extract the numeric sequence from an existing ID.
    Handles formats like:
      HH_0034588 → 34588
      ZALAMB15909 → 15909
      ZA_LAMB_HH_00000001 → 1
    """
    if not current_id:
        return 0
    match = re.search(r'(\d+)\s*$', current_id)
    return int(match.group(1)) if match else 0


def build_id(ou_code, type_code, sequence):
    """Build a standardised ID string. E.g. ZA_CHIK_HH_00000001."""
    return f"{ou_code}_{type_code}_{str(sequence).zfill(SEQ_LENGTH)}"


def get_max_sequence_from_teis(teis, id_attribute):
    """
    Scan a list of TEIs and return the highest sequence number found
    for the given ID attribute.
    """
    max_seq = 0
    for tei in teis:
        current_id = extract_current_id(tei, id_attribute)
        seq = extract_sequence_number(current_id)
        if seq > max_seq:
            max_seq = seq
    return max_seq
