"""
TEI Fetcher — Fetches TEIs, enrollments, events, and relationships from DHIS2.
Filters by enrollment year range and builds full transfer payloads.
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.dhis2_client import api_get, fetch_paged, DHIS2_URL, SESSION
from shared.id_utils import PROGRAMS


def fetch_teis_via_enrollments(org_unit_uid, program_key, year_start, year_end, page_size=50):
    """
    Fetch TEIs via enrollments API (workaround for TEI query caching issues).
    
    Returns list of TEI dicts with nested enrollments/events.
    """
    program = PROGRAMS[program_key]
    program_id = program['id']
    
    # Date range for enrollment filter
    start_date = f"{year_start}-01-01"
    end_date = f"{year_end}-12-31"
    
    print(f"  📡 Fetching {program['name']} enrollments from {org_unit_uid} "
          f"(enrolled {year_start}-{year_end})...")
    
    # First, get enrollments at this OU
    enr_resp = SESSION.get(
        f'{DHIS2_URL}/api/enrollments.json',
        params={
            'ou': org_unit_uid,
            'program': program_id,
            'enrollmentEnrolledAfter': start_date,
            'enrollmentEnrolledBefore': end_date,
            'fields': 'enrollment,trackedEntityInstance',
            'pageSize': 1000
        }
    )
    
    if enr_resp.status_code != 200:
        print(f"\r  ⚠️  Enrollment query failed: {enr_resp.status_code}".ljust(80))
        return []
    
    enrollments = enr_resp.json().get('enrollments', [])
    tei_uids = list(set(e.get('trackedEntityInstance') for e in enrollments if e.get('trackedEntityInstance')))
    
    print(f"\r  📡 Found {len(enrollments)} enrollments for {len(tei_uids)} unique TEIs".ljust(80))
    
    if not tei_uids:
        print(f"\r  ✅ Fetched 0 TEIs, 0 events".ljust(80))
        return []
    
    # Fetch full TEI details for each
    all_teis = []
    for i, tei_uid in enumerate(tei_uids, 1):
        print(f"\r  📡 Fetching TEI details: [{i}/{len(tei_uids)}]".ljust(80), end='', flush=True)
        
        tei_data = api_get(f'/api/trackedEntityInstances/{tei_uid}.json', params={
            'program': program_id,
            'fields': (
                'trackedEntityInstance,trackedEntityType,orgUnit,created,createdBy,'
                'attributes[attribute,displayName,value,created,lastUpdated],'
                'enrollments[enrollment,program,orgUnit,enrollmentDate,incidentDate,'
                'status,created,createdBy,'
                'events[event,program,programStage,orgUnit,eventDate,dueDate,'
                'status,created,createdBy,'
                'dataValues[dataElement,value,created,lastUpdated,storedBy]]],'
                'relationships[relationship,relationshipType,from[trackedEntityInstance[trackedEntityInstance]],'
                'to[trackedEntityInstance[trackedEntityInstance]]]'
            )
        })
        
        if tei_data:
            all_teis.append(tei_data)
    
    # Count events
    total_events = sum(
        len(ev)
        for tei in all_teis
        for enr in tei.get('enrollments', [])
        for ev in [enr.get('events', [])]
    )
    
    print(f"\r  ✅ Fetched {len(all_teis)} TEIs, {total_events} events".ljust(80))
    return all_teis


def fetch_teis_full(org_unit_uid, program_key, year_start, year_end, page_size=50):
    """
    Fetch TEIs with full enrollments, events, and relationships for a given
    org unit, program, and enrollment year range.
    
    Uses enrollments API as primary method (more reliable after transfers).

    Returns list of TEI dicts with nested enrollments/events.
    """
    # Try enrollments API first (works better after transfers)
    teis = fetch_teis_via_enrollments(org_unit_uid, program_key, year_start, year_end, page_size)
    if teis:
        return teis
    
    # Fallback to direct TEI query (for backwards compatibility)
    program = PROGRAMS[program_key]
    program_id = program['id']

    # Date range for enrollment filter
    start_date = f"{year_start}-01-01"
    end_date = f"{year_end}-12-31"

    print(f"  📡 Fetching {program['name']} TEIs from {org_unit_uid} "
          f"(enrolled {year_start}-{year_end})...")

    all_teis = []
    page = 1

    while True:
        params = {
            'ou': org_unit_uid,
            'program': program_id,
            'programStartDate': start_date,
            'programEndDate': end_date,
            'fields': (
                'trackedEntityInstance,trackedEntityType,orgUnit,created,createdBy,'
                'attributes[attribute,displayName,value,created,lastUpdated],'
                'enrollments[enrollment,program,orgUnit,enrollmentDate,incidentDate,'
                'status,created,createdBy,'
                'events[event,program,programStage,orgUnit,eventDate,dueDate,'
                'status,created,createdBy,'
                'dataValues[dataElement,value,created,lastUpdated,storedBy]]],'
                'relationships[relationship,relationshipType,from[trackedEntityInstance[trackedEntityInstance]],'
                'to[trackedEntityInstance[trackedEntityInstance]]]'
            ),
            'pageSize': page_size,
            'page': page,
            'totalPages': True,
        }

        data = api_get('/api/trackedEntityInstances.json', params=params)
        if data is None:
            break

        teis = data.get('trackedEntityInstances', [])
        pager = data.get('pager', {})
        total = pager.get('total', len(teis))
        page_count = pager.get('pageCount', 1)

        all_teis.extend(teis)

        if total > 0:
            pct = len(all_teis) * 100 // total
            print(f"\r  📡 Fetching: [{len(all_teis)}/{total}] ({pct}%)".ljust(80), end='', flush=True)

        if page >= page_count:
            break
        page += 1

    # Count events
    total_events = sum(
        len(ev)
        for tei in all_teis
        for enr in tei.get('enrollments', [])
        for ev in [enr.get('events', [])]
    )

    print(f"\r  ✅ Fetched {len(all_teis)} TEIs, {total_events} events".ljust(80))
    return all_teis


def fetch_relationships_for_tei(tei_uid):
    """Fetch all relationships for a specific TEI."""
    data = api_get(f'/api/trackedEntityInstances/{tei_uid}.json', params={
        'fields': 'relationships[relationship,relationshipType,'
                  'from[trackedEntityInstance[trackedEntityInstance]],'
                  'to[trackedEntityInstance[trackedEntityInstance]]]'
    })
    if data:
        return data.get('relationships', [])
    return []


def build_relationship_graph(household_teis, child_teis):
    """
    Build a mapping of household ↔ child relationships.

    Returns:
        hh_to_children: dict of household_uid -> set of child_uids
        child_to_hh: dict of child_uid -> household_uid
    """
    hh_uids = {t['trackedEntityInstance'] for t in household_teis}
    child_uids = {t['trackedEntityInstance'] for t in child_teis}

    hh_to_children = {uid: set() for uid in hh_uids}
    child_to_hh = {}

    # Scan relationships from both TEI types
    for tei in household_teis + child_teis:
        tei_uid = tei['trackedEntityInstance']
        for rel in tei.get('relationships', []):
            from_uid = (rel.get('from', {})
                        .get('trackedEntityInstance', {})
                        .get('trackedEntityInstance', ''))
            to_uid = (rel.get('to', {})
                      .get('trackedEntityInstance', {})
                      .get('trackedEntityInstance', ''))

            # Determine which is the household and which is the child
            if from_uid in hh_uids and to_uid in child_uids:
                hh_to_children[from_uid].add(to_uid)
                child_to_hh[to_uid] = from_uid
            elif to_uid in hh_uids and from_uid in child_uids:
                hh_to_children[to_uid].add(from_uid)
                child_to_hh[from_uid] = to_uid

    return hh_to_children, child_to_hh


def resolve_transfer_set(keep_uids, all_teis, hh_to_children, child_to_hh):
    """
    Given TEIs the user wants to KEEP at source, determine the full
    transfer set — ensuring household-child relationships stay intact.

    Args:
        keep_uids: set of TEI UIDs the user wants to keep
        all_teis: list of all TEI dicts
        hh_to_children: dict hh_uid -> set(child_uids)
        child_to_hh: dict child_uid -> hh_uid

    Returns:
        (keep_set, transfer_set) — both sets of UIDs
    """
    all_uids = {t['trackedEntityInstance'] for t in all_teis}
    keep_set = set(keep_uids)

    # Expand keep_set to preserve relationships:
    # If a child is kept, keep its household
    # If a household is kept, keep all its children
    expanded = True
    while expanded:
        expanded = False
        for uid in list(keep_set):
            # Child → keep household
            if uid in child_to_hh:
                hh = child_to_hh[uid]
                if hh in all_uids and hh not in keep_set:
                    keep_set.add(hh)
                    expanded = True
            # Household → keep children
            if uid in hh_to_children:
                for child in hh_to_children[uid]:
                    if child in all_uids and child not in keep_set:
                        keep_set.add(child)
                        expanded = True

    transfer_set = all_uids - keep_set

    # Expand transfer_set to preserve relationships for transferred TEIs:
    # If a child is being transferred, ensure its household is too (if not kept)
    # If a household is being transferred, ensure its children are too (if not kept)
    expanded = True
    while expanded:
        expanded = False
        for uid in list(transfer_set):
            if uid in child_to_hh:
                hh = child_to_hh[uid]
                if hh in all_uids and hh not in keep_set and hh not in transfer_set:
                    transfer_set.add(hh)
                    expanded = True
            if uid in hh_to_children:
                for child in hh_to_children[uid]:
                    if child in all_uids and child not in keep_set and child not in transfer_set:
                        transfer_set.add(child)
                        expanded = True

    return keep_set, transfer_set
